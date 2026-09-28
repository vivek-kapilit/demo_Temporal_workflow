"""REST endpoints. Every endpoint here talks to Temporal through the CLIENT.

Notice what is NOT here: no payment logic runs inside FastAPI. The API only
starts workflows, sends signals, runs queries and reads history. The actual
work happens in the Worker process.
"""
import dataclasses
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from temporalio.api.enums.v1 import EventType, PendingActivityState
from temporalio.client import WorkflowExecutionStatus, WorkflowFailureError
from temporalio.service import RPCError

from app.config import APPROVAL_THRESHOLD, APPROVAL_TIMEOUT_SECONDS, TEMPORAL_TASK_QUEUE
from app.db import get_conn
from app.models.api import ApprovalRequest, CreatePaymentRequest
from app.models.payment import PaymentInput
from app.temporal_client import get_client
from app.workflows.payment_workflow import PaymentWorkflow

router = APIRouter()

# A query needs a running worker. If none answers quickly we report "worker offline".
QUERY_TIMEOUT = timedelta(seconds=3)


# --------------------------------------------------------------------- accounts
@router.get("/accounts")
def list_accounts():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM accounts ORDER BY account_id")]


@router.get("/transactions")
def list_transactions():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 50")
        return [dict(r) for r in rows]


# --------------------------------------------------------------------- payments
@router.post("/payments")
async def create_payment(req: CreatePaymentRequest):
    """Start a PaymentWorkflow. Returns immediately - the workflow runs in the worker."""
    payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
    workflow_id = f"payment-{payment_id}"
    payment = PaymentInput(
        payment_id=payment_id,
        sender=req.sender,
        receiver=req.receiver,
        amount=req.amount,
        approval_threshold=APPROVAL_THRESHOLD,
        approval_timeout_seconds=APPROVAL_TIMEOUT_SECONDS,
        simulate_fraud_failure=req.simulate_fraud_failure,
        simulate_fraud_timeout=req.simulate_fraud_timeout,
        simulate_payment_failure=req.simulate_payment_failure,
    )
    handle = await get_client().start_workflow(
        PaymentWorkflow.run,
        payment,
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
        # Memo = small metadata stored with the workflow, shown in lists/Temporal UI.
        memo={"sender": req.sender, "receiver": req.receiver, "amount": req.amount},
    )
    return {"payment_id": payment_id, "workflow_id": handle.id, "run_id": handle.result_run_id}


@router.get("/payments")
async def list_payments():
    """List recent payment workflows straight from Temporal's visibility store."""
    items = []
    async for wf in get_client().list_workflows("WorkflowType='PaymentWorkflow'", limit=30):
        memo = await wf.memo()
        items.append(
            {
                "workflow_id": wf.id,
                "status": wf.status.name if wf.status else None,
                "start_time": wf.start_time.isoformat() if wf.start_time else None,
                "close_time": wf.close_time.isoformat() if wf.close_time else None,
                **memo,
            }
        )
    return items


@router.get("/payments/{workflow_id}")
async def get_payment(workflow_id: str):
    """Combine three Temporal views of one workflow:
    1. describe()  -> Temporal's own status (RUNNING/COMPLETED/FAILED) + pending activities
    2. query()     -> the workflow's business state (steps, approval, transaction id)
    3. history     -> how many attempts each activity needed (retry count)
    """
    handle = get_client().get_workflow_handle(workflow_id)
    try:
        desc = await handle.describe()
    except RPCError:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    state, worker_online = None, True
    try:
        state = await handle.query(PaymentWorkflow.get_status, rpc_timeout=QUERY_TIMEOUT)
    except (RPCError, Exception):
        worker_online = False
        if desc.status == WorkflowExecutionStatus.COMPLETED:
            # Closed workflows keep their result in history: no worker needed.
            state = await handle.result()

    attempts, last_failures = await _activity_attempts(handle)

    # Activities that are scheduled/running/retrying right now.
    pending = []
    for pa in desc.raw_description.pending_activities:
        name = pa.activity_type.name
        attempts[name] = max(attempts.get(name, 0), pa.attempt)
        if pa.last_failure.message:
            last_failures[name] = pa.last_failure.message
        pending.append(
            {
                "activity": name,
                "attempt": pa.attempt,
                "state": PendingActivityState.Name(pa.state).removeprefix("PENDING_ACTIVITY_STATE_"),
                "last_failure": pa.last_failure.message or None,
                "next_attempt_time": pa.next_attempt_schedule_time.ToDatetime().isoformat()
                if pa.HasField("next_attempt_schedule_time")
                else None,
            }
        )

    failure = None
    if desc.status == WorkflowExecutionStatus.FAILED:
        try:
            await handle.result()
        except WorkflowFailureError as e:
            failure = str(e.cause) if e.cause else str(e)

    return {
        "workflow_id": workflow_id,
        "run_id": desc.run_id,
        "workflow_status": desc.status.name if desc.status else None,
        "start_time": desc.start_time.isoformat() if desc.start_time else None,
        "close_time": desc.close_time.isoformat() if desc.close_time else None,
        "history_length": desc.history_length,
        "worker_online": worker_online,
        "state": dataclasses.asdict(state) if state else None,
        "attempts": attempts,
        "last_failures": last_failures,
        "pending_activities": pending,
        "workflow_failure": failure,
    }


