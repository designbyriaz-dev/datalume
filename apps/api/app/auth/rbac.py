"""Fixed role -> permission sets, defined in code per
architecture/01-platform-foundations.md §3. Not user-editable in Build 1."""

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "OWNER": {"*"},
    "ADMIN": {"*"},
    "DATA_ANALYST": {
        "development.read", "development.write", "operations.read", "operations.write",
        "commercial.read", "uploads.write", "reports.read",
    },
    "MANAGER": {
        "development.read", "development.write", "operations.read", "operations.write",
        "commercial.read", "reports.read",
    },
    "VIEWER": {
        "development.read", "operations.read", "commercial.read", "reports.read",
    },
    "DEVELOPMENT_MANAGER": {"development.read", "development.write", "reports.read"},
    "HANDOVER_MANAGER": {"development.read", "development.write", "development.handover", "reports.read"},
    "ASSET_MANAGER": {"development.read", "development.write", "operations.read", "reports.read"},
    "REPAIRS_MANAGER": {"operations.read", "operations.write", "reports.read"},
    "COMPLIANCE_MANAGER": {"operations.read", "operations.write", "operations.compliance", "reports.read"},
    "BUILDING_SAFETY_MANAGER": {"operations.read", "operations.write", "operations.compliance", "reports.read"},
    "PROPERTY_MANAGER": {"development.read", "operations.read", "operations.write", "reports.read"},
    "COMMERCIAL_PROPERTY_MANAGER": {"commercial.read", "commercial.write", "reports.read"},
    "LEASE_MANAGER": {"commercial.read", "commercial.write", "reports.read"},
    "RENT_MANAGER": {"commercial.read", "commercial.write", "commercial.payments", "reports.read"},
    "FINANCE_VIEWER": {"commercial.read", "reports.read"},
    "EXECUTIVE": {
        "development.read", "operations.read", "commercial.read", "reports.read", "reports.board",
    },
}

SYSTEM_ROLE_CODES = list(ROLE_PERMISSIONS.keys())


def role_has_permission(role_code: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role_code, set())
    return "*" in perms or permission in perms
