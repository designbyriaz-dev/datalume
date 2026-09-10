import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role_code: str
    status: str


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role_code: str = Field(min_length=1, max_length=64)


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role_code: str
    status: str
    expires_at: datetime
    invite_url: str


class PublicInvitationOut(BaseModel):
    organisation_name: str
    email: str
    role_code: str
    account_exists: bool


class AcceptInvitationRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=10, max_length=255)
