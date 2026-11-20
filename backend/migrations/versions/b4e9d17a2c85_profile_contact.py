"""Emails and phones as a table, not one column each (M-03)

A candidate has more than one email and more than one phone. The merge already
treats them that way: it unions them across every source, de-duplicates on the
normalised value and takes a primary from the newest source, so two addresses
are never a conflict and never a question to the candidate.

The database did not. `profile.email` and `profile.phone` are one column each,
so only the primary was reachable in SQL and the rest of the list existed only
inside `profile.final_json`. That made contacts the one piece of multi-valued
profile data that could not be queried or traced like the others: skills,
jobs, degrees, certificates, projects, languages and links all have a child
table carrying `field_ids`. It also meant a candidate could not be found by
their second address, which is exactly the address a recruiter is likely to
have.

`profile_contact` closes that gap, following `profile_link`: one row per value,
`field_ids` for the field records behind it (FR-063), and
`UNIQUE (profile_id, kind, value)` so the de-duplication the merge performs is
enforced where it cannot be forgotten.

`profile.email` and `profile.phone` stay, holding the primary. They are a
denormalisation, not a duplicate: the common read wants one address without a
join, the same way `profile.country_id` sits next to the country table.

Existing rows are backfilled from those two columns, so every profile that
already had an email keeps it as a primary contact row. Their `field_ids` are
left empty: the rows are rebuilt from the field records on the next run of any
of the candidate's files, and inventing a provenance here would be a lie. No
data is lost either way, since `final_json` already holds the full lists.

Revision ID: b4e9d17a2c85
Revises: b2d8e56a0f41
Create Date: 2026-11-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b4e9d17a2c85'
down_revision: Union[str, Sequence[str], None] = 'b2d8e56a0f41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTACT_KINDS = ('email', 'phone')

contact_kind = postgresql.ENUM(*CONTACT_KINDS, name='contact_kind', create_type=False)


def upgrade() -> None:
    contact_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'profile_contact',
        sa.Column('contact_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('kind', contact_kind, nullable=False),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('field_ids', postgresql.ARRAY(sa.Integer()), nullable=False,
                  server_default='{}'),
        sa.ForeignKeyConstraint(['profile_id'], ['profile.profile_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('contact_id'),
        sa.UniqueConstraint('profile_id', 'kind', 'value', name='uq_profile_contact_value'),
    )
    op.create_index('ix_profile_contact_profile_id', 'profile_contact', ['profile_id'])
    # The lookup this table exists to make possible: find a candidate by any
    # of their addresses, not only the one that happened to be primary.
    op.create_index('ix_profile_contact_value', 'profile_contact', ['kind', 'value'])

    # Backfill the primary each profile already had.
    op.execute("""
        INSERT INTO profile_contact (profile_id, kind, value, is_primary)
        SELECT profile_id, 'email'::contact_kind, email, true
          FROM profile
         WHERE email IS NOT NULL AND email <> ''
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO profile_contact (profile_id, kind, value, is_primary)
        SELECT profile_id, 'phone'::contact_kind, phone, true
          FROM profile
         WHERE phone IS NOT NULL AND phone <> ''
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Restore primary email and phone to profile if they became null/empty
    op.execute("""
        UPDATE profile p
           SET email = c.value
          FROM profile_contact c
         WHERE c.profile_id = p.profile_id
           AND c.kind = 'email'
           AND c.is_primary = true
           AND (p.email IS NULL OR p.email = '')
    """)
    op.execute("""
        UPDATE profile p
           SET phone = c.value
          FROM profile_contact c
         WHERE c.profile_id = p.profile_id
           AND c.kind = 'phone'
           AND c.is_primary = true
           AND (p.phone IS NULL OR p.phone = '')
    """)
    op.drop_index('ix_profile_contact_value', table_name='profile_contact')
    op.drop_index('ix_profile_contact_profile_id', table_name='profile_contact')
    op.drop_table('profile_contact')
    contact_kind.drop(op.get_bind(), checkfirst=True)
