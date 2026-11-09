
import redis
import os
from dotenv import load_dotenv

load_dotenv()

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    password=os.getenv("REDIS_PASSWORD"),
    decode_responses=True,
    ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
)

print("Redis database:", redis_client.connection_pool.connection_kwargs.get("db"))
print("Keys before clearing:", redis_client.dbsize())

confirmation = input(
    "This will DELETE ALL KEYS in this Redis database. Type DELETE to continue: "
)

if confirmation == "DELETE":
    redis_client.flushdb()
    print("Redis database cleared successfully.")
    print("Keys remaining:", redis_client.dbsize())
else:
    print("Operation cancelled.")
