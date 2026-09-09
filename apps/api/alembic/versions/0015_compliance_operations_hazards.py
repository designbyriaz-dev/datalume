"""Compliance Operations (inspections, actions) and Hazards/Damp & Mould —
architecture/04-operations-domain.md §3/§5.

Revision ID: 0015_compliance_operations_hazards
Revises: 0014_compliance_foundation
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_compliance_operations_hazards"
down_revision: Union[str, None] = "0014_compliance_foundation"
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
        "inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_requirements.id"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("inspector", sa.String(255), nullable=False),
        sa.Column("inspection_date", sa.Date, nullable=False),
        sa.Column("result", sa.Enum("SATISFACTORY", "UNSATISFACTORY", "ADVISORY", name="inspectionresult"), nullable=False),
        sa.Column("next_due_date", sa.Date, nullable=True),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
        *_provenance_columns(),
    )
    op.create_index("ix_inspections_organisation_id", "inspections", ["organisation_id"])
    op.create_index("ix_inspections_requirement_id", "inspections", ["requirement_id"])
    op.create_index("ix_inspections_entity", "inspections", ["entity_type", "entity_id"])
    _tenant_rls("inspections")

    op.create_table(
        "compliance_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspections.id"), nullable=True),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_requirements.id"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("deadline", sa.Date, nullable=False),
        sa.Column("status", sa.Enum("OPEN", "COMPLETED", "CANCELLED", name="complianceactionstatus"), nullable=False),
        sa.Column("completed_date", sa.Date, nullable=True),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
        *_provenance_columns(),
    )
    op.create_index("ix_compliance_actions_organisation_id", "compliance_actions", ["organisation_id"])
    op.create_index("ix_compliance_actions_requirement_id", "compliance_actions", ["requirement_id"])
    op.create_index("ix_compliance_actions_entity", "compliance_actions", ["entity_type", "entity_id"])
    _tenant_rls("compliance_actions")

    op.create_table(
        "hazards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("hazard_type", sa.String(128), nullable=False),
        sa.Column("reported_date", sa.Date, nullable=False),
        sa.Column("severity", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="hazardseverity"), nullable=False),
        sa.Column(
            "investigation_status",
            sa.Enum("PENDING", "CONFIRMED", "NOT_CONFIRMED", "INCONCLUSIVE", name="hazardinvestigationstatus"),
            nullable=False,
        ),
        sa.Column("findings", sa.Text, nullable=True),
        sa.Column("deadline", sa.Date, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "REPORTED", "TRIAGED", "INVESTIGATING", "INVESTIGATED", "ACTION_IN_PROGRESS", "FOLLOW_UP", "CLOSED",
                name="hazardstatus",
            ),
            nullable=False,
        ),
        *_provenance_columns(),
    )
    op.create_index("ix_hazards_organisation_id", "hazards", ["organisation_id"])
    op.create_index("ix_hazards_property_id", "hazards", ["property_id"])
    _tenant_rls("hazards")

    op.create_table(
        "hazard_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("hazard_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hazards.id"), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("deadline", sa.Date, nullable=False),
        sa.Column("status", sa.Enum("OPEN", "COMPLETED", "CANCELLED", name="hazardactionstatus"), nullable=False),
        sa.Column("completed_date", sa.Date, nullable=True),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
    )
    op.create_index("ix_hazard_actions_organisation_id", "hazard_actions", ["organisation_id"])
    op.create_index("ix_hazard_actions_hazard_id", "hazard_actions", ["hazard_id"])
    _tenant_rls("hazard_actions")

    op.create_table(
        "hazard_rule_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("window_months", sa.Integer, nullable=False),
        sa.Column("threshold", sa.Integer, nullable=False),
        sa.UniqueConstraint("organisation_id", "rule_code", name="uq_hazard_rule_config_org_rule"),
    )
    op.create_index("ix_hazard_rule_configs_organisation_id", "hazard_rule_configs", ["organisation_id"])
    _tenant_rls("hazard_rule_configs")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_hazard_rule_configs ON hazard_rule_configs")
    op.drop_table("hazard_rule_configs")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_hazard_actions ON hazard_actions")
    op.drop_table("hazard_actions")
    op.execute("DROP TYPE IF EXISTS hazardactionstatus")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_hazards ON hazards")
    op.drop_table("hazards")
    op.execute("DROP TYPE IF EXISTS hazardstatus")
    op.execute("DROP TYPE IF EXISTS hazardinvestigationstatus")
    op.execute("DROP TYPE IF EXISTS hazardseverity")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_compliance_actions ON compliance_actions")
    op.drop_table("compliance_actions")
    op.execute("DROP TYPE IF EXISTS complianceactionstatus")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_inspections ON inspections")
    op.drop_table("inspections")
    op.execute("DROP TYPE IF EXISTS inspectionresult")
