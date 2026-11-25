"""add wallet (coins) tables and payment coin columns

Revision ID: a7c1d2e9f001
Revises: 6e5e3616eae5
Create Date: 2026-11-25 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c1d2e9f001'
down_revision: Union[str, Sequence[str], None] = '6e5e3616eae5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wallet_lots',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('lot_key', sa.String(length=150), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('booking_id', sa.String(length=36), nullable=True),
        sa.Column('coins_total', sa.Integer(), nullable=False),
        sa.Column('coins_remaining', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('earned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lot_key', name='uq_wallet_lots_lot_key'),
    )
    op.create_index(
        'ix_wallet_lots_user_expiry', 'wallet_lots',
        ['user_id', 'status', 'expires_at'], unique=False,
    )

    op.create_table(
        'wallet_transactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('coins', sa.Integer(), nullable=False),
        sa.Column('lot_id', sa.String(length=36), nullable=True),
        sa.Column('booking_id', sa.String(length=36), nullable=True),
        sa.Column('payment_id', sa.String(length=36), nullable=True),
        sa.Column('idempotency_key', sa.String(length=200), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lot_id'], ['wallet_lots.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_wallet_tx_idempotency_key'),
    )
    op.create_index(
        'ix_wallet_tx_user_created', 'wallet_transactions',
        ['user_id', 'created_at'], unique=False,
    )
    op.create_index(
        'ix_wallet_tx_payment', 'wallet_transactions',
        ['payment_id'], unique=False,
    )

    op.add_column('payments', sa.Column(
        'coins_used', sa.Integer(), server_default='0', nullable=False))
    op.add_column('payments', sa.Column(
        'coin_value', sa.Numeric(12, 2), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('payments', 'coin_value')
    op.drop_column('payments', 'coins_used')
    op.drop_index('ix_wallet_tx_payment', table_name='wallet_transactions')
    op.drop_index('ix_wallet_tx_user_created', table_name='wallet_transactions')
    op.drop_table('wallet_transactions')
    op.drop_index('ix_wallet_lots_user_expiry', table_name='wallet_lots')
    op.drop_table('wallet_lots')
