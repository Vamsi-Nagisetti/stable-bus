import pytest

from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor


@pytest.fixture(scope="session")
def redis_cache():
    """
    Creates a connection to the existing cloud Redis instance.
    Reuses the StableBus Redis adapter.
    """
    redis_adaptee = RedisCacheAdaptee()
    cache = RedisCacheAdaptor(redis_adaptee)

    # Confirm Redis connectivity before running integration tests.
    redis_adaptee.client.ping()

    yield cache

    # Close the Redis connection after all tests finish.
    redis_adaptee.close()