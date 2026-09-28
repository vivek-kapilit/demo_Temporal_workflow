"""All configuration comes from environment variables (optionally loaded from backend/.env)."""
import os

from dotenv import load_dotenv

load_dotenv()

TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "payment-task-queue")

DATABASE_PATH = os.getenv("DATABASE_PATH", "payments.db")

APPROVAL_THRESHOLD = float(os.getenv("APPROVAL_THRESHOLD", "50000"))
APPROVAL_TIMEOUT_SECONDS = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "600"))

STEP_DELAY_SECONDS = float(os.getenv("STEP_DELAY_SECONDS", "2"))
PROCESSING_DELAY_SECONDS = float(os.getenv("PROCESSING_DELAY_SECONDS", "10"))

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
