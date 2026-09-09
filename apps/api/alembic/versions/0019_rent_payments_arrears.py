"""Rent obligations, payment transactions, payment allocations —
architecture/05-commercial-domain.md §1-3.

Revision ID: 0019_rent_payments_arrears
Revises: 0018_tenancies
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_rent_payments_arrears"
down_revision: Union[str, None] = "0018_tenancies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table_name} ON {table_name}
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def _provenance_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "source_type",
            sa.Enum(
                "MANUAL", "FILE_UPLOAD", "API", "SCHEDULED_IMPORT", "INTEGRATION", "SYSTEM_GENERATED",
                name="sourcetype",
            ),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(128), nullable=True),
        sa.Column("source_dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_jobs.id"), nullable=True),
        sa.Column("original_reference", sa.String(255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "rent_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leases.id"), nullable=False),
        sa.Column(
            "obligation_type",
            sa.Enum("RENT", "SERVICE_CHARGE", "INSURANCE_RECHARGE", "UTILITY_RECHARGE", "OTHER", name="obligationtype"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("amount_due_pence", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("invoice_reference", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("ACTIVE", "CANCELLED", name="rentobligationstatus"), nullable=False),
    )
    op.create_index("ix_rent_obligations_organisation_id", "rent_obligations", ["organisation_id"])
    op.create_index("ix_rent_obligations_lease_id", "rent_obligations", ["lease_id"])
    _tenant_rls("rent_obligations")

    op.create_table(
        "payment_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leases.id"), nullable=True),
        sa.Column("amount_pence", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("received_date", sa.Date, nullable=False),
        sa.Column("payer_reference", sa.String(255), nullable=True),
        sa.Column("method", sa.String(64), nullable=True),
        *_provenance_columns(),
    )
    op.create_index("ix_payment_transactions_organisation_id", "payment_transactions", ["organisation_id"])
    op.create_index("ix_payment_transactions_lease_id", "payment_transactions", ["lease_id"])
    _tenant_rls("payment_transactions")

    op.create_table(
        "payment_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("payment_transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_transactions.id"), nullable=False),
        sa.Column("rent_obligation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rent_obligations.id"), nullable=True),
        sa.Column("amount_allocated_pence", sa.Integer, nullable=False),
        sa.Column(
            "allocation_status",
            sa.Enum("MATCHED", "POSSIBLE_MATCH", "UNALLOCATED", "NEEDS_REVIEW", name="allocationstatus"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "MANUAL", "FILE_UPLOAD", "API", "SCHEDULED_IMPORT", "INTEGRATION", "SYSTEM_GENERATED",
                name="sourcetype",
            ),
            nullable=False,
        ),
    )
    op.create_index("ix_payment_allocations_organisation_id", "payment_allocations", ["organisation_id"])
    op.create_index("ix_payment_allocations_payment_transaction_id", "payment_allocations", ["payment_transaction_id"])
    op.create_index("ix_payment_allocations_rent_obligation_id", "payment_allocations", ["rent_obligation_id"])
    _tenant_rls("payment_allocations")

    op.create_table(
        "payment_reconciliation_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("due_date_window_days", sa.Integer, nullable=False, server_default="14"),
        sa.UniqueConstraint("organisation_id", name="uq_payment_reconciliation_config_org"),
    )
    op.create_index("ix_payment_reconciliation_configs_organisation_id", "payment_reconciliation_configs", ["organisation_id"])
    _tenant_rls("payment_reconciliation_configs")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_payment_reconciliation_configs ON payment_reconciliation_configs")
    op.drop_table("payment_reconciliation_configs")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_payment_allocations ON payment_allocations")
    op.drop_table("payment_allocations")
    op.execute("DROP TYPE IF EXISTS allocationstatus")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_payment_transactions ON payment_transactions")
    op.drop_table("payment_transactions")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_rent_obligations ON rent_obligations")
    op.drop_table("rent_obligations")
    op.execute("DROP TYPE IF EXISTS rentobligationstatus")
    op.execute("DROP TYPE IF EXISTS obligationtype")
