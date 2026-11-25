
import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from Adaptors.AOPayBusAPI.AOPayAdaptee import AOPayAdaptee
from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter


# Load environment variables
load_dotenv()

# Initialize AO Pay client
adaptee = AOPayAdaptee(
    base_url=os.environ["AOPAY_BASE_URL"],
    timeout=30
)

adapter = AOPayAdapter(
    adaptee=adaptee,
    registration_id=os.environ["AOPAY_REGISTRATION_ID"],
    ip_address=os.environ["AOPAY_IP_ADDRESS"],
    imei_number=os.environ["AOPAY_IMEI_NUMBER"],
)


# Search parameters
from_city = "3"       # Hyderabad
to_city = "5"         # Vijayawada

# Travel date: 7 days from today
travel_date = (datetime.now() + timedelta(days=7)).strftime("%m/%d/%Y")


print("=" * 60)
print("STABLEBUS - AO PAY BUS SEARCH TEST")
print("=" * 60)

print(f"From City   : {from_city}")
print(f"To City     : {to_city}")
print(f"Travel Date : {travel_date}")
print("-" * 60)


try:
    response = adapter.BusSearch(
        from_city=from_city,
        to_city=to_city,
        travel_date=travel_date
    )

    print("\nAPI RESPONSE:")
    print(json.dumps(response, indent=4, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("RESPONSE SUMMARY")
    print("=" * 60)

    if isinstance(response, dict):
        print("Status      :", response.get("statuss"))
        print("Message     :", response.get("message"))
        print("Search Key  :", response.get("search_Key"))

        buses = response.get("buses")

        if isinstance(buses, list):
            print("Bus Count   :", len(buses))
        else:
            print("Bus Count   : Not available")

    else:
        print("Unexpected response format:", type(response))

except Exception as e:
    print("\nBUS SEARCH FAILED")
    print(f"Error: {type(e).__name__}: {e}")

print("\nTest completed.")
