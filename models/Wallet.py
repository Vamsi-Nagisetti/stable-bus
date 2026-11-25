import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WalletLot(Base):
    """A batch of coins that share one expiry date (Jan 1 after earning)."""

    __tablename__ = "wallet_lots"

    __table_args__ = (
        UniqueConstraint("lot_key", name="uq_wallet_lots_lot_key"),
        Index("ix_wallet_lots_user_expiry", "user_id", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Idempotency key, e.g. "earn:<booking_id>"
    lot_key: Mapped[str] = mapped_column(String(150), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    coins_total: Mapped[int] = mapped_column(Integer, nullable=False)
    coins_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    # ACTIVE / EXHAUSTED / EXPIRED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class WalletTransaction(Base):
    """Append-only ledger. coins > 0 adds to the wallet, coins < 0 removes."""

    __tablename__ = "wallet_transactions"

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_wallet_tx_idempotency_key"),
        Index("ix_wallet_tx_user_created", "user_id", "created_at"),
        Index("ix_wallet_tx_payment", "payment_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # EARN / REDEEM / REVERSE / EXPIRE / ADJUST / RESTORE
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    coins: Mapped[int] = mapped_column(Integer, nullable=False)
    lot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("wallet_lots.id"), nullable=True
    )
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
