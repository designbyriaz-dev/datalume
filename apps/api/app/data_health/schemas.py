from pydantic import BaseModel


class CheckSummary(BaseModel):
    check_code: str
    applicable_count: int
    failing_count: int
    pass_ratio: float


class FindingOut(BaseModel):
    check_code: str
    severity: str
    affected_entity_type: str
    affected_entity_id: str
    message: str


class DataHealthOut(BaseModel):
    score_pct: float
    checks: list[CheckSummary]
    findings: list[FindingOut]
