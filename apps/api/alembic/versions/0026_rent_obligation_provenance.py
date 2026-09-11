"""Backfill RentObligation's missing ProvenanceMixin columns —
architecture/05-commercial-domain.md §1, CLAUDE.md's own "full data
provenance on every important record" rule.

0019_rent_payments_arrears.py created `payment_transactions` with the
full provenance column set but `rent_obligations`, right next to it in
the same migration, never got them — a real gap, not a deliberate
choice (nothing about RentObligation makes provenance less relevant;
architecture §1's own "what is owed" is exactly the kind of record
this rule exists for). Surfaced while building the commercial CSV
importer (spec §78's "Import rent obligations"), which needs
source_dataset_id/import_job_id to record where an imported row came
from the same way every other importer does.

Added in three steps rather than one NOT NULL column, since a real
deployment could already have rows: nullable first, backfill existing
rows as MANUAL (accurate — every rent_obligation ever created so far
came from the manual "Add an obligation" form, not an import), then
enforce NOT NULL to match every sibling ProvenanceMixin table exactly
(no lingering server_default, same as `0005_properties.py`'s columns).

Revision ID: 0026_rent_obligation_provenance
Revises: 0025_ingestion_job_results
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_rent_obligation_provenance"
down_revision: Union[str, None] = "0025_ingestion_job_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rent_obligations",
        sa.Column(
            "source_type",
            sa.Enum(
                "MANUAL", "FILE_UPLOAD", "API", "SCHEDULED_IMPORT", "INTEGRATION", "SYSTEM_GENERATED",
                name="sourcetype",
            ),
            nullable=True,
        ),
    )
    op.execute("UPDATE rent_obligations SET source_type = 'MANUAL' WHERE source_type IS NULL")
    op.alter_column("rent_obligations", "source_type", nullable=False)

    op.add_column("rent_obligations", sa.Column("source_system", sa.String(128), nullable=True))
    op.add_column(
        "rent_obligations",
        sa.Column("source_dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=True),
    )
    op.add_column(
        "rent_obligations",
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_jobs.id"), nullable=True),
    )
    op.add_column("rent_obligations", sa.Column("original_reference", sa.String(255), nullable=True))
    op.add_column(
        "rent_obligations",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "rent_obligations", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    op.add_column(
        "rent_obligations",
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "rent_obligations", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now())
    )


def downgrade() -> None:
    op.drop_column("rent_obligations", "updated_at")
    op.drop_column("rent_obligations", "updated_by")
    op.drop_column("rent_obligations", "created_at")
    op.drop_column("rent_obligations", "created_by")
    op.drop_column("rent_obligations", "original_reference")
    op.drop_column("rent_obligations", "import_job_id")
    op.drop_column("rent_obligations", "source_dataset_id")
    op.drop_column("rent_obligations", "source_system")
    op.drop_column("rent_obligations", "source_type")
