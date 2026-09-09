from app.organisations.adaptive import resolve_workspace_layout
from app.organisations.models import OrganisationType


def test_housing_association_prioritises_development_and_compliance():
    layout = resolve_workspace_layout(OrganisationType.HOUSING_ASSOCIATION, [])
    keys = [s.key for s in layout.nav_sections]
    assert "developments" in keys
    assert "compliance" in keys
    assert len(layout.compliance_domains) == 21


def test_commercial_landlord_prioritises_leases_and_rent():
    layout = resolve_workspace_layout(OrganisationType.COMMERCIAL_LANDLORD, [])
    keys = [s.key for s in layout.nav_sections]
    assert "leases" in keys
    assert "arrears" in keys
    assert layout.terminology.get("property") == "unit"
    # HHSRS/hazards and decent homes are HA-specific concepts, spec §11
    assert "HAZARDS_HHSRS" not in layout.compliance_domains


def test_private_landlord_gets_lean_navigation():
    layout = resolve_workspace_layout(OrganisationType.PRIVATE_LANDLORD, [])
    keys = [s.key for s in layout.nav_sections]
    assert "developments" not in keys
    assert "leases" not in keys
    assert "repairs" in keys
