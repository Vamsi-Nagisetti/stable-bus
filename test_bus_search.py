import json
import os

from dotenv import load_dotenv
from Adaptors.AOPayBusAPI.AOPayAdaptee import AOPayAdaptee
from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter

load_dotenv()

adaptee = AOPayAdaptee(
    base_url=os.environ["AOPAY_BASE_URL"],
    timeout=30,
)

adapter = AOPayAdapter(
    adaptee=adaptee,
    registration_id=os.environ["AOPAY_REGISTRATION_ID"],
    ip_address=os.environ["AOPAY_IP_ADDRESS"],
    imei_number=os.environ["AOPAY_IMEI_NUMBER"],
)

# Hyderabad (3) -> Vijayawada (5)
# Date format: MM/DD/YYYY
travel_date = "10/30/2026"

try:
    result = adapter.BusSearch(
        from_city="3",
        to_city="5",
        travel_date=travel_date,
    )

    if not isinstance(result, dict):
        print("Unexpected response type:", type(result).__name__)
    else:
        header = result.get("response_Header", {})
        buses = result.get("buses", [])

        print("Response header:")
        print(json.dumps(header, indent=2))
        print("Number of buses:", len(buses) if isinstance(buses, list) else "Unexpected format")

        if isinstance(buses, list):
            print("\nFirst five buses:")
            for bus in buses[:5]:
                print(json.dumps({
                    "operator_Name": bus.get("operator_Name"),
                    "bus_Type": bus.get("bus_Type"),
                    "departure_Time": bus.get("departure_Time"),
                    "arrival_Time": bus.get("arrival_Time"),
                    "available_Seats": bus.get("available_Seats"),
                    "from_City": bus.get("from_City"),
                    "to_City": bus.get("to_City"),
                    "travelDate": bus.get("travelDate"),
                    "bookable": bus.get("bookable"),
                }, indent=2))

        if str(header.get("error_Code")) == "0000":
            print("\nBusSearch API call succeeded.")
            print("Search key received:", bool(result.get("search_Key")))
        else:
            print("\nBusSearch returned an error. Check the response header.")

except Exception as exc:
    print("BusSearch API call failed:", type(exc).__name__, str(exc))