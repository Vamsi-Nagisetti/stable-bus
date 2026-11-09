
class BusService:

    def __init__(self, bus_provider):
        self.bus_provider = bus_provider

    def get_cities(self) -> dict:
        result = self.bus_provider.BusCityList()

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
