"""CV processing tables: skills, profile records, field records, attempts, review queue, vetting

Adds every table the CV processing pipeline writes to. Compared with the
original design in sql/cverge_schema.sql it also:
- adds processing_attempt (FR-058) - one insert-only row per LLM try
- adds entity, raw_value, evidence, page, evidence/review status and the
  producing attempt to extracted_field (FR-035, FR-060, FR-065)
- adds field_ids to every profile child table (FR-063)
- stores dates as 'YYYY' / 'YYYY-MM' text instead of DATE, so no day is
  ever invented (FR-028)
- adds employment_status and location to work_experience (FR-028, FR-004)
- makes review_item.field_name nullable and adds entity, reasons, message,
  so a failed job can be queued without a field (FR-042)
- adds evidence, page and field_id to review_option (FR-043)
- adds verified / source_file_ids to profile_skill and the vetting_record
  table (FR-056, FR-057)
- seeds the country, skill and skill_alias lists

Revision ID: 5f8a2c41d9e7
Revises: 1b322870ccb9
Create Date: 2026-11-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '5f8a2c41d9e7'
down_revision: Union[str, Sequence[str], None] = '1b322870ccb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PARTIAL_DATE = r"^\d{4}(-(0[1-9]|1[0-2]))?$"

link_type = postgresql.ENUM('linkedin', 'github', 'portfolio', 'website', 'other',
                            name='link_type', create_type=False)
attempt_trigger = postgresql.ENUM('first_run', 'auto_retry', 'admin_rerun',
                                  name='attempt_trigger', create_type=False)
attempt_outcome = postgresql.ENUM('valid', 'invalid', 'error',
                                  name='attempt_outcome', create_type=False)

INT_ARRAY = postgresql.ARRAY(sa.Integer())


def _profile_fk():
    return sa.Column('profile_id', sa.Integer(),
                     sa.ForeignKey('profile.profile_id', ondelete='CASCADE'), nullable=False)


def _field_ids():
    return sa.Column('field_ids', INT_ARRAY, server_default='{}', nullable=False)


def _date_check(table, column):
    return sa.CheckConstraint(f"{column} ~ '{PARTIAL_DATE}'", name=f'ck_{table}_{column}')


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (link_type, attempt_trigger, attempt_outcome):
        enum.create(bind, checkfirst=True)

    # ---------- lookup tables ----------
    op.create_table(
        'skill',
        sa.Column('skill_id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('canonical_name', sa.String(100), nullable=False, unique=True),
    )
    op.create_table(
        'skill_alias',
        sa.Column('alias_id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('skill_id', sa.Integer(),
                  sa.ForeignKey('skill.skill_id', ondelete='CASCADE'), nullable=False),
        sa.Column('alias_name', sa.String(100), nullable=False, unique=True),
    )

    # ---------- processing audit trail ----------
    op.create_table(
        'processing_attempt',
        sa.Column('attempt_id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('file_id', sa.Integer(),
                  sa.ForeignKey('source_file.file_id', ondelete='CASCADE'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('trigger', attempt_trigger, nullable=False),
        sa.Column('outcome', attempt_outcome, nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('llm_response', sa.Text()),
        sa.Column('validation_result', postgresql.JSONB()),
        sa.Column('error_message', sa.Text()),
        sa.Column('confidence_threshold', sa.REAL()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('file_id', 'attempt_number', name='uq_attempt_file_number'),
        sa.CheckConstraint('confidence_threshold BETWEEN 0 AND 1', name='ck_attempt_threshold'),
    )
    op.create_index('ix_processing_attempt_file_id', 'processing_attempt', ['file_id'])

    op.create_table(
        'extracted_field',
        sa.Column('field_id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('file_id', sa.Integer(),
                  sa.ForeignKey('source_file.file_id', ondelete='CASCADE'), nullable=False),
        sa.Column('attempt_id', sa.Integer(),
                  sa.ForeignKey('processing_attempt.attempt_id', ondelete='CASCADE')),
        sa.Column('entity', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('raw_value', postgresql.JSONB()),
        sa.Column('value', postgresql.JSONB()),
        sa.Column('confidence', sa.REAL()),
        sa.Column('evidence', sa.Text()),
        sa.Column('page', sa.Integer()),
        sa.Column('evidence_status', sa.String(20), nullable=False),
        sa.Column('rule', sa.String(100)),
        sa.Column('review_status', sa.String(20), server_default='accepted', nullable=False),
        sa.Column('review_reasons', postgresql.ARRAY(sa.String(50)),
                  server_default='{}', nullable=False),
        sa.Column('is_winner', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.CheckConstraint('confidence BETWEEN 0 AND 1', name='ck_field_confidence'),
        sa.CheckConstraint('page IS NULL OR page >= 1', name='ck_field_page'),
        sa.CheckConstraint("review_status IN ('accepted', 'needs_review')",
                           name='ck_field_review_status'),
    )
    op.create_index('ix_extracted_field_attempt_id', 'extracted_field', ['attempt_id'])
    op.create_index('ix_extracted_field_file_field', 'extracted_field', ['file_id', 'field_name'])

    # ---------- profile child records ----------
    op.create_table(
        'profile_skill',
        sa.Column('profile_id', sa.Integer(),
                  sa.ForeignKey('profile.profile_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('skill_id', sa.Integer(), sa.ForeignKey('skill.skill_id'), primary_key=True),
        sa.Column('level', sa.Integer()),
        sa.Column('confidence', sa.REAL()),
        sa.Column('verified', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('source_file_ids', INT_ARRAY, server_default='{}', nullable=False),
        _field_ids(),
        sa.CheckConstraint('level BETWEEN 1 AND 5', name='ck_profile_skill_level'),
        sa.CheckConstraint('confidence BETWEEN 0 AND 1', name='ck_profile_skill_confidence'),
    )

    op.create_table(
        'work_experience',
        sa.Column('exp_id', sa.Integer(), autoincrement=True, primary_key=True),
        _profile_fk(),
        sa.Column('company', sa.String(255)),
        sa.Column('title', sa.String(255)),
        sa.Column('location', sa.String(255)),
        sa.Column('start_date', sa.String(7)),
        sa.Column('end_date', sa.String(7)),
        sa.Column('employment_status', sa.String(10), server_default='unknown', nullable=False),
        sa.Column('description', sa.Text()),
        _field_ids(),
        _date_check('work_experience', 'start_date'),
        _date_check('work_experience', 'end_date'),
        sa.CheckConstraint("employment_status IN ('current', 'ended', 'unknown')",
                           name='ck_work_experience_status'),
    )

    op.create_table(
        'education',
        sa.Column('edu_id', sa.Integer(), autoincrement=True, primary_key=True),
        _profile_fk(),
        sa.Column('institution', sa.String(255)),
        sa.Column('degree', sa.String(255)),
        sa.Column('field', sa.String(255)),
        sa.Column('start_date', sa.String(7)),
        sa.Column('end_date', sa.String(7)),
        _field_ids(),
        _date_check('education', 'start_date'),
        _date_check('education', 'end_date'),
    )

    op.create_table(
        'certification',
        sa.Column('cert_id', sa.Integer(), autoincrement=True, primary_key=True),
        _profile_fk(),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('issuer', sa.String(255)),
        sa.Column('issue_date', sa.String(7)),
        sa.Column('url', sa.Text()),
        _field_ids(),
        _date_check('certification', 'issue_date'),
    )

    op.create_table(
        'project',
        sa.Column('project_id', sa.Integer(), autoincrement=True, primary_key=True),
        _profile_fk(),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('url', sa.Text()),
        sa.Column('tech_stack', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        _field_ids(),
    )

    op.create_table(
        'language',
        sa.Column('language_id', sa.Integer(), autoincrement=True, primary_key=True),
        _profile_fk(),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('proficiency', sa.String(30)),
        _field_ids(),
        sa.UniqueConstraint('profile_id', 'name', name='uq_language_profile_name'),
        sa.CheckConstraint("proficiency IN ('native', 'fluent', 'intermediate', 'basic')",
                           name='ck_language_proficiency'),
    )

    op.create_table(
        'profile_link',
        sa.Column('link_id', sa.Integer(), autoincrement=True, primary_key=True),
        _profile_fk(),
        sa.Column('type', link_type, nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        _field_ids(),
        sa.UniqueConstraint('profile_id', 'url', name='uq_profile_link_url'),
    )

    for table in ('work_experience', 'education', 'certification', 'project',
                  'language', 'profile_link'):
        op.create_index(f'ix_{table}_profile_id', table, ['profile_id'])

    # ---------- human review queue ----------
    op.create_table(
        'review_item',
        sa.Column('review_id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('profile_id', sa.Integer(),
                  sa.ForeignKey('profile.profile_id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_id', sa.Integer(),
                  sa.ForeignKey('source_file.file_id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity', sa.String(100)),
        sa.Column('field_name', sa.String(100)),          # NULL for a failed job (FR-042)
        sa.Column('reasons', postgresql.ARRAY(sa.String(50)), server_default='{}', nullable=False),
        sa.Column('message', sa.Text()),
        sa.Column('assigned_to_candidate', sa.Boolean(), server_default='false'),
        sa.Column('sent_to_candidate_at', sa.DateTime()),
        sa.Column('resolved', sa.Boolean(), server_default='false'),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('app_user.user_id')),
        sa.Column('resolved_value', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime()),
    )
    op.create_index('ix_review_item_file_id', 'review_item', ['file_id'])
    op.create_index('ix_review_item_resolved', 'review_item', ['resolved'])

    op.create_table(
        'review_option',
        sa.Column('option_id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('review_id', sa.Integer(),
                  sa.ForeignKey('review_item.review_id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_id', sa.Integer(),
                  sa.ForeignKey('source_file.file_id', ondelete='CASCADE'), nullable=False),
        sa.Column('field_id', sa.Integer(),
                  sa.ForeignKey('extracted_field.field_id', ondelete='SET NULL')),
        sa.Column('value', sa.Text()),
        sa.Column('confidence', sa.REAL()),
        sa.Column('evidence', sa.Text()),
        sa.Column('page', sa.Integer()),
        sa.CheckConstraint('confidence BETWEEN 0 AND 1', name='ck_option_confidence'),
    )
    op.create_index('ix_review_option_review_id', 'review_option', ['review_id'])
    op.create_index('ix_review_option_file_id', 'review_option', ['file_id'])

    # ---------- vetting (parser waits for flag 7) ----------
    op.create_table(
        'vetting_record',
        sa.Column('vetting_id', sa.Integer(), autoincrement=True, primary_key=True),
        _profile_fk(),
        sa.Column('skill_id', sa.Integer(), sa.ForeignKey('skill.skill_id'), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(),
                  sa.ForeignKey('source_file.file_id', ondelete='CASCADE'), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('app_user.user_id'), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('level BETWEEN 1 AND 5', name='ck_vetting_level'),
    )
    op.create_index('ix_vetting_record_profile_id', 'vetting_record', ['profile_id'])

    # ---------- seed data (same lists as sql/cverge_schema.sql) ----------
    op.execute("""
        INSERT INTO country (country_name, country_code) VALUES
          ('Jordan', 'JO'), ('Palestine', 'PS'), ('United Arab Emirates', 'AE'),
          ('Saudi Arabia', 'SA'), ('Egypt', 'EG'), ('United States', 'US'),
          ('United Kingdom', 'GB'), ('Germany', 'DE')
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO skill (canonical_name) VALUES
          ('React'), ('Node.js'), ('Python'), ('JavaScript'), ('TypeScript'),
          ('PostgreSQL'), ('MySQL'), ('Docker'), ('Java'), ('C#'), ('Git')
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO skill_alias (skill_id, alias_name)
        SELECT s.skill_id, a.alias FROM (VALUES
          ('React', 'reactjs'), ('React', 'react.js'), ('Node.js', 'node'),
          ('Node.js', 'nodejs'), ('JavaScript', 'js'), ('TypeScript', 'ts'),
          ('PostgreSQL', 'postgres'), ('PostgreSQL', 'psql'), ('MySQL', 'mysql8')
        ) AS a(skill, alias)
        JOIN skill s ON s.canonical_name = a.skill
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    for table in ('vetting_record', 'review_option', 'review_item', 'profile_link',
                  'language', 'project', 'certification', 'education', 'work_experience',
                  'profile_skill', 'extracted_field', 'processing_attempt',
                  'skill_alias', 'skill'):
        op.drop_table(table)
    op.execute("DELETE FROM country WHERE country_code IN "
               "('JO', 'PS', 'AE', 'SA', 'EG', 'US', 'GB', 'DE') "
               "AND country_id NOT IN (SELECT country_id FROM profile WHERE country_id IS NOT NULL)")

    bind = op.get_bind()
    for enum in (attempt_outcome, attempt_trigger, link_type):
        enum.drop(bind, checkfirst=True)
