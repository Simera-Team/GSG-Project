"""Source kind, stored separately from file format (FR-053)

`file_type` is the file's format (pdf, docx, md, json). FR-053 asks for the
*kind* of source (CV, LinkedIn, vetting) as its own field, because the two are
not the same thing: a CV arrives as either pdf or docx, and a format alone
cannot say whether a json file is a vetting result or something else.

The kind is what the conflict rules read to prefer a vetted value over a
self-reported one (FR-032) and to break a tie by source priority, so without
this column those rules have nothing to work from.

Existing rows are backfilled from their format using the FR-054 mapping
(pdf/docx -> cv, md -> linkedin, json -> vetting), which is the only kind each
of those formats was accepted as until now.

Revision ID: 7a4c91e8d205
Revises: 4e2b8d6f1a73
Create Date: 2026-11-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7a4c91e8d205'
down_revision: Union[str, Sequence[str], None] = '4e2b8d6f1a73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_KINDS = ('cv', 'linkedin', 'vetting')


def upgrade() -> None:
    source_kind = sa.Enum(*SOURCE_KINDS, name='source_kind')
    source_kind.create(op.get_bind(), checkfirst=True)

    # Added nullable, backfilled, then made NOT NULL, so the migration works on
    # a table that already holds rows.
    op.add_column('source_file', sa.Column('source_kind', source_kind, nullable=True))
    op.execute("""
        UPDATE source_file
           SET source_kind = CASE file_type
                                 WHEN 'md'   THEN 'cv'
                                 WHEN 'json' THEN 'vetting'
                                 ELSE 'cv'
                             END::source_kind
         WHERE source_kind IS NULL
    """)
    # LinkedIn exports are the only markdown source accepted so far (FR-006).
    op.execute("UPDATE source_file SET source_kind = 'linkedin' WHERE file_type = 'md'")
    op.alter_column('source_file', 'source_kind', nullable=False)

    op.create_index('ix_source_file_source_kind', 'source_file', ['source_kind'])


def downgrade() -> None:
    op.drop_index('ix_source_file_source_kind', table_name='source_file')
    op.drop_column('source_file', 'source_kind')
    sa.Enum(name='source_kind').drop(op.get_bind(), checkfirst=True)
