"""add target percentage to exit signals"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "7c2e9f1a5b33"
down_revision: Union[str, None] = "6a1d3b8e4c22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exit_signals", sa.Column("target_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("exit_signals", "target_pct")