@router.get("/payments/{workflow_id}/history")
async def get_history(workflow_id: str):
    """A simplified, human-readable version of the workflow's event history."""
    handle = get_client().get_workflow_handle(workflow_id)
    history = await handle.fetch_history()
    scheduled = {}  # scheduled_event_id -> activity name
    events = []
    for e in history.events:
        kind = EventType.Name(e.event_type).removeprefix("EVENT_TYPE_")
        attr_name = e.WhichOneof("attributes")
        attrs = getattr(e, attr_name) if attr_name else None
        detail = ""
        if kind == "ACTIVITY_TASK_SCHEDULED":
            scheduled[e.event_id] = attrs.activity_type.name
            detail = attrs.activity_type.name
        elif kind == "ACTIVITY_TASK_STARTED":
            detail = f"{scheduled.get(attrs.scheduled_event_id)} (attempt {attrs.attempt})"
            if attrs.last_failure.message:
                detail += f" - previous failure: {attrs.last_failure.message}"
        elif kind == "ACTIVITY_TASK_COMPLETED":
            detail = scheduled.get(attrs.scheduled_event_id, "")
        elif kind in ("ACTIVITY_TASK_FAILED", "ACTIVITY_TASK_TIMED_OUT"):
            detail = f"{scheduled.get(attrs.scheduled_event_id)}: {attrs.failure.message}"
        elif kind == "WORKFLOW_EXECUTION_SIGNALED":
            detail = f"signal '{attrs.signal_name}'"
        elif kind == "TIMER_STARTED":
            detail = f"timer {attrs.start_to_fire_timeout.ToSeconds()}s"
        elif kind == "WORKFLOW_EXECUTION_FAILED":
            detail = attrs.failure.message
        elif kind == "WORKFLOW_EXECUTION_STARTED":
            detail = f"task queue '{attrs.task_queue.name}'"
        events.append(
            {
                "event_id": e.event_id,
                "time": e.event_time.ToDatetime().isoformat(),
                "type": kind,
                "detail": detail,
            }
        )
    return events


# --------------------------------------------------------------------- approval
@router.post("/payments/{workflow_id}/approve")
async def approve_payment(workflow_id: str, body: ApprovalRequest):
    return await _send_decision(workflow_id, PaymentWorkflow.approve, body.approver)


@router.post("/payments/{workflow_id}/reject")
async def reject_payment(workflow_id: str, body: ApprovalRequest):
    return await _send_decision(workflow_id, PaymentWorkflow.reject, body.reason or "Rejected by user")


async def _send_decision(workflow_id: str, signal, arg: str):
    handle = get_client().get_workflow_handle(workflow_id)
    try:
        state = await handle.query(PaymentWorkflow.get_status, rpc_timeout=QUERY_TIMEOUT)
        if state.approval_status != "PENDING":
            raise HTTPException(409, f"Payment is not waiting for approval ({state.approval_status})")
        note = "signal delivered"
    except HTTPException:
        raise
    except Exception:
        # Worker offline: a signal is still accepted and stored durably by the
        # Temporal Server; the workflow will process it when a worker is back.
        note = "worker offline - signal stored by Temporal, will be processed on restart"
    try:
        await handle.signal(signal, arg)
    except RPCError as e:
        raise HTTPException(400, f"Could not signal workflow: {e.message}")
    return {"workflow_id": workflow_id, "signal": signal.__name__, "note": note}


# --------------------------------------------------------------------- helpers
async def _activity_attempts(handle):
    """Read history: for each activity, the highest attempt number seen + last failure."""
    attempts, failures, scheduled = {}, {}, {}
    async for e in handle.fetch_history_events():
        if e.HasField("activity_task_scheduled_event_attributes"):
            scheduled[e.event_id] = e.activity_task_scheduled_event_attributes.activity_type.name
        elif e.HasField("activity_task_started_event_attributes"):
            a = e.activity_task_started_event_attributes
            name = scheduled.get(a.scheduled_event_id)
            attempts[name] = max(attempts.get(name, 0), a.attempt)
            if a.last_failure.message:
                failures[name] = a.last_failure.message
        elif e.HasField("activity_task_failed_event_attributes"):
            a = e.activity_task_failed_event_attributes
            failures[scheduled.get(a.scheduled_event_id)] = a.failure.message
        elif e.HasField("activity_task_timed_out_event_attributes"):
            a = e.activity_task_timed_out_event_attributes
            failures[scheduled.get(a.scheduled_event_id)] = a.failure.message
    return attempts, failures

