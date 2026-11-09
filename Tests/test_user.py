
from datetime import datetime, timedelta, timezone

from core.database import SessionLocal
from models.User import User
from Repositories.UserRepository import UserRepository
from Management.UserManagement import UserManagement


database = SessionLocal()

try:
    repository = UserRepository(database)
    management = UserManagement(repository, otp_management=None)

    test_mobile = "9123456789"

    # Ensure this number is reserved for this test.
    existing = repository.get_by_mobile_number(test_mobile)
    if existing is not None:
        raise RuntimeError(
            "Test number already exists. Choose another test number."
        )

    # Create a dedicated test user.
    test_user = User(
        mobile_number=test_mobile,
        is_deletion_requested=True,
        deletion_requested_at=(
            datetime.now(timezone.utc) - timedelta(days=31)
        ),
    )
    test_user = repository.save(test_user)
    test_user_id = test_user.id

    deleted_count = management.permanently_delete_expired_accounts()
    print("Expired accounts deleted:", deleted_count)

    remaining_user = repository.get_by_id(test_user_id)
    print("Expired test user removed:", remaining_user is None)

finally:
    database.close()
