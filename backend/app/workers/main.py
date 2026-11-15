import asyncio
import logging

import aio_pika

from app.core.config import settings
from app.workers.cv_worker import handle_message


logger = logging.getLogger(__name__)

QUEUE_NAME = "cv.processing"


async def main():
    connection = await aio_pika.connect_robust(
        settings.RABBITMQ_URL
    )

    async with connection:
        channel = await connection.channel()

        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue(
            QUEUE_NAME,
            durable=True
        )

        await queue.consume(handle_message)

        logger.info("CV Worker started. Waiting for messages...")

        await asyncio.Future()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())