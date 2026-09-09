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
    memberships: list[MembershipSummary]
