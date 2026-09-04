"""Account-registration use case with system-generated internal identities."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .contracts import AccountRegistration, AccountRegistrationRepository, CredentialRef, Provider


class AccountRegistrationService:
    """Create the authoritative scope only when a WB seller is first registered."""

    def __init__(self, repository: AccountRegistrationRepository) -> None:
        self._repository = repository

    def register_wildberries_seller(self, *, seller_id: str, credential_ref: CredentialRef) -> AccountRegistration:
        """Register one seller idempotently; generated UUIDs are never derived from it."""

        existing = self._repository.get_wildberries_by_seller_id(seller_id)
        if existing is not None:
            return existing
        registration = AccountRegistration(
            tenant_id=uuid4(),
            account_id=uuid4(),
            provider=Provider.WILDBERRIES,
            seller_id=seller_id,
            active=True,
            created_at=datetime.now(UTC),
            credential_ref=credential_ref,
        )
        return self._repository.register(registration)
