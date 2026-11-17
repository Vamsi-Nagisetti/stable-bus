
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter


class FakeAdaptee:
    def __init__(self):
        self.endpoint = None
        self.payload = None

    def BusSeatMap(self, endpoint, payload):
        self.endpoint = endpoint
        self.payload = payload
        return {"status": "success", "seatMap": []}


class AOPayAdapterTestCase(unittest.TestCase):

    def setUp(self):
        self.adaptee = FakeAdaptee()
        self.adapter = AOPayAdapter(
            adaptee=self.adaptee,
            registration_id="TEST_REGISTRATION",
            ip_address="127.0.0.1",
            imei_number="TEST_IMEI",
        )

    def test_bus_seat_map_forwards_all_arguments(self):
        bus_key = "BUS_KEY_123"
        search_key = "SEARCH_KEY_456"
        boarding_id = "BOARD_1"
        dropping_id = "DROP_1"

        result = self.adapter.BusSeatMap(
            bus_key,
            search_key,
            boarding_id,
            dropping_id,
        )

        self.assertEqual(result["status"], "success")

        self.assertEqual(
            self.adaptee.endpoint,
            "/api/V1/Bus/Travel/BusSeatMap",
        )

        payload = self.adaptee.payload

        self.assertEqual(payload["bus_Key"], bus_key)
        self.assertEqual(payload["search_Key"], search_key)
        self.assertEqual(payload["boarding_Id"], boarding_id)
        self.assertEqual(payload["dropping_Id"], dropping_id)

        self.assertEqual(
            payload["registrationID"],
            "TEST_REGISTRATION",
        )
        self.assertEqual(payload["iP_Address"], "127.0.0.1")
        self.assertEqual(payload["imeI_Number"], "TEST_IMEI")

        self.assertIn("request_Id", payload)
        self.assertTrue(payload["request_Id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
