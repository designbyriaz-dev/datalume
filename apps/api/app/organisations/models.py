import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class OrganisationType(str, enum.Enum):
    HOUSING_ASSOCIATION = "HOUSING_ASSOCIATION"
    LOCAL_AUTHORITY = "LOCAL_AUTHORITY"
    MANAGING_AGENT = "MANAGING_AGENT"
    PRIVATE_LANDLORD = "PRIVATE_LANDLORD"
    COMMERCIAL_LANDLORD = "COMMERCIAL_LANDLORD"
    BUILD_TO_RENT = "BUILD_TO_RENT"
    PROPERTY_MANAGEMENT_CO = "PROPERTY_MANAGEMENT_CO"
    SUPPORTED_HOUSING = "SUPPORTED_HOUSING"
    PROPERTY_INVESTOR = "PROPERTY_INVESTOR"
    OTHER = "OTHER"


class OrganisationStatus(str, enum.Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    organisation_type: Mapped[OrganisationType] = mapped_column(Enum(OrganisationType))
    goals: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[OrganisationStatus] = mapped_column(
        Enum(OrganisationStatus), default=OrganisationStatus.TRIAL
    )
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/London")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="organisation")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    name: Mapped[str] = mapped_column(String(255))
    workspace_type: Mapped[str] = mapped_column(String(64), default="DEFAULT")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organisation: Mapped[Organisation] = relationship(back_populates="workspaces")
