"""Standard skill list: 89 more skills and 67 aliases (FR-029)

The first seed had 11 programming skills, so almost every skill in a real CV
(Power BI, Excel, Adobe Premiere, Communication...) went to review. This adds
a broad standard list - programming, data, cloud, office, design/media,
business and soft skills - and their common synonyms.

Spelling variants (Node JS / node.js, "Pandas (Software)") need no alias: they
match through the skill match key in app/domain/services/skills.py.
Rows that already exist are left alone (ON CONFLICT DO NOTHING), so skills an
administrator or reviewer added are kept.

Revision ID: 3c7f1a9e5b42
Revises: 9b1e6d3a7c20
Create Date: 2026-11-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3c7f1a9e5b42'
down_revision: Union[str, Sequence[str], None] = '9b1e6d3a7c20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of app/infrastructure/reference_data.py (ADDED_SKILLS / ADDED_SKILL_ALIASES).
SKILLS = [
    'C', 'C++', 'Go', 'PHP', 'Ruby', 'Kotlin',
    'Swift', 'R', 'SQL', 'HTML', 'CSS', 'Bash',
    'React Native', 'Angular', 'Vue.js', 'Next.js', 'Express', 'Django',
    'Flask', 'FastAPI', 'Spring Boot', '.NET', 'Laravel', 'MongoDB',
    'SQL Server', 'Oracle Database', 'Redis', 'Pandas', 'NumPy', 'scikit-learn',
    'TensorFlow', 'PyTorch', 'Power BI', 'Tableau', 'Microsoft Excel', 'DAX',
    'SPSS', 'Data Analysis', 'Data Engineering', 'Data Visualization', 'Machine Learning', 'Artificial Intelligence',
    'Deep Learning', 'Statistics', 'ETL', 'Kubernetes', 'GitHub', 'Linux',
    'AWS', 'Microsoft Azure', 'Google Cloud', 'CI/CD', 'REST APIs', 'Microsoft Office',
    'Microsoft Word', 'Microsoft PowerPoint', 'Microsoft Access', 'Google Analytics', 'Slack', 'Zoom',
    'Jira', 'Windows', 'macOS', 'Adobe Photoshop', 'Adobe Illustrator', 'Adobe Premiere Pro',
    'Adobe After Effects', 'Final Cut Pro', 'Avid Media Composer', 'Figma', 'Video Editing', 'Marketing',
    'Digital Marketing', 'Sales', 'Customer Service', 'Project Management', 'Agile', 'Scrum',
    'Public Relations', 'Fundraising', 'Communication', 'Teamwork', 'Leadership', 'Problem Solving',
    'Critical Thinking', 'Time Management', 'Conflict Resolution', 'Active Listening', 'Organization',
]

ALIASES = [
    ('golang', 'Go'),
    ('c plus plus', 'C++'),
    ('cpp', 'C++'),
    ('vue', 'Vue.js'),
    ('express.js', 'Express'),
    ('expressjs', 'Express'),
    ('dotnet', '.NET'),
    ('asp.net', '.NET'),
    ('html5', 'HTML'),
    ('css3', 'CSS'),
    ('shell scripting', 'Bash'),
    ('mongo', 'MongoDB'),
    ('mssql', 'SQL Server'),
    ('microsoft sql server', 'SQL Server'),
    ('oracle', 'Oracle Database'),
    ('sklearn', 'scikit-learn'),
    ('microsoft power bi', 'Power BI'),
    ('excel', 'Microsoft Excel'),
    ('ms excel', 'Microsoft Excel'),
    ('spss statistics', 'SPSS'),
    ('ibm spss', 'SPSS'),
    ('ibm spss statistics', 'SPSS'),
    ('data analytics', 'Data Analysis'),
    ('ml', 'Machine Learning'),
    ('ai', 'Artificial Intelligence'),
    ('dl', 'Deep Learning'),
    ('k8s', 'Kubernetes'),
    ('amazon web services', 'AWS'),
    ('azure', 'Microsoft Azure'),
    ('gcp', 'Google Cloud'),
    ('google cloud platform', 'Google Cloud'),
    ('rest', 'REST APIs'),
    ('rest api', 'REST APIs'),
    ('restful apis', 'REST APIs'),
    ('continuous integration', 'CI/CD'),
    ('ms office', 'Microsoft Office'),
    ('microsoft office suite', 'Microsoft Office'),
    ('office 365', 'Microsoft Office'),
    ('microsoft 365', 'Microsoft Office'),
    ('ms word', 'Microsoft Word'),
    ('powerpoint', 'Microsoft PowerPoint'),
    ('ms powerpoint', 'Microsoft PowerPoint'),
    ('ms access', 'Microsoft Access'),
    ('mac os', 'macOS'),
    ('mac os x', 'macOS'),
    ('os x', 'macOS'),
    ('osx', 'macOS'),
    ('microsoft windows', 'Windows'),
    ('photoshop', 'Adobe Photoshop'),
    ('illustrator', 'Adobe Illustrator'),
    ('premiere', 'Adobe Premiere Pro'),
    ('premiere pro', 'Adobe Premiere Pro'),
    ('adobe premiere', 'Adobe Premiere Pro'),
    ('after effects', 'Adobe After Effects'),
    ('final cut', 'Final Cut Pro'),
    ('fcp', 'Final Cut Pro'),
    ('avid', 'Avid Media Composer'),
    ('media composer', 'Avid Media Composer'),
    ('customer care', 'Customer Service'),
    ('pr', 'Public Relations'),
    ('team work', 'Teamwork'),
    ('team player', 'Teamwork'),
    ('team leadership', 'Leadership'),
    ('organisation', 'Organization'),
    ('organizational skills', 'Organization'),
    ('organisational skills', 'Organization'),
    ('time-management', 'Time Management'),
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
