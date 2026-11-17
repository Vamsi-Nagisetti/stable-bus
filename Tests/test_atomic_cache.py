from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor


adaptee = RedisCacheAdaptee()
cache = RedisCacheAdaptor(adaptee)

try:
    script = """
    local value = redis.call('INCR', KEYS[1])
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    return value
    """

    result = cache.execute_atomic(
        script=script,
        keys=["stablebus:test:atomic"],
        args=[60]
    )

    print("Redis atomic operation result:", result)

finally:
    cache.delete("stablebus:test:atomic")
    adaptee.close()