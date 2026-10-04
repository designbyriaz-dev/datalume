"""Add (organisation_id, <sort column> DESC) composite indexes for the
four list endpoints spec §72 names as needing to scale ("millions of
repairs/payment records", "large document/evidence registers") and
that this session's load test (STATUS.md) just paginated.

Each endpoint already filters on organisation_id (covered by an
existing plain index) and then does `ORDER BY <date column> DESC
OFFSET ... LIMIT ...`. The existing organisation_id-only index lets
Postgres find the org's rows but not avoid a separate sort step, and a
deep OFFSET still has to walk and discard every row before it in sort
order. Measured directly against a 20,000-property / 200,000-repair
seed: GET /api/v1/repairs at offset=0 took ~65ms, the same call at
offset=199,000 took ~104ms — a real, growing cost from exactly this
missing composite index. These let the planner use an index-only scan
in (organisation_id, date DESC) order instead, for repairs,
payment_transactions, documents, and rent_obligations alike.

Revision ID: 0031_list_endpoint_sort_indexes
Revises: 0030_org_component_type_unique_constraint
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_list_endpoint_sort_indexes"
down_revision: Union[str, None] = "0030_org_component_type_unique_constraint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_repairs_org_reported_date", "repairs", "reported_date"),
    ("ix_payment_transactions_org_received_date", "payment_transactions", "received_date"),
    ("ix_documents_org_uploaded_at", "documents", "uploaded_at"),
    ("ix_rent_obligations_org_due_date", "rent_obligations", "due_date"),
]


def upgrade() -> None:
    for name, table, date_column in _INDEXES:
        op.create_index(name, table, ["organisation_id", sa.text(f"{date_column} DESC")], unique=False)


def downgrade() -> None:
    for name, table, _date_column in _INDEXES:
        op.drop_index(name, table_name=table)
