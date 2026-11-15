"""Add rejected status and source_file rule column (R-11)

Only English sources are accepted. Sources in other languages are rejected
(status 'rejected') with rule 'R-11' and a candidate-facing message.

Revision ID: b2d8e56a0f41
Revises: a1c7e45b9f38
Create Date: 2026-11-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d8e56a0f41'
down_revision: Union[str, Sequence[str], None] = 'a1c7e45b9f38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add rule column to source_file
    op.add_column('source_file', sa.Column('rule', sa.String(length=20), nullable=True))

    # 2. Add 'rejected' to file_status enum if using postgresql
    bind = op.get_bind()
    if bind.engine.name == 'postgresql':
        op.execute("ALTER TYPE file_status ADD VALUE IF NOT EXISTS 'rejected'")


def downgrade() -> None:
    op.drop_column('source_file', 'rule')
