"""The Temporal WORKER - a separate process that actually runs our code.

    python -m app.temporal_worker

The worker long-polls the Temporal Server's task queue. When there is work
("run the next piece of PaymentWorkflow" or "run activity fraud_check"), the
server hands it to this process, the worker runs it and reports the result
back. The server stores the result in the workflow history.

You can stop this process at any time (Ctrl+C, kill) and start it again:
workflows are not lost - the server keeps their state, and the restarted
worker replays their history and continues.
"""
import asyncio
import logging

from temporalio.worker import Worker

from app.activities.payment_activities import ALL_ACTIVITIES
from app.config import TEMPORAL_ADDRESS, TEMPORAL_TASK_QUEUE
from app.db import init_db
from app.temporal_client import connect
from app.workflows.payment_workflow import PaymentWorkflow


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    client = await connect()
    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[PaymentWorkflow],
        activities=ALL_ACTIVITIES,
    )
    logging.info("Worker connected to %s, polling task queue '%s'", TEMPORAL_ADDRESS, TEMPORAL_TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
