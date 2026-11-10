
import asyncio
import json
import logging

import aio_pika

from app.infrastructure.persistence.db.session import SessionLocal
from app.infrastructure.persistence.repositories.file_repository import (
    SourceFileRepository
)
from app.infrastructure.storage.local_file_storage import (
    LocalFileStorage
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_cv(file_id: int):
    """
    Get CV metadata from PostgreSQL
    and read file content from Local Storage.
    """

    with SessionLocal() as db:
        repository = SourceFileRepository(db)

        source_file = repository.get_by_id(file_id)

        if source_file is None:
            logger.warning(
                "File not found: file_id=%s",
                file_id
            )
            return None

        storage = LocalFileStorage()

        file_bytes = storage.read(
            source_file.storage_path
        )

        logger.info(
            "CV loaded: file_id=%s, filename=%s, size=%s bytes",
            file_id,
            source_file.original_name,
            len(file_bytes)
        )

        return file_bytes, source_file.original_name


async def handle_message(message: aio_pika.IncomingMessage):

    async with message.process(requeue=False):

        data = json.loads(message.body.decode("utf-8"))
        file_id = data["file_id"]

        logger.info(
            "Received message: file_id=%s",
            file_id
        )

        # Run blocking database and file I/O
        # outside the event loop
        result = await asyncio.to_thread(load_cv, file_id)

        if result is None:
            logger.warning(
                "Skipping missing file_id=%s",
                file_id
            )
            return

        file_bytes, filename = result

        logger.info(
            "File ready for extraction: %s (%s bytes)",
            filename,
            len(file_bytes)
        )

        # TODO: Call teammate's extraction function here

        logger.info(
            "Message acknowledged: file_id=%s",
            file_id
        )




