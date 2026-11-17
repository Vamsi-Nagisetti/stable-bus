
from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor

adaptee = RedisCacheAdaptee()
cache = RedisCacheAdaptor(adaptee)

try:
    cache.set("stablebus:test", "hello", 60)
    print("Retrieved:", cache.get("stablebus:test"))

    cache.delete("stablebus:test")
    print("After deletion:", cache.get("stablebus:test"))

except Exception as exc:
    print("Cache test failed:", exc)

finally:
    adaptee.close()
