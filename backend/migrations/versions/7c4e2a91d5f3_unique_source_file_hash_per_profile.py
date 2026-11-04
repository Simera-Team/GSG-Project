"""Make source_file hash unique per profile

Revision ID: 7c4e2a91d5f3
Revises: 1b322870ccb9
Create Date: 2026-11-04 12:00:00.000000

FR-011 / FR-055: the SHA-256 hash of a source is unique per candidate,
not system-wide. Two different candidates may upload the same file.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7c4e2a91d5f3'
down_revision: Union[str, Sequence[str], None] = '1b322870ccb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        'uq_source_file_profile_hash',
        'source_file',
        ['profile_id', 'file_hash']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'uq_source_file_profile_hash',
        'source_file',
        type_='unique'
    )
