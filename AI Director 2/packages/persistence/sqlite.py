"""Versioned SQLite schema used by the first production ingestion slice."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SqliteMigration:
    """One reversible schema migration."""

    version: int
    up: tuple[str, ...]
    down: tuple[str, ...]


_MIGRATIONS: tuple[SqliteMigration, ...] = (
    SqliteMigration(
        version=1,
        up=(
            """
            CREATE TABLE account_registrations (
                provider TEXT NOT NULL,
                seller_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                active INTEGER NOT NULL CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                credential_reference TEXT NOT NULL,
                PRIMARY KEY (provider, seller_id),
                UNIQUE (tenant_id, account_id)
            )
            """,
            """
            CREATE TABLE raw_objects (
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                endpoint_name TEXT NOT NULL,
                endpoint_json TEXT NOT NULL,
                object_type TEXT NOT NULL,
                source TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                operational_date TEXT NOT NULL,
                request_scope_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                PRIMARY KEY (tenant_id, account_id, object_id),
                FOREIGN KEY (tenant_id, account_id)
                    REFERENCES account_registrations (tenant_id, account_id)
            )
            """,
            """
            CREATE INDEX raw_objects_scope_endpoint_idx
            ON raw_objects (tenant_id, account_id, endpoint_name, object_id)
            """,
        ),
        down=(
            "DROP INDEX IF EXISTS raw_objects_scope_endpoint_idx",
            "DROP TABLE IF EXISTS raw_objects",
            "DROP TABLE IF EXISTS account_registrations",
        ),
    ),
    SqliteMigration(
        version=2,
        up=(
            """
            CREATE TABLE raw_object_payload_bytes (
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                payload_bytes BLOB NOT NULL,
                payload_sha256 TEXT NOT NULL,
                PRIMARY KEY (tenant_id, account_id, object_id),
                FOREIGN KEY (tenant_id, account_id, object_id)
                    REFERENCES raw_objects (tenant_id, account_id, object_id)
                    ON DELETE CASCADE
            )
            """,
        ),
        down=("DROP TABLE IF EXISTS raw_object_payload_bytes",),
    ),
    SqliteMigration(
        version=3,
        up=(
            # Денежные значения хранятся строкой под Decimal: NUMERIC-аффинность
            # SQLite привела бы их к float, а денежный контракт проекта это запрещает.
            """
            CREATE TABLE product_cost_settings (
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                nm_id TEXT NOT NULL CHECK (length(nm_id) BETWEEN 1 AND 30),
                seller_sku TEXT,
                cogs_per_unit TEXT NOT NULL CHECK (cogs_per_unit NOT LIKE '-%'),
                effective_from TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, account_id, nm_id),
                FOREIGN KEY (tenant_id, account_id)
                    REFERENCES account_registrations (tenant_id, account_id)
            )
            """,
            """
            CREATE TABLE tax_rate_settings (
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                tax_rate_percent TEXT NOT NULL CHECK (tax_rate_percent NOT LIKE '-%'),
                tax_basis TEXT NOT NULL CHECK (tax_basis IN ('realized_revenue')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, account_id),
                FOREIGN KEY (tenant_id, account_id)
                    REFERENCES account_registrations (tenant_id, account_id)
            )
            """,
            """
            CREATE TABLE period_finality_confirmations (
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                operational_date TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                evidence_code TEXT NOT NULL,
                PRIMARY KEY (tenant_id, account_id, operational_date),
                FOREIGN KEY (tenant_id, account_id)
                    REFERENCES account_registrations (tenant_id, account_id)
            )
            """,
        ),
        down=(
            "DROP TABLE IF EXISTS period_finality_confirmations",
            "DROP TABLE IF EXISTS tax_rate_settings",
            "DROP TABLE IF EXISTS product_cost_settings",
        ),
    ),
)

SQLITE_BUSY_TIMEOUT_SECONDS = 10.0


def connect(database_path: Path) -> sqlite3.Connection:
    """Open a short-lived durable connection with explicit contention settings."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


def _execute_all(connection: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        connection.execute(statement)


def apply_migrations(database_path: Path) -> None:
    """Apply every known migration exactly once."""

    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY
            )
            """
        )
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for migration in _MIGRATIONS:
            if migration.version in applied:
                continue
            _execute_all(connection, migration.up)
            connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (migration.version,))


def rollback_last_migration(database_path: Path) -> bool:
    """Rollback the newest known applied migration and report whether work occurred."""

    if not database_path.exists():
        return False
    with connect(database_path) as connection:
        try:
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        except sqlite3.OperationalError:
            return False
        if row is None or row[0] is None:
            return False
        version = int(row[0])
        migration = next((item for item in _MIGRATIONS if item.version == version), None)
        if migration is None:
            raise RuntimeError(f"cannot rollback unknown migration version: {version}")
        _execute_all(connection, migration.down)
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
        return True
