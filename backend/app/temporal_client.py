"""The Temporal CLIENT used by FastAPI.

The client does NOT run workflows. It only talks to the Temporal Server over
gRPC to: start workflows, send signals, run queries, describe workflows and
fetch their history. The Worker (temporal_worker.py) is what executes code.
"""
import asyncio
import logging

from temporalio.client import Client

from app.config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE

_client: Client | None = None


async def connect(retries: int = 30) -> Client:
    """Connect to Temporal, retrying for a while (in Docker the server may still be booting)."""
    global _client
    for attempt in range(1, retries + 1):
        try:
            _client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
            return _client
        except Exception as e:
            if attempt == retries:
                raise
            logging.warning("Temporal not reachable at %s (%s), retrying...", TEMPORAL_ADDRESS, e)
            await asyncio.sleep(2)


def get_client() -> Client:
    if _client is None:
        raise RuntimeError("Temporal client not connected yet")
    return _client
