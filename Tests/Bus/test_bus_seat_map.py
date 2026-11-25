
import unittest
from unittest.mock import MagicMock

from Services.Bus.bus_service import BusService


class TestBusServiceSeatMap(unittest.TestCase):

    def setUp(self):
        self.provider = MagicMock()
        self.service = BusService(
            bus_provider=self.provider,
            cache=None,
        )

    def test_get_seat_map_success(self):
        expected_response = {
            "response_Header": {"error_Code": "0000"},
            "seatDetails": [],
        }
        self.provider.BusSeatMap.return_value = expected_response

        result = self.service.get_seat_map(
            "BUS123",
            "SEARCH123",
            "BOARD1",
            "DROP1",
        )

        self.assertEqual(result, expected_response)
        self.provider.BusSeatMap.assert_called_once_with(
            "BUS123",
            "SEARCH123",
            "BOARD1",
            "DROP1",
        )

    def test_get_seat_map_provider_error(self):
        self.provider.BusSeatMap.return_value = {
            "response_Header": {
                "error_Code": "1001",
                "error_Desc": "Seat map unavailable",
            }
        }

        with self.assertRaisesRegex(RuntimeError, "Seat map unavailable"):
            self.service.get_seat_map(
                "BUS123",
                "SEARCH123",
                "BOARD1",
                "DROP1",
            )

    def test_get_seat_map_invalid_response(self):
        self.provider.BusSeatMap.return_value = None

        with self.assertRaisesRegex(ValueError, "Invalid seat map response"):
            self.service.get_seat_map(
                "BUS123",
                "SEARCH123",
                "BOARD1",
                "DROP1",
            )

    def test_get_seat_map_missing_parameters(self):
        with self.assertRaisesRegex(ValueError, "required"):
            self.service.get_seat_map(
                "",
                "SEARCH123",
                "BOARD1",
                "DROP1",
            )

        self.provider.BusSeatMap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
