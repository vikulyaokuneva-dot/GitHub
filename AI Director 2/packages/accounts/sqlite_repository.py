"""SQLite implementation of the account-registration repository."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from packages.persistence.sqlite import apply_migrations, connect

from .contracts import AccountRegistration, CredentialRef, Provider


class SQLiteAccountRegistrationRepository:
    """Durably maps a WB seller id to system-created tenant/account UUIDs."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        apply_migrations(database_path)

    @staticmethod
    def _from_row(row: tuple[object, ...]) -> AccountRegistration:
        return AccountRegistration(
            provider=Provider(str(row[0])),
            seller_id=str(row[1]),
            tenant_id=UUID(str(row[2])),
            account_id=UUID(str(row[3])),
            active=bool(row[4]),
            created_at=datetime.fromisoformat(str(row[5])),
            credential_ref=CredentialRef(reference=str(row[6])),
        )

    def register(self, registration: AccountRegistration) -> AccountRegistration:
        existing = self.get_wildberries_by_seller_id(registration.seller_id)
        if existing is not None:
            return existing
        with connect(self._database_path) as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO account_registrations (
                        provider, seller_id, tenant_id, account_id, active, created_at, credential_reference
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        registration.provider.value,
                        registration.seller_id,
                        str(registration.tenant_id),
                        str(registration.account_id),
                        int(registration.active),
                        registration.created_at.isoformat(),
                        registration.credential_ref.reference,
                    ),
                )
            except Exception:
                existing = self.get_wildberries_by_seller_id(registration.seller_id)
                if existing is not None:
                    return existing
                raise
        return registration

    def get_wildberries_by_seller_id(self, seller_id: str) -> AccountRegistration | None:
        with connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT provider, seller_id, tenant_id, account_id, active, created_at, credential_reference
                FROM account_registrations
                WHERE provider = ? AND seller_id = ?
                """,
                (Provider.WILDBERRIES.value, seller_id),
            ).fetchone()
        return None if row is None else self._from_row(tuple(row))

    def get_by_account_id(self, account_id: UUID) -> AccountRegistration | None:
        """Read a system account identity without exposing credential material."""

        with connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT provider, seller_id, tenant_id, account_id, active, created_at, credential_reference
                FROM account_registrations
                WHERE account_id = ?
                """,
                (str(account_id),),
            ).fetchone()
        return None if row is None else self._from_row(tuple(row))

    def list_wildberries(self) -> tuple[AccountRegistration, ...]:
        """List WB account identities for UI selection; credential values are never stored here."""

        with connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT provider, seller_id, tenant_id, account_id, active, created_at, credential_reference
                FROM account_registrations
                WHERE provider = ?
                ORDER BY seller_id, account_id
                """,
                (Provider.WILDBERRIES.value,),
            ).fetchall()
        return tuple(self._from_row(tuple(row)) for row in rows)
