"""Tiny SQLite layer for the fake bank.

Only ACTIVITIES (and read-only API endpoints) touch the database.
Workflow code never does I/O - see workflows/payment_workflow.py for why.
"""
import sqlite3
from contextlib import contextmanager

from app.config import DATABASE_PATH

SEED_ACCOUNTS = [
    # (account_id, owner, balance in INR)
    ("ACC-1001", "Alice", 100_000.0),
    ("ACC-1002", "Bob", 250_000.0),
    ("ACC-1003", "Charlie", 5_000.0),
    ("ACC-1004", "Diana", 1_000_000.0),
]


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                owner      TEXT NOT NULL,
                balance    REAL NOT NULL
            );
            -- Money movements done by process_payment. payment_id is UNIQUE so a
            -- retried activity can never move the same money twice (idempotency).
            CREATE TABLE IF NOT EXISTS ledger (
                payment_id     TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                sender         TEXT NOT NULL,
                receiver       TEXT NOT NULL,
                amount         REAL NOT NULL,
                created_at     TEXT DEFAULT CURRENT_TIMESTAMP
            );
            -- Business record written by save_transaction.
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                payment_id     TEXT UNIQUE NOT NULL,
                workflow_id    TEXT NOT NULL,
                sender         TEXT NOT NULL,
                receiver       TEXT NOT NULL,
                amount         REAL NOT NULL,
                status         TEXT NOT NULL,
                created_at     TEXT DEFAULT CURRENT_TIMESTAMP
            );
            -- "Sent" notifications (we just store them - nothing is really sent).
            CREATE TABLE IF NOT EXISTS notifications (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id TEXT NOT NULL,
                message    TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.executemany(
            "INSERT OR IGNORE INTO accounts (account_id, owner, balance) VALUES (?, ?, ?)",
            SEED_ACCOUNTS,
        )
