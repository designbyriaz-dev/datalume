"""AdaptiveWorkspaceResolver — see architecture/01-platform-foundations.md §5.

Pure function: (organisation_type, goals) -> WorkspaceLayout. No I/O, no
per-page conditionals in the frontend — this is the single place sector
adaptivity is decided, and the single place it is unit tested."""

from pydantic import BaseModel

from app.organisations.models import OrganisationType


class NavSection(BaseModel):
    key: str
    label: str
    icon: str
    href: str


class WorkspaceLayout(BaseModel):
    nav_sections: list[NavSection]
    home_kpis: list[str]
    terminology: dict[str, str]
    compliance_domains: list[str]


_DEFAULT_21_DOMAINS = [
    "GAS_SAFETY", "ELECTRICAL_SAFETY", "FIRE_SAFETY", "ASBESTOS_MANAGEMENT",
    "WATER_HYGIENE_LEGIONELLA", "LIFT_SAFETY", "SMOKE_CO_ALARMS", "DAMP_AND_MOULD",
    "BUILDING_SAFETY", "HAZARDS_HHSRS", "DECENT_HOMES", "STOCK_CONDITION",
    "REPAIRS_MAINTENANCE_SAFETY", "EMERGENCY_RESPONSE", "EPC", "ACCESSIBILITY",
    "STRUCTURAL_SAFETY", "COMMUNAL_AREA_SAFETY", "CONTRACTOR_EVIDENCE",
    "STATUTORY_INSPECTION_TRACKING", "SAFETY_DATA_ASSURANCE",
]

_BASE_NAV = [
    NavSection(key="home", label="Home", icon="home", href="/home"),
    NavSection(key="properties", label="Properties", icon="building", href="/properties"),
    NavSection(key="data-uploads", label="Data & Uploads", icon="upload", href="/data-and-uploads"),
    NavSection(key="reports", label="Reports", icon="file-text", href="/reports"),
    NavSection(key="ask", label="Ask DataLume", icon="sparkles", href="/ask"),
]

_DEVELOPMENT_NAV = [
    NavSection(key="developments", label="Developments", icon="hard-hat", href="/developments"),
    NavSection(key="buildings", label="Buildings", icon="layers", href="/buildings"),
    NavSection(key="components", label="Components", icon="cpu", href="/components"),
    NavSection(key="handover", label="Handover", icon="check-circle", href="/developments"),
]

_OPERATIONS_NAV = [
    NavSection(key="repairs", label="Repairs", icon="wrench", href="/repairs"),
    NavSection(key="compliance", label="Compliance", icon="shield", href="/compliance"),
    NavSection(key="safety", label="Safety", icon="alert-triangle", href="/safety"),
    NavSection(key="stock-condition", label="Stock Condition", icon="clipboard", href="/stock-condition"),
    NavSection(key="planned-investment", label="Planned Investment", icon="trending-up", href="/planned-investment"),
]

_COMMERCIAL_NAV = [
    NavSection(key="tenancies", label="Tenancies", icon="users", href="/tenancies"),
    NavSection(key="leases", label="Leases", icon="file-signature", href="/leases"),
    NavSection(key="rent-payments", label="Rent & Payments", icon="banknote", href="/rent-and-payments"),
    NavSection(key="arrears", label="Arrears", icon="alert-circle", href="/arrears"),
]

_HOUSING_ASSOCIATION_TYPES = {
    OrganisationType.HOUSING_ASSOCIATION,
    OrganisationType.LOCAL_AUTHORITY,
    OrganisationType.SUPPORTED_HOUSING,
}

_COMMERCIAL_TYPES = {
    OrganisationType.COMMERCIAL_LANDLORD,
    OrganisationType.MANAGING_AGENT,
    OrganisationType.BUILD_TO_RENT,
    OrganisationType.PROPERTY_MANAGEMENT_CO,
    OrganisationType.PROPERTY_INVESTOR,
}


def resolve_workspace_layout(
    organisation_type: OrganisationType, goals: list[str] | None = None
) -> WorkspaceLayout:
    goals = goals or []
    nav = list(_BASE_NAV)
    terminology: dict[str, str] = {}
    compliance_domains: list[str] = []
    home_kpis = ["total_properties", "data_health_score", "items_needing_attention"]

    if organisation_type in _HOUSING_ASSOCIATION_TYPES:
        nav = nav[:2] + _DEVELOPMENT_NAV + _OPERATIONS_NAV + nav[2:]
        compliance_domains = _DEFAULT_21_DOMAINS
        home_kpis += ["compliance_rate", "open_repairs", "maintenance_spend"]
    elif organisation_type in _COMMERCIAL_TYPES:
        nav = nav[:2] + _COMMERCIAL_NAV + _OPERATIONS_NAV[1:2] + nav[2:]
        terminology = {"property": "unit", "tenant": "occupier"}
        compliance_domains = [
            d for d in _DEFAULT_21_DOMAINS
            if d not in {"DECENT_HOMES", "HAZARDS_HHSRS"}
        ]
        home_kpis += ["rent_collection_rate", "arrears_outstanding", "lease_expiries_90d"]
    else:  # PRIVATE_LANDLORD, OTHER
        nav = nav[:2] + _OPERATIONS_NAV[:2] + nav[2:]
        compliance_domains = _DEFAULT_21_DOMAINS
        home_kpis += ["compliance_rate", "open_repairs"]

    return WorkspaceLayout(
        nav_sections=nav,
        home_kpis=home_kpis,
        terminology=terminology,
        compliance_domains=compliance_domains,
    )
