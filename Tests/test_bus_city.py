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



try:

    result = adapter.BusCityList()



    if not isinstance(result, dict):

        print("Unexpected response type:", type(result).__name__)

    else:

        header = result.get("response_Header", {})

        cities = result.get("cityDetails", [])



        print("Response header:")

        print(json.dumps(header, indent=2))

        print("Number of cities:", len(cities) if isinstance(cities, list) else "Unexpected format")



        if isinstance(cities, list):

            print("First five cities:")

            print(json.dumps(cities[:5], indent=2))



        if str(header.get("error_Code")) == "0000":

            print("BusCityList API call succeeded.")

        else:

            print("Check the provider response for the error details.")



except Exception as exc:

    print("BusCityList API call failed:", type(exc).__name__, str(exc))
