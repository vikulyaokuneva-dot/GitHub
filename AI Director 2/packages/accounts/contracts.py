"""Non-secret account-registration contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.wb_core.contracts import TenantAccountScope


class Provider(StrEnum):
    """External commerce providers supported by account registration."""

    WILDBERRIES = "wildberries"


class CredentialRef(BaseModel):
    """Reference to separately managed credentials; never a credential value."""

    model_config = ConfigDict(frozen=True)

    reference: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.:-]{2,199}$")

    @field_validator("reference")
    @classmethod
    def reject_secret_shaped_references(cls, value: str) -> str:
        lowered = value.lower()
        if "=" in value or lowered.startswith(("bearer", "basic", "sk-")):
            raise ValueError("credential reference must not contain a secret value")
        return value


class AccountRegistration(BaseModel):
    """Stable internal ownership mapping for one registered provider account."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    account_id: UUID
    provider: Provider
    seller_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,150}$")
    active: bool
    created_at: datetime
    credential_ref: CredentialRef

    @field_validator("created_at")
    @classmethod
    def require_utc_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("created_at must be timezone-aware UTC")
        return value

    @property
    def scope(self) -> TenantAccountScope:
        """Expose the production ownership scope after registration only."""

        return TenantAccountScope(tenant_id=self.tenant_id, account_id=self.account_id)


class AccountRegistrationRepository(Protocol):
    """Durable provider-account registration boundary."""

    def register(self, registration: AccountRegistration) -> AccountRegistration:
        """Persist a new registration or return its idempotent existing record."""

    def get_wildberries_by_seller_id(self, seller_id: str) -> AccountRegistration | None:
        """Look up a registered WB seller without loading credential material."""

    def get_by_account_id(self, account_id: UUID) -> AccountRegistration | None:
        """Load the registered internal account identity for a scoped analysis run."""

    def list_wildberries(self) -> tuple[AccountRegistration, ...]:
        """List registered WB accounts without loading credential material."""
