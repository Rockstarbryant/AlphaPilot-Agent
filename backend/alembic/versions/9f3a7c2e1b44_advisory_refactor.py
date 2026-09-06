"""advisory refactor: drop binance oauth connections, account snapshot raw payload

Binance's agent allowlist only covers Claude Desktop/Code, ChatGPT, Codex,
VS Code, and Grok Bot — not self-built backends like AlphaPilot's. This
drops the now-unusable binance_connections OAuth table (AlphaPilot never
completes that OAuth flow) and adds a raw_snapshot column to
account_snapshots so a client-reported balance/position payload can be
stored in full, not just the four aggregate numbers already captured.
See BINANCE_AGENT_OS_REFACTOR.md and docs/ADVISORY_REFACTOR.md.

Revision ID: 9f3a7c2e1b44
Revises: f1a2b3c4d5e6
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f3a7c2e1b44"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_snapshots",
        sa.Column("raw_snapshot", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.drop_table("binance_connections")

    # StrategyType gains 'user_requested' for chat-driven ad-hoc analysis
    # (not a scheduled scan). Postgres enums require ALTER TYPE; SQLite (used
    # in tests) has no native enum constraint to update.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE strategytype ADD VALUE IF NOT EXISTS 'user_requested'")


def downgrade() -> None:
    op.create_table(
        "binance_connections",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
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
    op.drop_column("account_snapshots", "raw_snapshot")
