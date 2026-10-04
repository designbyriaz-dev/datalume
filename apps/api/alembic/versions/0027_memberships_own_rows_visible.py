"""Widen memberships' RLS policy so a user can see their own rows
across every organisation they belong to — app/core/tenancy.py's
GET /auth/me needs this for the workspace-switcher list (a legitimately
cross-tenant query for one user, not a cross-tenant leak).

Found via a real backup/restore drill (see STATUS.md): logging in
against a freshly-restored database and calling the real /me endpoint
returned memberships: [] even though the row and a correctly org-
scoped GET /api/v1/properties both worked fine — /me's own query
(`.filter(Membership.user_id == user.id, ...)`, deliberately no
organisation_id filter, spanning every org the user belongs to) had no
tenant context to scope TenantScopedSession to, and memberships'
original policy (0001_foundation.py) only ever matched on
organisation_id.

The fix adds `OR user_id = current_setting('app.current_user_id',
true)::uuid` rather than touching organisation_id's own clause at all
— a membership row is now visible if it belongs to the currently
scoped organisation (unchanged) OR belongs to the currently
authenticated user regardless of org (new). This can only ever ADD
visibility for the user's own rows; it cannot let Org A see Org B's
membership roster, since that path (organisations/router.py's
list_members) stays additionally filtered by
Membership.organisation_id == ctx.organisation_id at the app layer
exactly as before, and RLS's own organisation_id clause still blocks
every row outside that org regardless of whose session is asking.

app/core/tenancy.py's get_current_user sets app.current_user_id (same
connection-scoped set_config pattern as app.current_org_id, same
reset-on-checkin in app/core/db.py) the moment a session cookie
resolves to a real user — before any organisation is chosen, which is
exactly when /me runs.

Revision ID: 0027_memberships_own_rows_visible
Revises: 0026_rent_obligation_provenance
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027_memberships_own_rows_visible"
down_revision: Union[str, None] = "0026_rent_obligation_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP POLICY tenant_isolation_memberships ON memberships")
    op.execute(
        """
        CREATE POLICY tenant_isolation_memberships ON memberships
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
            OR user_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY tenant_isolation_memberships ON memberships")
    op.execute(
        """
        CREATE POLICY tenant_isolation_memberships ON memberships
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )
