import uuid

from pydantic import BaseModel, EmailStr, Field

from app.organisations.models import OrganisationType


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=10, max_length=255)
    organisation_name: str = Field(min_length=1, max_length=255)
    organisation_type: OrganisationType
    goals: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MembershipSummary(BaseModel):
    organisation_id: uuid.UUID
    organisation_name: str
    role_code: str

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    mfa_enabled: bool
    mfa_backup_codes_remaining: int
    memberships: list[MembershipSummary]


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_url: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MfaVerifyResponse(BaseModel):
    mfa_enabled: bool
    backup_codes: list[str]


# Accepts either a 6-digit TOTP code or a backup code (XXXXX-XXXXX,
# 11 chars including the separator) — the endpoint tries TOTP first,
# then falls back to backup codes, so the shape has to fit both.
class MfaChallengeRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=16)


class MfaDisableRequest(BaseModel):
    password: str


class MfaRegenerateBackupCodesRequest(BaseModel):
    password: str


class MfaBackupCodesResponse(BaseModel):
    backup_codes: list[str]
