
import os
import redis
from dotenv import load_dotenv

load_dotenv()


class RedisCacheAdaptee:

    def __init__(self):
        self.client = redis.Redis(
            host=os.getenv("REDIS_HOST"),
            port=int(os.getenv("REDIS_PORT")),
            username=os.getenv("REDIS_USERNAME"),
            password=os.getenv("REDIS_PASSWORD"),
            ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
            decode_responses=True,
            socket_connect_timeout=10,
        )

    def set_value(self, key: str, value: str, ttl: int) -> None:
        self.client.set(key, value, ex=ttl)

    def get_value(self, key: str):
        return self.client.get(key)

    def delete_value(self, key: str) -> None:
        self.client.delete(key)

    def get_ttl(self, key: str) -> int:
        return self.client.ttl(key)

    
    def execute_atomic(
        self,
        script: str,
        keys: list[str],
        args: list
    ):
        redis_script = self.client.register_script(script)

        return redis_script(
            keys=keys,
            args=args,
            client=self.client
        )


    def close(self) -> None:
        self.client.close()
