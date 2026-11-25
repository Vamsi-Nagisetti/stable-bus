import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, UniqueConstraint

from core.database import Base


class PreRegisteredUser(Base):
    __tablename__ = "pre_registered_users"
    __table_args__ = (
        UniqueConstraint("mobile", name="uq_pre_registered_users_mobile"),
        UniqueConstraint("email", name="uq_pre_registered_users_email"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=True)
    mobile = Column(String(10), nullable=False)
    email = Column(String(254), nullable=False)
    city = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
