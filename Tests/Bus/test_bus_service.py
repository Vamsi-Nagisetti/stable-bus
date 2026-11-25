
import pytest
from unittest.mock import Mock

from Services.Bus.bus_service import BusService


def test_get_cities_success():
    provider = Mock()
    provider.BusCityList.return_value = {
        "response_Header": {
            "error_Code": "0000",
            "error_Desc": "Success"
        },
        "cityDetails": [
            {"cityId": 3, "cityName": "Hyderabad"},
            {"cityId": 5, "cityName": "Vijayawada"}
        ]
    }

    service = BusService(provider)

    result = service.get_cities()

    assert result["total"] == 2
    assert len(result["cities"]) == 2
    assert result["cities"][0]["cityName"] == "Hyderabad"
    provider.BusCityList.assert_called_once()


def test_get_cities_invalid_provider_response():
    provider = Mock()
    provider.BusCityList.return_value = None

    service = BusService(provider)

    with pytest.raises(ValueError, match="Invalid response"):
        service.get_cities()


def test_get_cities_invalid_header():
    provider = Mock()
    provider.BusCityList.return_value = {
        "response_Header": None,
        "cityDetails": []
    }

    service = BusService(provider)

    with pytest.raises(ValueError, match="Invalid response header"):
        service.get_cities()


def test_get_cities_provider_error():
    provider = Mock()
    provider.BusCityList.return_value = {
        "response_Header": {
            "error_Code": "9999",
            "error_Desc": "Provider error"
        },
        "cityDetails": []
    }

    service = BusService(provider)

    with pytest.raises(RuntimeError, match="Provider error"):
        service.get_cities()


def test_get_cities_invalid_city_list():
    provider = Mock()
    provider.BusCityList.return_value = {
        "response_Header": {
            "error_Code": "0000",
            "error_Desc": "Success"
        },
        "cityDetails": None
    }

    service = BusService(provider)

    with pytest.raises(ValueError, match="Invalid city list"):
        service.get_cities()
