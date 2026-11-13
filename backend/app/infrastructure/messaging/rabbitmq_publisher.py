
import json

import aio_pika
from aio_pika import DeliveryMode, Message

from app.application.interfaces.message_publisher import IMessagePublisher


class RabbitMQPublisher(IMessagePublisher):

    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url

    async def publish_cv(self, file_id: int) -> None:
        connection = await aio_pika.connect_robust(
            self.rabbitmq_url
        )

        try:
            channel = await connection.channel(
                publisher_confirms=True
            )

            queue = await channel.declare_queue(
                "cv.processing",
                durable=True
            )

            message = Message(
                body=json.dumps({
                    "file_id": file_id
                }).encode("utf-8"),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json"
            )

            await channel.default_exchange.publish(
                message,
                routing_key=queue.name,
                mandatory=True
            )

        finally:
            await connection.close()
