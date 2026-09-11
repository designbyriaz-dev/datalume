"""Ingestion IMPORT job results — app/ingestion/models.py ImportJob.

Moving the IMPORT step to the background worker (spec §72's "tens of
thousands of properties" performance requirement) means the request
that triggers it returns before the work is done, so the result
(previously the synchronous response body's ImportResultOut) has to be
persisted on the job row instead, for a client to poll for via
GET /datasets/{id}.

Revision ID: 0025_ingestion_job_results
Revises: 0024_attention_signal_race
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_ingestion_job_results"
down_revision: Union[str, None] = "0024_attention_signal_race"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("rows_processed", sa.Integer(), nullable=True))
    op.add_column("import_jobs", sa.Column("entities_created", sa.Integer(), nullable=True))
    op.add_column("import_jobs", sa.Column("rows_failed", sa.Integer(), nullable=True))
    op.add_column("import_jobs", sa.Column("importer_registered", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("import_jobs", "importer_registered")
    op.drop_column("import_jobs", "rows_failed")
    op.drop_column("import_jobs", "entities_created")
    op.drop_column("import_jobs", "rows_processed")
