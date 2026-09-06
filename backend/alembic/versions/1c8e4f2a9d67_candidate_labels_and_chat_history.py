"""candidate market_type + ai_explanation, chat_messages table

Adds spot/futures labeling and cached plain-language explanations to
market_candidates (app/services/candidate_explainer.py), and a chat_messages
table so the Copilot page has persistent history
(app/api/routes/agent_chat.py).

Revision ID: 1c8e4f2a9d67
Revises: 9f3a7c2e1b44
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1c8e4f2a9d67"
down_revision: Union[str, None] = "9f3a7c2e1b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "market_candidates",
        sa.Column("market_type", sa.String(), nullable=False, server_default="spot"),
    )
    op.add_column(
        "market_candidates",
        sa.Column("ai_explanation", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_market_candidates_created_at", "market_candidates", ["created_at"], unique=False
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_used", sa.String(), nullable=True),
        sa.Column("tool_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"], unique=False)
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_user_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_market_candidates_created_at", table_name="market_candidates")
    op.drop_column("market_candidates", "ai_explanation")
    op.drop_column("market_candidates", "market_type")
