"""CV worker: processes files queued by the upload endpoint (and admin re-runs).

Each RabbitMQ message is {"file_id": ..., "trigger": "first_run" | "admin_rerun"}.
Processing runs the full pipeline (ProcessCVUseCase): text extraction with OCR
for scans, LLM field extraction with up to 3 attempts, validation and evidence
checks, review items, and the profile update - all saved in one transaction.

Run it from the backend folder (next to the API):
    python -m app.workers.main
"""

import asyncio
import json
import logging

import aio_pika

from app.core.config import settings
from app.core.processing_dependencies import build_process_cv_use_case
from app.domain.entities.processing_attempt import AttemptTrigger
from app.infrastructure.persistence.db.session import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_cv(file_id: int, trigger: AttemptTrigger) -> None:
    """Run the pipeline for one file with its own database session."""
    with SessionLocal() as db:
        result = build_process_cv_use_case(db, settings).execute(file_id, trigger)
    # NFR-022: log ids and outcomes only, never CV content.
    logger.info(
        "Processed file_id=%s: status=%s, attempts=%s, review_items=%s",
        file_id, result.status, len(result.attempts), len(result.review_items)
    )


async def handle_message(message: aio_pika.IncomingMessage):
    async with message.process(requeue=False):
        data = json.loads(message.body.decode("utf-8"))
        file_id = data["file_id"]
        trigger = AttemptTrigger(data.get("trigger", AttemptTrigger.FIRST_RUN.value))

        logger.info(
            "Received message: file_id=%s, trigger=%s",
            file_id, trigger.value
        )

        # OCR, the LLM call and database work are blocking: run them
        # outside the event loop.
        try:
            await asyncio.to_thread(process_cv, file_id, trigger)
        except Exception:
            # The use case already marked the file failed where it could, so
            # the job is visible to an administrator (FR-042); don't requeue.
            logger.exception("Processing failed: file_id=%s", file_id)

        logger.info(
            "Message acknowledged: file_id=%s",
            file_id
        )
