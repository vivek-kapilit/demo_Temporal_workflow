"""Data classes shared by the API, the Workflow and the Activities.

Temporal serializes these to JSON when they cross process boundaries
(API -> Temporal Server -> Worker), so keep them plain and serializable.
"""
from dataclasses import dataclass, field
from typing import Optional

# Order of steps shown in the UI.
STEPS = [
    "validate_payment",
    "check_balance",
    "fraud_check",
    "approval",
    "process_payment",
    "save_transaction",
    "send_notification",
]


@dataclass
class PaymentInput:
    payment_id: str
    sender: str
    receiver: str
    amount: float
    # Business rules are passed IN to the workflow (instead of the workflow
    # reading env vars) because workflow code must be deterministic.
    approval_threshold: float = 50_000
    approval_timeout_seconds: int = 600
    # Failure-simulation switches (demo only).
    simulate_fraud_failure: bool = False
    simulate_fraud_timeout: bool = False
    simulate_payment_failure: bool = False


@dataclass
class ProcessResult:
    transaction_id: str


@dataclass
class SaveTransactionInput:
    transaction_id: str
    payment_id: str
    workflow_id: str
    sender: str
    receiver: str
    amount: float
    status: str


@dataclass
class NotificationInput:
    payment_id: str
    message: str


@dataclass
class PaymentState:
    """What the workflow reports back through its `get_status` Query."""

    payment_id: str
    amount: float
    sender: str
    receiver: str
    # RUNNING | WAITING_APPROVAL | COMPLETED | REJECTED | FAILED
    status: str = "RUNNING"
    current_step: Optional[str] = None
    # step name -> pending | running | completed | failed | skipped | waiting
    steps: dict = field(default_factory=lambda: {s: "pending" for s in STEPS})
    # NOT_REQUIRED | PENDING | APPROVED | REJECTED | TIMED_OUT
    approval_status: str = "NOT_REQUIRED"
    approval_note: Optional[str] = None
    transaction_id: Optional[str] = None
    error: Optional[str] = None
