"""Temporal WORKFLOW - the orchestration of a payment.

WHY is this code in the Workflow and not in an Activity?
  The workflow only DECIDES what happens next: which activity to run, in what
  order, with which timeouts/retries, whether to wait for approval, and what to
  do when something fails. It does no I/O itself.

  Temporal persists every step (activity results, signals, timers) in the
  workflow HISTORY. If the worker crashes, a new worker REPLAYS this code
  against the history to rebuild its exact state and continues where it left
  off. For replay to work, workflow code must be DETERMINISTIC:
    - no database / network / file access   -> put it in an activity
    - no datetime.now(), random, uuid4()     -> use workflow.now(), workflow.uuid4()
    - no time.sleep() / asyncio.sleep()      -> use workflow.sleep() / wait_condition()
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

# Activity imports are "passed through" the workflow sandbox: the workflow only
# needs their names/signatures. The activity code itself runs outside the sandbox.
with workflow.unsafe.imports_passed_through():
    from app.activities import payment_activities as acts
    from app.models.payment import (
        NotificationInput,
        PaymentInput,
        PaymentState,
        SaveTransactionInput,
    )

# Default retry policy for activities: wait 1s, 2s, 4s, ... between attempts.
DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)


@workflow.defn
class PaymentWorkflow:
    def __init__(self) -> None:
        self.state: PaymentState | None = None
        self._decision: str | None = None  # set by the approve/reject signals

    # ------------------------------------------------------------------ Signals
    # Signals are how the outside world (our FastAPI endpoint) pushes data INTO
    # a running workflow. They are durably recorded in the workflow history.
    @workflow.signal
    def approve(self, approver: str) -> None:
        if self.state and self.state.approval_status == "PENDING":
            self._decision = "APPROVED"
            self.state.approval_note = f"Approved by {approver}"

    @workflow.signal
    def reject(self, reason: str) -> None:
        if self.state and self.state.approval_status == "PENDING":
            self._decision = "REJECTED"
            self.state.approval_note = f"Rejected: {reason}"

    # ------------------------------------------------------------------ Query
    # Queries let the API READ the workflow's in-memory state (read-only).
    @workflow.query
    def get_status(self) -> PaymentState:
        return self.state

    # ------------------------------------------------------------------ Main
    @workflow.run
    async def run(self, payment: PaymentInput) -> PaymentState:
        self.state = PaymentState(
            payment_id=payment.payment_id,
            amount=payment.amount,
            sender=payment.sender,
            receiver=payment.receiver,
        )
        try:
            # 1-3. Validate, check balance, fraud check
            await self._step("validate_payment", acts.validate_payment, payment)
            await self._step("check_balance", acts.check_balance, payment)
            await self._step(
                "fraud_check",
                acts.fraud_check,
                payment,
                # Short timeout so the "simulate timeout" demo trips it quickly.
                timeout=timedelta(seconds=5),
            )

            # 4. Human approval for large payments (a pure workflow decision).
            if payment.amount > payment.approval_threshold:
                approved = await self._wait_for_approval(payment)
                if not approved:
                    self.state.status = "REJECTED"
                    self._skip_remaining(except_step="send_notification")
                    await self._notify(
                        payment, f"Payment {payment.payment_id} was not approved."
                    )
                    self.state.current_step = None
                    return self.state
            else:
                self.state.steps["approval"] = "skipped"

            # 5. Move the money. The heartbeat timeout lets Temporal detect a
            #    dead worker quickly and retry the activity on another worker.
            result = await self._step(
                "process_payment",
                acts.process_payment,
                payment,
                timeout=timedelta(seconds=60),
                heartbeat_timeout=timedelta(seconds=5),
                retry=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    maximum_attempts=3,
                ),
            )
            self.state.transaction_id = result.transaction_id

            # 6. Save the business record
            await self._step(
                "save_transaction",
                acts.save_transaction,
                SaveTransactionInput(
                    transaction_id=result.transaction_id,
                    payment_id=payment.payment_id,
                    workflow_id=workflow.info().workflow_id,
                    sender=payment.sender,
                    receiver=payment.receiver,
                    amount=payment.amount,
                    status="COMPLETED",
                ),
            )

            # 7. Notify
            await self._step(
                "send_notification",
                acts.send_notification,
                NotificationInput(
                    payment_id=payment.payment_id,
                    message=f"Payment of INR {payment.amount:,.2f} from {payment.sender} "
                    f"to {payment.receiver} completed ({result.transaction_id}).",
                ),
            )
            self.state.status = "COMPLETED"
            self.state.current_step = None
            return self.state

        except ActivityError as err:
            # FAILURE HANDLING: an activity failed for good (non-retryable error,
            # or all retries used up). The workflow decides what to do about it:
            # here we notify the customer and then fail the workflow so it shows
            # as "Failed" in Temporal. (A real system might also compensate,
            # e.g. refund, if money had already moved.)
            reason = str(err.cause) if err.cause else str(err)
            self.state.error = reason
            self.state.status = "FAILED"
            self._skip_remaining(except_step="send_notification")
            await self._notify(payment, f"Payment {payment.payment_id} failed: {reason}")
            self.state.current_step = None
            raise ApplicationError(f"Payment failed: {reason}", non_retryable=True)

    # ------------------------------------------------------------------ Helpers
    async def _step(
        self,
        name,
        activity_fn,
        arg,
        timeout=timedelta(seconds=15),
        heartbeat_timeout=None,
        retry=DEFAULT_RETRY,
    ):
        """Run one activity and keep the step status up to date for the Query."""
        self.state.current_step = name
        self.state.steps[name] = "running"
        try:
            result = await workflow.execute_activity(
                activity_fn,
                arg,
                start_to_close_timeout=timeout,
                heartbeat_timeout=heartbeat_timeout,
                retry_policy=retry,
            )
        except ActivityError:
            self.state.steps[name] = "failed"
            raise
        self.state.steps[name] = "completed"
        return result

    async def _wait_for_approval(self, payment: PaymentInput) -> bool:
        self.state.current_step = "approval"
        self.state.steps["approval"] = "waiting"
        self.state.approval_status = "PENDING"
        self.state.status = "WAITING_APPROVAL"
        try:
            # Durable wait: survives worker restarts and blocks no thread while
            # waiting. It ends when a signal sets _decision, or on timeout.
            await workflow.wait_condition(
                lambda: self._decision is not None,
                timeout=timedelta(seconds=payment.approval_timeout_seconds),
            )
        except TimeoutError:
            self._decision = "TIMED_OUT"
            self.state.approval_note = "No decision in time - auto-rejected"

        self.state.approval_status = self._decision
        self.state.status = "RUNNING"
        approved = self._decision == "APPROVED"
        self.state.steps["approval"] = "completed" if approved else "failed"
        return approved

    async def _notify(self, payment: PaymentInput, message: str) -> None:
        # Best effort: a failed notification should not hide the real outcome.
        try:
            await self._step(
                "send_notification",
                acts.send_notification,
                NotificationInput(payment_id=payment.payment_id, message=message),
            )
        except ActivityError:
            pass

    def _skip_remaining(self, except_step: str | None = None) -> None:
        for step, status in self.state.steps.items():
            if status == "pending" and step != except_step:
                self.state.steps[step] = "skipped"
