"""Run CV processing after the HTTP response has been sent (FR-013).

The upload endpoint answers at once with the file id; processing (OCR, Gemini,
saving the profile) then runs in the API process. When the RabbitMQ worker is
built, the upload should publish the file id instead and the worker should call
the same use case - nothing else changes.
"""

import logging

from app.core.config import settings
from app.core.processing_dependencies import build_process_cv_use_case
from app.domain.entities.processing_attempt import AttemptTrigger
from app.infrastructure.persistence.db.session import SessionLocal

logger = logging.getLogger("cverge.processing")


def process_file_in_background(file_id: int,
                               trigger: AttemptTrigger = AttemptTrigger.FIRST_RUN) -> None:
    # Own session: the request's session is closed by the time this runs.
    with SessionLocal() as db:
        try:
            result = build_process_cv_use_case(db, settings).execute(file_id, trigger)
            # NFR-022: log ids and status only, never CV content.
            logger.info("file %s processed: %s (%d attempts)", file_id, result.status,
                        len(result.attempts))
        except Exception:
            # The use case has already marked the file failed where it could.
            logger.exception("file %s: processing crashed", file_id)
