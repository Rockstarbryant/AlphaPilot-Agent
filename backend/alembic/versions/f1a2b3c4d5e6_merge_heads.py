"""merge heads

Revision ID: f1a2b3c4d5e6
Revises: 7c2e9f1a5b33, b6e12205c17c
"""
from typing import Sequence, Union

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = ("7c2e9f1a5b33", "b6e12205c17c")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass