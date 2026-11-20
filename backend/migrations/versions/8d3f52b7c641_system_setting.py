"""System settings an administrator can change (FR-046, FR-067)

The confidence limit below which a field goes to review was an environment
variable, so changing it meant a redeploy and nothing recorded who changed it.
FR-067 asks for a stored setting with a default, keeping who changed it and
when; FR-046 asks the administrator to be able to set it.

The limit each job actually used is already stored on the job's attempts, so
raising or lowering it only affects later jobs and an old job stays
explainable.

Revision ID: 8d3f52b7c641
Revises: 7a4c91e8d205
Create Date: 2026-11-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8d3f52b7c641'
down_revision: Union[str, Sequence[str], None] = '7a4c91e8d205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Default review limit. A field the extraction is less sure of than this goes
#: to a person instead of into the live profile.
DEFAULT_CONFIDENCE_THRESHOLD = '0.65'


def upgrade() -> None:
    op.create_table(
        'system_setting',
        sa.Column('key', sa.String(length=64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        # FR-067: who changed it and when. Null means nobody has changed it
        # since the default was seeded.
        sa.Column('updated_by', sa.Integer(),
                  sa.ForeignKey('app_user.user_id', ondelete='SET NULL')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False,
                  server_default=sa.text('now()')),
    )

    op.execute(f"""
        INSERT INTO system_setting (key, value, description)
        VALUES ('review_confidence_threshold', '{DEFAULT_CONFIDENCE_THRESHOLD}',
                'Fields the extraction is less sure of than this go to review (FR-046)')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('system_setting')
