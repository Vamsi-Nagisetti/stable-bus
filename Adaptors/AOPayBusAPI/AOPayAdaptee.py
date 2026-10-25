import requests


class AOPayAdaptee:

    def __init__(self, base_url, headers=None, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    def _post(self, endpoint, payload):
        response = requests.post(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            json=payload,
            headers=self.headers,
            timeout=self.timeout,
        )

        response.raise_for_status()
        return response.json()

    def BusSearch(self, payload):
        return self._post(
            "/api/V1/Bus/Travel/BusSearch",
            payload,
        )

    def BusCityList(self, payload):
        return self._post(
            "/api/V1/Bus/Travel/BusCityList",
            payload,
        )

    def BusSeatMap(self, endpoint, payload):
        return self._post(endpoint, payload)

    def BusTempBooking(self, endpoint, payload):
        return self._post(endpoint, payload)

    def BusTicketing(self, endpoint, payload):
        return self._post(endpoint, payload)

    def BusRequery(self, endpoint, payload):
        return self._post(endpoint, payload)