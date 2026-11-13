"""Process an uploaded source file by id and save the results in the database.

Usage (from the backend folder):
    python -m scripts.process_file --file-id 3
    python -m scripts.process_file --file-id 3 --rerun     # admin re-run (FR-045)

Until the RabbitMQ worker is wired up, this is how a stored upload is processed.
"""

import argparse
import sys

from app.core.config import settings
from app.core.processing_dependencies import build_process_cv_use_case
from app.domain.entities.processing_attempt import AttemptTrigger
from app.infrastructure.persistence.db.session import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-id", type=int, required=True)
    parser.add_argument("--rerun", action="store_true", help="record as an admin re-run")
    args = parser.parse_args()

    trigger = AttemptTrigger.ADMIN_RERUN if args.rerun else AttemptTrigger.FIRST_RUN
    with SessionLocal() as db:
        result = build_process_cv_use_case(db, settings).execute(args.file_id, trigger)

    print(f"file {args.file_id}: {result.status}"
          f" | attempts={len(result.attempts)} fields={len(result.field_records)}"
          f" review={len(result.review_items)}"
          + (f" | {result.reason}" if result.reason else ""))
    return 0 if result.status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
