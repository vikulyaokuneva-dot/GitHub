"""Durable SQLite repository for immutable, tenant-scoped raw objects."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from packages.persistence.sqlite import apply_migrations, connect

from .contracts import (
    DuplicateRawObjectError,
    EndpointMetadata,
    RawObject,
    RawObjectNotFoundError,
    RawObjectType,
    TenantAccountScope,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return deepcopy(value)


def _json_text(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=True, separators=(",", ":"), allow_nan=False)


class SQLiteRawObjectRepository:
    """Production repository preserving raw JSON separately from normalization."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        apply_migrations(database_path)

    @staticmethod
    def _from_row(row: tuple[object, ...]) -> RawObject:
        endpoint = EndpointMetadata.model_validate(json.loads(str(row[0])))
        return RawObject(
            object_id=str(row[1]),
            scope=TenantAccountScope(tenant_id=UUID(str(row[2])), account_id=UUID(str(row[3]))),
            endpoint=endpoint,
            object_type=RawObjectType(str(row[4])),
            source=str(row[5]),
            retrieved_at=datetime.fromisoformat(str(row[6])),
            operational_date=date.fromisoformat(str(row[7])),
            request_scope=cast(dict[str, Any], json.loads(str(row[8]))),
            payload=cast(dict[str, Any], json.loads(str(row[9]))),
            schema_version=str(row[10]),
            raw_payload_bytes=cast(bytes, row[11]),
        )

    def save(self, raw_object: RawObject) -> None:
        with connect(self._database_path) as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO raw_objects (
                        tenant_id, account_id, object_id, endpoint_name, endpoint_json, object_type,
                        source, retrieved_at, operational_date, request_scope_json, payload_json, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(raw_object.scope.tenant_id),
                        str(raw_object.scope.account_id),
                        raw_object.object_id,
                        raw_object.endpoint.name,
                        _json_text(raw_object.endpoint.model_dump(mode="json")),
                        raw_object.object_type.value,
                        raw_object.source,
                        raw_object.retrieved_at.isoformat(),
                        raw_object.operational_date.isoformat() if raw_object.operational_date is not None else None,
                        _json_text(raw_object.request_scope),
                        _json_text(raw_object.payload),
                        raw_object.schema_version,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO raw_object_payload_bytes (
                        tenant_id, account_id, object_id, payload_bytes, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(raw_object.scope.tenant_id),
                        str(raw_object.scope.account_id),
                        raw_object.object_id,
                        raw_object.payload_bytes,
                        raw_object.payload_sha256,
                    ),
                )
            except sqlite3.IntegrityError as error:
                if "raw_objects.tenant_id, raw_objects.account_id, raw_objects.object_id" in str(error):
                    raise DuplicateRawObjectError(f"raw object already exists: {raw_object.object_id}") from error
                raise

    def get(self, *, scope: TenantAccountScope, object_id: str) -> RawObject:
        with connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT endpoint_json, object_id, tenant_id, account_id, object_type, source,
                       retrieved_at, operational_date, request_scope_json, payload_json, schema_version,
                       payload_bytes
                FROM raw_objects
                INNER JOIN raw_object_payload_bytes USING (tenant_id, account_id, object_id)
                WHERE tenant_id = ? AND account_id = ? AND object_id = ?
                """,
                (str(scope.tenant_id), str(scope.account_id), object_id),
            ).fetchone()
        if row is None:
            raise RawObjectNotFoundError(f"raw object not found: {object_id}")
        return self._from_row(tuple(row))

    def list(self, *, scope: TenantAccountScope, endpoint_name: str | None = None) -> tuple[RawObject, ...]:
        query = """
            SELECT endpoint_json, object_id, tenant_id, account_id, object_type, source,
                   retrieved_at, operational_date, request_scope_json, payload_json, schema_version,
                   payload_bytes
            FROM raw_objects
            INNER JOIN raw_object_payload_bytes USING (tenant_id, account_id, object_id)
            WHERE tenant_id = ? AND account_id = ?
        """
        parameters: tuple[str, ...] = (str(scope.tenant_id), str(scope.account_id))
        if endpoint_name is not None:
            query += " AND endpoint_name = ?"
            parameters += (endpoint_name,)
        query += " ORDER BY object_id"
        with connect(self._database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._from_row(tuple(row)) for row in rows)
