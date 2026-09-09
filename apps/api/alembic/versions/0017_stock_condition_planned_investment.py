"""Stock Condition Surveys and Planned Investment scoring config —
architecture/04-operations-domain.md §6, architecture/03-development-domain.md §6.

Revision ID: 0017_stock_condition_planned_investment
Revises: 0016_compliance_assurance
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_stock_condition_planned_investment"
down_revision: Union[str, None] = "0016_compliance_assurance"
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


def upgrade() -> None:
    op.create_table(
        "stock_condition_surveys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("survey_date", sa.Date, nullable=False),
        sa.Column("surveyor", sa.String(255), nullable=False),
        sa.Column("condition_ratings", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("next_survey_due", sa.Date, nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
    )
    op.create_index("ix_stock_condition_surveys_organisation_id", "stock_condition_surveys", ["organisation_id"])
    op.create_index("ix_stock_condition_surveys_property_id", "stock_condition_surveys", ["property_id"])
    _tenant_rls("stock_condition_surveys")

    op.create_table(
        "planned_investment_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("factor_code", sa.String(64), nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.UniqueConstraint("organisation_id", "factor_code", name="uq_planned_investment_weight_org_factor"),
    )
    op.create_index("ix_planned_investment_weights_organisation_id", "planned_investment_weights", ["organisation_id"])
    _tenant_rls("planned_investment_weights")

    op.create_table(
        "planned_investment_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("repair_frequency_window_months", sa.Integer, nullable=False, server_default="18"),
        sa.Column("repair_frequency_threshold", sa.Integer, nullable=False, server_default="3"),
        sa.UniqueConstraint("organisation_id", name="uq_planned_investment_config_org"),
    )
    op.create_index("ix_planned_investment_configs_organisation_id", "planned_investment_configs", ["organisation_id"])
    _tenant_rls("planned_investment_configs")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_planned_investment_configs ON planned_investment_configs")
    op.drop_table("planned_investment_configs")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_planned_investment_weights ON planned_investment_weights")
    op.drop_table("planned_investment_weights")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_stock_condition_surveys ON stock_condition_surveys")
    op.drop_table("stock_condition_surveys")
