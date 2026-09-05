"""add direct Binance execution fields to exit signals"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "6a1d3b8e4c22"
down_revision: Union[str, None] = "4d2f7f4f9b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exit_signals", sa.Column("execution_status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("exit_signals", sa.Column("binance_order_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("exit_signals", "binance_order_id")
    op.drop_column("exit_signals", "execution_status")
