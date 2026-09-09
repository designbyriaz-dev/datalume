"""Field dictionaries used to propose a column mapping — architecture/02
§2 step 3 ("Understand"). Deliberately data, not domain models — these
dictionaries describe the *shape* an upload is expected to have,
independent of whichever canonical table happens to receive it (Property
landed Sprint 5, Component Sprint 8). Sprint 5+ adds a dictionary per
domain as each one lands — see docs/BUILD_PROMPT.md §13 for the full
dataset list this eventually covers (Developments, Repairs, Compliance,
Tenancies...).
"""

from pydantic import BaseModel


class FieldSpec(BaseModel):
    key: str
    label: str
    required: bool
    aliases: list[str] = []


FIELD_DICTIONARIES: dict[str, list[FieldSpec]] = {
    "PROPERTIES": [
        FieldSpec(key="address", label="Address", required=True, aliases=["property_address", "addr"]),
        FieldSpec(key="postcode", label="Postcode", required=False, aliases=["post_code", "zip"]),
        FieldSpec(key="uprn", label="UPRN", required=False, aliases=["unique_property_reference_number"]),
        FieldSpec(key="property_type", label="Property Type", required=True, aliases=["type"]),
    ],
    "COMPONENTS": [
        FieldSpec(key="component_type", label="Component Type", required=True, aliases=["type", "asset_type"]),
        FieldSpec(key="manufacturer", label="Manufacturer", required=False, aliases=["make"]),
        FieldSpec(key="model", label="Model", required=False, aliases=[]),
        FieldSpec(key="serial_number", label="Serial Number", required=False, aliases=["serial", "serial_no"]),
        FieldSpec(key="installation_date", label="Installation Date", required=False, aliases=["installed", "install_date"]),
    ],
}


def get_field_dictionary(dataset_type: str) -> list[FieldSpec]:
    if dataset_type not in FIELD_DICTIONARIES:
        raise ValueError(f"Unknown dataset_type: {dataset_type}")
    return FIELD_DICTIONARIES[dataset_type]
