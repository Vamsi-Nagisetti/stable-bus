import runpy

# Reuse the existing test setup and call the API directly.
from dotenv import load_dotenv
import os

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

result = adapter.BusSearch(
    from_city="3",
    to_city="5",
    travel_date="10/30/2026",
)

print("Search key present:", bool(result.get("search_Key")))

buses = result.get("buses", [])
print("Total buses:", len(buses))

for index, bus in enumerate(buses):
    boarding = bus.get("boardingDetails") or []
    dropping = bus.get("droppingDetails") or []

    print({
        "index": index,
        "operator": bus.get("operator_Name"),
        "bookable": bus.get("bookable"),
        "bus_key_present": bool(bus.get("bus_Key")),
        "boarding_points": len(boarding),
        "dropping_points": len(dropping),
        "first_boarding_id": boarding[0].get("boarding_Id") if boarding else None,
        "first_dropping_id": dropping[0].get("dropping_Id") if dropping else None,
    })

    if bus.get("bookable") is True or str(bus.get("bookable")).lower() == "true":
        print("First bookable bus found at index:", index)
        break