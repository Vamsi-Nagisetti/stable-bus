import pytest
from pydantic import ValidationError

from api.Schemas.PreRegistrationSchemas import CreatePreRegistrationRequest
from api.Schemas.ReviewSchemas import CreateReviewRequest


def test_pre_registration_requires_mobile_and_email():
    with pytest.raises(ValidationError):
        CreatePreRegistrationRequest(name="Test")


def test_pre_registration_normalizes_mobile_and_email():
    payload = CreatePreRegistrationRequest(
        name=" Test User ", mobile="9876543210", email=" TEST@Example.com ", city=" Hyderabad "
    )
    assert payload.name == "Test User"
    assert payload.email == "test@example.com"
    assert payload.city == "Hyderabad"


def test_pre_registration_rejects_invalid_mobile_and_email():
    with pytest.raises(ValidationError):
        CreatePreRegistrationRequest(mobile="1234567890", email="test@example.com")
    with pytest.raises(ValidationError):
        CreatePreRegistrationRequest(mobile="9876543210", email="not-an-email")


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_review_accepts_ratings_one_to_five(rating):
    assert CreateReviewRequest(rating=rating).rating == rating


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_review_rejects_out_of_range_ratings(rating):
    with pytest.raises(ValidationError):
        CreateReviewRequest(rating=rating)
