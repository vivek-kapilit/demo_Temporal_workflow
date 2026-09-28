"""Temporal ACTIVITIES - the individual steps of a payment.

WHY is this code in an Activity and not in the Workflow?
  Activities are where anything non-deterministic or with side effects lives:
  reading/writing the database, calling other services, generating IDs,
  sleeping on the wall clock, random numbers, etc.

  Temporal gives activities:
    * automatic RETRIES (configured by the workflow's RetryPolicy)
    * TIMEOUTS (start_to_close, heartbeat)
    * results recorded in workflow history, so a finished activity is never
      re-run when the workflow replays after a worker restart.

  Because an activity may be retried (e.g. the worker crashed halfway through),
  activities that change data must be IDEMPOTENT - see process_payment.
"""
import asyncio
import uuid

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.config import PROCESSING_DELAY_SECONDS, STEP_DELAY_SECONDS
from app.db import get_conn
from app.models.payment import (
    NotificationInput,
    PaymentInput,
    ProcessResult,
    SaveTransactionInput,
)

FRAUD_LIMIT = 500_000  # fake rule: anything above this is "fraud"


def _log(msg: str) -> None:
    info = activity.info()
    activity.logger.info(f"[{info.activity_type} attempt={info.attempt}] {msg}")


async def _demo_delay(seconds: float = STEP_DELAY_SECONDS) -> None:
    """Artificial delay so the UI can show each step. Not needed in real code."""
    await asyncio.sleep(seconds)


def _get_account(conn, account_id: str):
    return conn.execute(
        "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
    ).fetchone()


@activity.defn
async def validate_payment(payment: PaymentInput) -> None:
    _log(f"validating {payment.payment_id}")
    await _demo_delay()

    # Business-rule errors are NON-retryable: retrying will not make them succeed.
    if payment.amount <= 0:
        raise ApplicationError("Amount must be greater than 0", non_retryable=True)
    if payment.sender == payment.receiver:
        raise ApplicationError("Sender and receiver must differ", non_retryable=True)
    with get_conn() as conn:
        for acc in (payment.sender, payment.receiver):
            if _get_account(conn, acc) is None:
                raise ApplicationError(f"Unknown account {acc}", non_retryable=True)


@activity.defn
async def check_balance(payment: PaymentInput) -> float:
    _log(f"checking balance of {payment.sender}")
    await _demo_delay()
    with get_conn() as conn:
        balance = _get_account(conn, payment.sender)["balance"]
    if balance < payment.amount:
        raise ApplicationError(
            f"Insufficient funds: balance {balance:,.2f} < amount {payment.amount:,.2f}",
            non_retryable=True,
        )
    return balance


@activity.defn
async def fraud_check(payment: PaymentInput) -> str:
    attempt = activity.info().attempt  # 1 on first try, 2 on first retry, ...
    _log("running fake fraud check")

    # --- Simulated TIMEOUT: attempt 1 takes longer than start_to_close_timeout.
    # Temporal cancels it, records a timeout, and schedules attempt 2.
    if payment.simulate_fraud_timeout and attempt == 1:
        _log("simulating a slow fraud service (will exceed the timeout)")
        await asyncio.sleep(60)

    await _demo_delay()

    # --- Simulated TRANSIENT FAILURE: attempts 1 and 2 fail, attempt 3 succeeds.
    # This is a normal (retryable) exception, so Temporal retries it.
    if payment.simulate_fraud_failure and attempt <= 2:
        raise RuntimeError(f"Fraud service unavailable (simulated, attempt {attempt})")

    if payment.amount > FRAUD_LIMIT:
        raise ApplicationError(
            f"Flagged as fraud: amount above {FRAUD_LIMIT:,}", non_retryable=True
        )
    return "LOW_RISK"


@activity.defn
async def process_payment(payment: PaymentInput) -> ProcessResult:
    """Moves the money. Long-running + heartbeating so we can demo worker crashes."""
    _log(f"processing {payment.amount} {payment.sender} -> {payment.receiver}")

    # Idempotency: if a previous attempt already moved the money (e.g. the worker
    # died right after committing), return the same result instead of paying twice.
    with get_conn() as conn:
        row = conn.execute(
            "SELECT transaction_id FROM ledger WHERE payment_id = ?", (payment.payment_id,)
        ).fetchone()
    if row:
        _log("already processed earlier - returning existing result")
        return ProcessResult(transaction_id=row["transaction_id"])

    # Simulate a slow bank call. We HEARTBEAT every second: if the worker dies,
    # heartbeats stop and Temporal notices within heartbeat_timeout, then
    # retries this activity on another (or the restarted) worker.
    for second in range(int(PROCESSING_DELAY_SECONDS)):
        activity.heartbeat(f"{second + 1}s of {PROCESSING_DELAY_SECONDS:.0f}s")
        await asyncio.sleep(1)

    if payment.simulate_payment_failure:
        # Retryable error -> Temporal retries until maximum_attempts is reached,
        # then the workflow receives the failure and handles it.
        raise RuntimeError("Bank rejected the transfer (simulated payment failure)")

    # UUIDs are fine here: activities may be non-deterministic.
    transaction_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
    with get_conn() as conn:  # one DB transaction: debit + credit + ledger row
        balance = _get_account(conn, payment.sender)["balance"]
        if balance < payment.amount:
            raise ApplicationError("Insufficient funds at processing time", non_retryable=True)
        conn.execute(
            "UPDATE accounts SET balance = balance - ? WHERE account_id = ?",
            (payment.amount, payment.sender),
        )
        conn.execute(
            "UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
            (payment.amount, payment.receiver),
        )
        conn.execute(
            "INSERT INTO ledger (payment_id, transaction_id, sender, receiver, amount) "
            "VALUES (?, ?, ?, ?, ?)",
            (payment.payment_id, transaction_id, payment.sender, payment.receiver, payment.amount),
        )
    return ProcessResult(transaction_id=transaction_id)


@activity.defn
async def save_transaction(txn: SaveTransactionInput) -> None:
    _log(f"saving {txn.transaction_id} with status {txn.status}")
    await _demo_delay()
    with get_conn() as conn:
        # INSERT OR REPLACE keyed by transaction_id -> safe to retry.
        conn.execute(
            "INSERT OR REPLACE INTO transactions "
            "(transaction_id, payment_id, workflow_id, sender, receiver, amount, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (txn.transaction_id, txn.payment_id, txn.workflow_id, txn.sender,
             txn.receiver, txn.amount, txn.status),
        )


@activity.defn
async def send_notification(note: NotificationInput) -> None:
    _log(f"notify: {note.message}")
    await _demo_delay(1)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notifications (payment_id, message) VALUES (?, ?)",
            (note.payment_id, note.message),
        )


ALL_ACTIVITIES = [
    validate_payment,
    check_balance,
    fraud_check,
    process_payment,
    save_transaction,
    send_notification,
]
