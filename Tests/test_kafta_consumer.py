
from messageQueues.KafkaEventConsumer import KafkaEventConsumer

consumer = KafkaEventConsumer()

try:
    consumer.consume(timeout=10)
finally:
    consumer.close()
