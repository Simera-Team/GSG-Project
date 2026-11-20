"""Review decisions and profile change history

- review_item: how it was resolved (FR-066) - which option was chosen, or that a
  custom value was typed, rejected or dismissed - and the field record the
  decision created
- profile_change_log table + trigger (FR-037), as designed in sql/cverge_schema.sql:
  every change to a profile column is logged with who made it and why

Revision ID: 9b1e6d3a7c20
Revises: 5f8a2c41d9e7
Create Date: 2026-11-13 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b1e6d3a7c20'
down_revision: Union[str, Sequence[str], None] = '5f8a2c41d9e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LOG_FUNCTION = """
CREATE OR REPLACE FUNCTION log_profile_changes() RETURNS TRIGGER AS $$
DECLARE
  k     TEXT;
  old_j JSONB := to_jsonb(OLD);
  new_j JSONB := to_jsonb(NEW);
  who   INT   := NULLIF(current_setting('app.current_user_id', true), '')::INT;
  why   TEXT  := NULLIF(current_setting('app.change_reason', true), '');
  src   INT   := NULLIF(current_setting('app.change_file_id', true), '')::INT;
BEGIN
  FOREACH k IN ARRAY ARRAY['first_name','last_name','email','phone',
                           'city','country_id','title','summary']
  LOOP
    IF old_j->>k IS DISTINCT FROM new_j->>k THEN
      INSERT INTO profile_change_log
        (profile_id, file_id, field_name, old_value, new_value, changed_by, reason)
      VALUES
        (NEW.profile_id, src, k, old_j->>k, new_j->>k, who, COALESCE(why, 'auto_merge'));
    END IF;
  END LOOP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.add_column('review_item', sa.Column('resolution', sa.String(20)))
    op.add_column('review_item', sa.Column(
        'resolved_option_id', sa.Integer(),
        sa.ForeignKey('review_option.option_id', ondelete='SET NULL')))
    op.add_column('review_item', sa.Column(
        'resolved_field_id', sa.Integer(),
        sa.ForeignKey('extracted_field.field_id', ondelete='SET NULL')))
    op.create_check_constraint(
        'ck_review_item_resolution', 'review_item',
        "resolution IN ('option', 'custom', 'rejected', 'dismissed')")

    op.create_table(
        'profile_change_log',
        sa.Column('change_id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('profile_id', sa.Integer(),
                  sa.ForeignKey('profile.profile_id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_id', sa.Integer(),
                  sa.ForeignKey('source_file.file_id', ondelete='SET NULL')),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('old_value', sa.Text()),
        sa.Column('new_value', sa.Text()),
        sa.Column('changed_by', sa.Integer(), sa.ForeignKey('app_user.user_id')),
        sa.Column('reason', sa.String(100)),        # auto_merge | review_decision | manual_edit
        sa.Column('changed_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index('ix_profile_change_log_profile', 'profile_change_log',
                    ['profile_id', 'changed_at'])

    op.execute(LOG_FUNCTION)
    op.execute("DROP TRIGGER IF EXISTS trg_profile_log ON profile")
    op.execute("CREATE TRIGGER trg_profile_log AFTER UPDATE ON profile "
               "FOR EACH ROW EXECUTE FUNCTION log_profile_changes()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_profile_log ON profile")
    op.execute("DROP FUNCTION IF EXISTS log_profile_changes()")
    op.drop_table('profile_change_log')
    op.drop_constraint('ck_review_item_resolution', 'review_item', type_='check')
    op.drop_column('review_item', 'resolved_field_id')
    op.drop_column('review_item', 'resolved_option_id')
    op.drop_column('review_item', 'resolution')
