from unittest.mock import MagicMock

import pytest

from Repositories.UserPassengerRepository import UserPassengerRepository


@pytest.fixture
def table():
    return MagicMock()


@pytest.fixture
def repository(table):
    return UserPassengerRepository(table)


def test_add_passenger(repository, table):
    result = repository.add_passenger(
        user_id="user-123",
        name="Rahul",
        age=25,
        gender="Male"
    )

    assert result["user_id"] == "user-123"
    assert result["name"] == "Rahul"
    assert result["age"] == 25
    assert result["gender"] == "Male"
    assert result["passenger_id"]

    table.put_item.assert_called_once()


def test_get_passengers(repository, table):
    expected = [
        {
            "user_id": "user-123",
            "passenger_id": "passenger-1",
            "name": "Rahul",
            "age": 25,
            "gender": "Male"
        }
    ]

    table.query.return_value = {"Items": expected}

    result = repository.get_passengers("user-123")

    assert result == expected
    table.query.assert_called_once()


def test_update_passenger(repository, table):
    expected = {
        "user_id": "user-123",
        "passenger_id": "passenger-1",
        "name": "Rahul Kumar",
        "age": 26,
        "gender": "Male"
    }

    table.update_item.return_value = {"Attributes": expected}

    result = repository.update_passenger(
        user_id="user-123",
        passenger_id="passenger-1",
        name="Rahul Kumar",
        age=26,
        gender="Male"
    )

    assert result == expected
    table.update_item.assert_called_once()


def test_delete_passenger(repository, table):
    table.delete_item.return_value = {
        "Attributes": {
            "user_id": "user-123",
            "passenger_id": "passenger-1"
        }
    }

    result = repository.delete_passenger(
        "user-123",
        "passenger-1"
    )

    assert result is True
    table.delete_item.assert_called_once()


def test_delete_nonexistent_passenger(repository, table):
    table.delete_item.return_value = {}

    result = repository.delete_passenger(
        "user-123",
        "passenger-1"
    )

    assert result is False