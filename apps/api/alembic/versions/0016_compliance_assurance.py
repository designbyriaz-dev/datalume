"""Compliance Assurance — architecture/04-operations-domain.md §4/§6:
adds ComplianceRequirement.hard_deadline (read by the status engine to
distinguish OVERDUE from EXPIRED) and the per-org
compliance_status_configs singleton (due_soon_days,
never_assessed_grace_days). The status engine itself computes at read
time and stores nothing new.

Revision ID: 0016_compliance_assurance
Revises: 0015_compliance_operations_hazards
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_compliance_assurance"
down_revision: Union[str, None] = "0015_compliance_operations_hazards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "compliance_requirements",
        sa.Column("hard_deadline", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "compliance_status_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("due_soon_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("never_assessed_grace_days", sa.Integer, nullable=False, server_default="30"),
        sa.UniqueConstraint("organisation_id", name="uq_compliance_status_config_org"),
    )
    op.create_index("ix_compliance_status_configs_organisation_id", "compliance_status_configs", ["organisation_id"])

    op.execute("ALTER TABLE compliance_status_configs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE compliance_status_configs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_compliance_status_configs ON compliance_status_configs
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_compliance_status_configs ON compliance_status_configs")
    op.drop_table("compliance_status_configs")
    op.drop_column("compliance_requirements", "hard_deadline")
