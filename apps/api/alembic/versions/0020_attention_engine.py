"""Cross-Domain Attention Engine — architecture/06-intelligence-layer.md §3.

Revision ID: 0020_attention_engine
Revises: 0019_rent_payments_arrears
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_attention_engine"
down_revision: Union[str, None] = "0019_rent_payments_arrears"
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
        "attention_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain_scope", sa.String(255), nullable=False),
        sa.Column("rule_definition", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("severity_default", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="attentionseverity"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organisation_id", "code", name="uq_attention_rule_org_code"),
    )
    op.create_index("ix_attention_rules_organisation_id", "attention_rules", ["organisation_id"])
    _tenant_rls("attention_rules")

    op.create_table(
        "attention_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("attention_rules.id"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("severity", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="attentionseverity"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("explanation", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum("OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED", name="signalstatus"),
            nullable=False,
        ),
    )
    op.create_index("ix_attention_signals_organisation_id", "attention_signals", ["organisation_id"])
    op.create_index("ix_attention_signals_rule_id", "attention_signals", ["rule_id"])
    op.create_index("ix_attention_signals_entity", "attention_signals", ["entity_type", "entity_id"])
    _tenant_rls("attention_signals")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_attention_signals ON attention_signals")
    op.drop_table("attention_signals")
    op.execute("DROP TYPE IF EXISTS signalstatus")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_attention_rules ON attention_rules")
    op.drop_table("attention_rules")
    op.execute("DROP TYPE IF EXISTS attentionseverity")
