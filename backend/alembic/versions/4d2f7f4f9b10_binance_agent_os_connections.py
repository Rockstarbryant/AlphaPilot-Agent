"""add Binance Agent OS MCP connections

Revision ID: 4d2f7f4f9b10
Revises: bca656ef4882
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "4d2f7f4f9b10"
down_revision: Union[str, None] = "bca656ef4882"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "binance_connections",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.Enum("pending", "connected", "revoked", "error", name="binanceconnectionstatus"), nullable=False),
        sa.Column("client_id", sa.String(), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_endpoint", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.Integer(), nullable=True),
        sa.Column("oauth_state", sa.String(), nullable=True),
        sa.Column("code_verifier_encrypted", sa.Text(), nullable=True),
        sa.Column("redirect_uri", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_binance_connections_user_id", "binance_connections", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_binance_connections_user_id", table_name="binance_connections")
    op.drop_table("binance_connections")
    op.execute("DROP TYPE IF EXISTS binanceconnectionstatus")
