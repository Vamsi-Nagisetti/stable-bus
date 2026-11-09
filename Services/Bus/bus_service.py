
import json
import logging
from typing import Any

from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor


logger = logging.getLogger("stablebus.services.bus")


class BusService:

    CITIES_CACHE_KEY = "bus:cities:v1"
    CITIES_STALE_CACHE_KEY = "bus:cities:v1:stale"

    CITIES_CACHE_TTL = 86400
    CITIES_STALE_CACHE_TTL = 604800

    BUS_SEARCH_CACHE_TTL = 300
    BUS_SEARCH_MAX_CACHE_ENTRIES = 3
    BUS_SEARCH_METADATA_KEY = "bus:search:v1:metadata"

    def __init__(self, bus_provider, cache: RedisCacheAdaptor = None):
        self.bus_provider = bus_provider
        self.cache = cache

    # ---------------- CITY CACHE ----------------

    def _get_cached_cities(self, key: str) -> dict | None:

        if self.cache is None:
            return None

        try:
            cached_value = self.cache.get(key)

            if cached_value is None:
                return None

            cached_data = json.loads(cached_value)

            if (
                not isinstance(cached_data, dict)
                or not isinstance(cached_data.get("cities"), list)
                or not isinstance(cached_data.get("total"), int)
            ):
                logger.warning("Invalid city cache structure: %s", key)
                self.cache.delete(key)
                return None

            return cached_data

        except json.JSONDecodeError:
            logger.warning("Malformed city cache detected: %s", key)

            try:
                self.cache.delete(key)
            except Exception:
                logger.exception("Unable to delete malformed city cache")

            return None

        except Exception:
            logger.exception("Unable to read city cache: %s", key)
            return None

    def _set_cached_cities(
        self,
        key: str,
        data: dict,
        ttl: int,
    ) -> None:

        if self.cache is None:
            return

        try:
            self.cache.set(key, json.dumps(data), ttl)

        except Exception:
            logger.exception("Unable to write city cache: %s", key)

    def _validate_provider_response(self, result: Any) -> dict:

        if not isinstance(result, dict):
            raise ValueError("Invalid response received from bus provider")

        header = result.get("response_Header")

        if not isinstance(header, dict):
            raise ValueError("Invalid response header received from bus provider")

        if str(header.get("error_Code")) != "0000":
            raise RuntimeError(
                header.get("error_Desc") or "Unable to fetch cities"
            )

        cities = result.get("cityDetails")

        if not isinstance(cities, list):
            raise ValueError("Invalid city list received from bus provider")

        return {
            "cities": cities,
            "total": len(cities),
        }

    def get_cities(self) -> dict:

        cached_cities = self._get_cached_cities(self.CITIES_CACHE_KEY)

        if cached_cities is not None:
            logger.info("Bus cities cache HIT")
            return cached_cities

        logger.info("Bus cities cache MISS")

        try:
            result = self.bus_provider.BusCityList()
            cities_response = self._validate_provider_response(result)

        except Exception:
            logger.exception("AO Pay city fetch failed")

            stale_cities = self._get_cached_cities(
                self.CITIES_STALE_CACHE_KEY
            )

            if stale_cities is not None:
                logger.warning("Returning stale bus cities from Redis")
                return stale_cities

            raise

        self._set_cached_cities(
            self.CITIES_CACHE_KEY,
            cities_response,
            self.CITIES_CACHE_TTL,
        )

        self._set_cached_cities(
            self.CITIES_STALE_CACHE_KEY,
            cities_response,
            self.CITIES_STALE_CACHE_TTL,
        )

        logger.info(
            "Bus cities cached successfully. Total cities: %s",
            cities_response["total"],
        )

        return cities_response

    # ---------------- BUS SEARCH CACHE ----------------

    def _get_bus_search_cache_key(
        self,
        from_city: str,
        to_city: str,
        travel_date: str,
    ) -> str:

        normalized_date = travel_date.replace("/", "-")

        return (
            f"bus:search:v1:"
            f"{from_city}:{to_city}:{normalized_date}"
        )

    def _get_search_cache_metadata(self) -> dict:

        if self.cache is None:
            return {}

        try:
            value = self.cache.get(self.BUS_SEARCH_METADATA_KEY)

            if value is None:
                return {}

            metadata = json.loads(value)

            if not isinstance(metadata, dict):
                raise ValueError("Invalid search cache metadata")

            return metadata

        except Exception:
            logger.exception("Unable to read bus search cache metadata")

            try:
                self.cache.delete(self.BUS_SEARCH_METADATA_KEY)
            except Exception:
                logger.exception("Unable to delete search cache metadata")

            return {}

    def _save_search_cache_metadata(self, metadata: dict) -> None:

        if self.cache is None:
            return

        try:
            self.cache.set(
                self.BUS_SEARCH_METADATA_KEY,
                json.dumps(metadata),
                self.BUS_SEARCH_CACHE_TTL,
            )

        except Exception:
            logger.exception("Unable to save bus search cache metadata")

    def _record_search_cache_hit(self, cache_key: str) -> None:

        metadata = self._get_search_cache_metadata()

        entry = metadata.get(cache_key)

        if not isinstance(entry, dict):
            entry = {"frequency": 1}

        entry["frequency"] = entry.get("frequency", 0) + 1
        metadata[cache_key] = entry

        self._save_search_cache_metadata(metadata)

        logger.info(
            "Bus search cache frequency updated: %s -> %s",
            cache_key,
            entry["frequency"],
        )

    def _evict_least_frequently_used(self) -> None:

        metadata = self._get_search_cache_metadata()

        # Remove metadata entries whose actual cache keys have expired.
        active_metadata = {}

        for key, details in metadata.items():

            try:
                if self.cache.get(key) is not None:
                    active_metadata[key] = details
            except Exception:
                logger.exception("Unable to verify search cache key: %s", key)

        metadata = active_metadata

        if len(metadata) >= self.BUS_SEARCH_MAX_CACHE_ENTRIES:

            # Python dictionaries preserve insertion order.
            # min() therefore evicts the oldest entry when frequencies tie.
            least_used_key = min(
                metadata,
                key=lambda key: metadata[key].get("frequency", 0),
            )

            self.cache.delete(least_used_key)
            metadata.pop(least_used_key, None)

            logger.info(
                "Evicted least frequently used bus search cache: %s",
                least_used_key,
            )

        self._save_search_cache_metadata(metadata)

    def _cache_bus_search_result(
        self,
        cache_key: str,
        result: dict,
    ) -> None:

        if self.cache is None:
            return

        try:
            metadata = self._get_search_cache_metadata()

            # Prune expired entries before deciding whether eviction is needed.
            active_metadata = {}

            for key, details in metadata.items():
                try:
                    if self.cache.get(key) is not None:
                        active_metadata[key] = details
                except Exception:
                    logger.exception(
                        "Unable to verify search cache key: %s",
                        key,
                    )

            metadata = active_metadata

            # Only evict when inserting a new cache entry.
            if cache_key not in metadata:
                if len(metadata) >= self.BUS_SEARCH_MAX_CACHE_ENTRIES:

                    least_used_key = min(
                        metadata,
                        key=lambda key: metadata[key].get("frequency", 0),
                    )

                    self.cache.delete(least_used_key)
                    metadata.pop(least_used_key, None)

                    logger.info(
                        "Evicted least frequently used bus search cache: %s",
                        least_used_key,
                    )

            self.cache.set(
                cache_key,
                json.dumps(result),
                self.BUS_SEARCH_CACHE_TTL,
            )

            metadata[cache_key] = {"frequency": 1}

            self._save_search_cache_metadata(metadata)

            logger.info(
                "Bus search cached. Active entries: %s, TTL: %s seconds",
                len(metadata),
                self.BUS_SEARCH_CACHE_TTL,
            )

        except Exception:
            logger.exception("Unable to cache bus search response")

    def search_buses(
        self,
        from_city: str,
        to_city: str,
        travel_date: str,
    ) -> dict:

        cache_key = self._get_bus_search_cache_key(
            from_city,
            to_city,
            travel_date,
        )

        # 1. Check Redis cache.
        if self.cache is not None:
            try:
                cached_value = self.cache.get(cache_key)

                if cached_value is not None:
                    cached_result = json.loads(cached_value)

                    if (
                        isinstance(cached_result, dict)
                        and isinstance(
                            cached_result.get("response_Header"), dict
                        )
                        and str(
                            cached_result["response_Header"].get("error_Code")
                        ) == "0000"
                        and isinstance(cached_result.get("buses"), list)
                        and cached_result.get("search_Key")
                    ):
                        logger.info("Bus search cache HIT: %s", cache_key)

                        self._record_search_cache_hit(cache_key)

                        return cached_result

                    logger.warning(
                        "Invalid bus search cache entry: %s",
                        cache_key,
                    )
                    self.cache.delete(cache_key)

            except json.JSONDecodeError:
                logger.warning(
                    "Malformed bus search cache entry: %s",
                    cache_key,
                )

                try:
                    self.cache.delete(cache_key)
                except Exception:
                    logger.exception(
                        "Unable to delete malformed bus search cache"
                    )

            except Exception:
                logger.exception("Unable to read bus search cache")

        logger.info("Bus search cache MISS: %s", cache_key)

        # 2. Fetch fresh results from AO Pay.
        result = self.bus_provider.BusSearch(
            from_city=from_city,
            to_city=to_city,
            travel_date=travel_date,
        )

        if not isinstance(result, dict):
            raise ValueError("Invalid response received from bus provider")

        header = result.get("response_Header")

        if not isinstance(header, dict):
            raise ValueError("Invalid response header received from bus provider")

        if str(header.get("error_Code")) != "0000":
            raise RuntimeError(
                header.get("error_Desc") or "Unable to search buses"
            )

        buses = result.get("buses")

        if not isinstance(buses, list):
            raise ValueError("Invalid bus list received from bus provider")

        # 3. Cache only successful responses with LFU eviction.
        if result.get("search_Key") and self.cache is not None:
            self._cache_bus_search_result(cache_key, result)

        logger.info(
            "Bus search completed. Total buses: %s",
            len(buses),
        )

        return result

    # ---------------- BUS SEAT MAP ----------------

    def get_seat_map(
        self,
        bus_key: str,
        search_key: str,
        boarding_id: str,
        dropping_id: str,
    ) -> dict:
        """
        Fetch the seat map for a selected bus from the provider.

        Seat maps are intentionally not cached because seat availability
        can change frequently.
        """

        if not all([bus_key, search_key, boarding_id, dropping_id]):
            raise ValueError("Bus key, search key, boarding ID and dropping ID are required")

        logger.info("Fetching seat map for bus: %s", bus_key)

        result = self.bus_provider.BusSeatMap(
            bus_key,
            search_key,
            boarding_id,
            dropping_id,
        )

        if not isinstance(result, dict):
            raise ValueError("Invalid seat map response received from bus provider")

        header = result.get("response_Header")

        if not isinstance(header, dict):
            raise ValueError("Invalid seat map response header")

        if str(header.get("error_Code")) != "0000":
            raise RuntimeError(
                header.get("error_Desc") or "Unable to fetch bus seat map"
            )

        logger.info("Seat map fetched successfully for bus: %s", bus_key)

        return result