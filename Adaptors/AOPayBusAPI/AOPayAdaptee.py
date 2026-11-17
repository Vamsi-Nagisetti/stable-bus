import logging
import time

import requests

logger = logging.getLogger("stablebus.aopay.http")


class AOPayAdaptee:

    def __init__(self, base_url, headers=None, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    def _post(self, endpoint, payload):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        started = time.perf_counter()
        request_id = payload.get("request_Id", "-") if isinstance(payload, dict) else "-"
        try:
            response = requests.post(
                url, json=payload, headers=self.headers, timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("AO Pay returned a non-object JSON response")
            header = data.get("response_Header") or {}
            logger.info(
                "AO Pay request completed endpoint=%s request_id=%s http_status=%s provider_code=%s duration_ms=%.1f",
                endpoint, request_id, response.status_code, header.get("error_Code"),
                (time.perf_counter() - started) * 1000,
            )
            return data
        except requests.Timeout:
            logger.exception(
                "AO Pay request timed out endpoint=%s request_id=%s timeout_seconds=%s",
                endpoint, request_id, self.timeout,
            )
            raise
        except requests.RequestException:
            logger.exception(
                "AO Pay HTTP request failed endpoint=%s request_id=%s duration_ms=%.1f",
                endpoint, request_id, (time.perf_counter() - started) * 1000,
            )
            raise
        except (ValueError, requests.exceptions.JSONDecodeError):
            logger.exception("AO Pay response parsing failed endpoint=%s request_id=%s", endpoint, request_id)
            raise

    def BusSearch(self, payload):
        return self._post("/api/V1/Bus/Travel/BusSearch", payload)

    def BusCityList(self, payload):
        return self._post("/api/V1/Bus/Travel/BusCityList", payload)

    def BusSeatMap(self, endpoint, payload):
        return self._post(endpoint, payload)

    def BusTempBooking(self, endpoint, payload):
        return self._post(endpoint, payload)

    def BusTicketing(self, endpoint, payload):
        return self._post(endpoint, payload)

    def BusRequery(self, endpoint, payload):
        return self._post(endpoint, payload)

    def BusCancellationCharges(self, payload):
        return self._post("/api/V1/Bus/Travel/BusCancellationCharges", payload)

    def BusCancellation(self, payload):
        return self._post("/api/V1/Bus/Travel/BusCancellation", payload)

    def BusHistory(self, payload):
        return self._post("/api/V1/Bus/Travel/BusHistory", payload)
