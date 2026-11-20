"""More soft skills: 21 standard soft skills and 64 aliases (FR-029)

CVs write soft skills in many ways ("Extremely organised", "Excellent
communication skills", "Hard-working", "Works well under pressure"). This adds
the soft skills that were missing (Attention to Detail, Adaptability, Work
Ethic...) and the common phrasings of all soft skills as aliases.
A trailing "skills"/"abilities" needs no alias: the skill match key drops it.
Existing rows are kept (ON CONFLICT DO NOTHING).

Revision ID: 4e2b8d6f1a73
Revises: 3c7f1a9e5b42
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4e2b8d6f1a73'
down_revision: Union[str, Sequence[str], None] = '3c7f1a9e5b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of app/infrastructure/reference_data.py (MORE_SOFT_SKILLS / MORE_SOFT_SKILL_ALIASES).
SKILLS = [
    'Attention to Detail', 'Adaptability', 'Creativity', 'Decision Making',
    'Emotional Intelligence', 'Interpersonal Skills', 'Negotiation', 'Presentation Skills',
    'Multitasking', 'Work Ethic', 'Analytical Thinking', 'Strategic Thinking',
    'Self-Motivation', 'Working Under Pressure', 'Mentoring', 'Empathy',
    'Accountability', 'Initiative', 'Punctuality', 'Delegation',
    'Cultural Awareness',
]

ALIASES = [
    ('excellent communication', 'Communication'),
    ('strong communication', 'Communication'),
    ('effective communication', 'Communication'),
    ('good communication', 'Communication'),
    ('communicator', 'Communication'),
    ('collaboration', 'Teamwork'),
    ('collaborative', 'Teamwork'),
    ('teamwork and collaboration', 'Teamwork'),
    ('team working', 'Teamwork'),
    ('strong leadership', 'Leadership'),
    ('people management', 'Leadership'),
    ('problem solver', 'Problem Solving'),
    ('troubleshooting', 'Problem Solving'),
    ('critical thinker', 'Critical Thinking'),
    ('time management and organization', 'Time Management'),
    ('prioritization', 'Time Management'),
    ('prioritisation', 'Time Management'),
    ('conflict management', 'Conflict Resolution'),
    ('dispute resolution', 'Conflict Resolution'),
    ('listening', 'Active Listening'),
    ('organized', 'Organization'),
    ('organised', 'Organization'),
    ('well organized', 'Organization'),
    ('well organised', 'Organization'),
    ('highly organized', 'Organization'),
    ('highly organised', 'Organization'),
    ('extremely organized', 'Organization'),
    ('extremely organised', 'Organization'),
    ('detail oriented', 'Attention to Detail'),
    ('attention to details', 'Attention to Detail'),
    ('eye for detail', 'Attention to Detail'),
    ('flexibility', 'Adaptability'),
    ('flexible', 'Adaptability'),
    ('adaptable', 'Adaptability'),
    ('creative thinking', 'Creativity'),
    ('creative', 'Creativity'),
    ('decisive', 'Decision Making'),
    ('eq', 'Emotional Intelligence'),
    ('people skills', 'Interpersonal Skills'),
    ('relationship building', 'Interpersonal Skills'),
    ('negotiating', 'Negotiation'),
    ('public speaking', 'Presentation Skills'),
    ('presenting', 'Presentation Skills'),
    ('presentations', 'Presentation Skills'),
    ('multitasker', 'Multitasking'),
    ('strong work ethic', 'Work Ethic'),
    ('hard working', 'Work Ethic'),
    ('hardworking', 'Work Ethic'),
    ('analytical', 'Analytical Thinking'),
    ('analytical thinker', 'Analytical Thinking'),
    ('self motivated', 'Self-Motivation'),
    ('self starter', 'Self-Motivation'),
    ('ability to work under pressure', 'Working Under Pressure'),
    ('works well under pressure', 'Working Under Pressure'),
    ('performing under pressure', 'Working Under Pressure'),
    ('stress management', 'Working Under Pressure'),
    ('coaching', 'Mentoring'),
    ('mentorship', 'Mentoring'),
    ('punctual', 'Punctuality'),
    ('responsibility', 'Accountability'),
    ('proactive', 'Initiative'),
    ('proactivity', 'Initiative'),
    ('cultural sensitivity', 'Cultural Awareness'),
    ('cross cultural communication', 'Cultural Awareness'),
]


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("INSERT INTO skill (canonical_name) VALUES (:n) ON CONFLICT DO NOTHING"),
                 [{"n": n} for n in SKILLS])
    bind.execute(sa.text(
        "INSERT INTO skill_alias (skill_id, alias_name) "
        "SELECT skill_id, :a FROM skill WHERE canonical_name = :n "
        "ON CONFLICT DO NOTHING"),
        [{"a": a, "n": n} for a, n in ALIASES])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM skill_alias WHERE alias_name = ANY(:a)"),
                 {"a": [a for a, _ in ALIASES]})
    # Keep any skill already used in a profile or vetting record.
    bind.execute(sa.text(
        "DELETE FROM skill WHERE canonical_name = ANY(:n) "
        "AND skill_id NOT IN (SELECT skill_id FROM profile_skill) "
        "AND skill_id NOT IN (SELECT skill_id FROM vetting_record)"),
        {"n": SKILLS})
