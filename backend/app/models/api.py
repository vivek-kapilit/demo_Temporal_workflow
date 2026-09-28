"""Request bodies for the FastAPI endpoints."""
from typing import Optional

from pydantic import BaseModel, Field


class CreatePaymentRequest(BaseModel):
    sender: str = Field(examples=["ACC-1001"])
    receiver: str = Field(examples=["ACC-1002"])
    amount: float = Field(examples=[1500])
    simulate_fraud_failure: bool = False
    simulate_fraud_timeout: bool = False
    simulate_payment_failure: bool = False


class ApprovalRequest(BaseModel):
    approver: str = "demo-user"
    reason: Optional[str] = None
