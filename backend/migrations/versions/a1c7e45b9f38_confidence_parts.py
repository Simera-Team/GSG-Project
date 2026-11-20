"""Confidence parts, the model's own number, and the rejected list

A field's confidence used to be whatever the language model reported about its
own answer. That number is not evidence: a model reports the same certainty
for a value copied off the page and one it invented. Confidence is now
computed in code as

    base x evidence x validation x mapping

so these columns store the parts the product came from. Without them a stored
0.68 is an opinion; with them it is "a 0.80 scan, quoted almost exactly", and
anyone can check the arithmetic months later (FR-035, FR-048, NFR-023). A
cross-source agreement (M-04) is added rather than multiplied and appears as
an extra `agreement` key, so `product + agreement` is always the stored value.

`model_confidence` keeps the model's own number next to the computed one, so
the two can be compared later. Nothing reads it.

`processing_attempt.rejected` holds the values an R- rule dropped — a snippet
that was not in the source text (R-03). Those never become field records and
never become review items, because a value that is not in the document is not
a judgement call; but "the model claimed this and we threw it away" is exactly
what someone investigating a bad profile needs to see, so it is stored with
the attempt that read it (NFR-028). It is personal data, which is why it lives
here and never in an application log.

Existing rows keep NULL in all three: a confidence written under the old model
cannot be decomposed after the fact, and claiming parts for it would be
inventing them. A NULL simply says "scored before this change".

Revision ID: a1c7e45b9f38
Revises: 8d3f52b7c641
Create Date: 2026-11-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1c7e45b9f38'
down_revision: Union[str, Sequence[str], None] = '8d3f52b7c641'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('extracted_field',
                  sa.Column('confidence_parts', postgresql.JSONB(), nullable=True))
    op.add_column('extracted_field',
                  sa.Column('model_confidence', sa.REAL(), nullable=True))
    op.create_check_constraint(
        'ck_field_model_confidence', 'extracted_field',
        'model_confidence IS NULL OR model_confidence BETWEEN 0 AND 1')

    op.add_column('processing_attempt',
                  sa.Column('rejected', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('processing_attempt', 'rejected')
    op.drop_constraint('ck_field_model_confidence', 'extracted_field', type_='check')
    op.drop_column('extracted_field', 'model_confidence')
    op.drop_column('extracted_field', 'confidence_parts')
