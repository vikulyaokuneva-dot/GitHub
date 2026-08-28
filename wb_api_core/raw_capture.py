"""Opt-in raw WB response capture at the transport boundary."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

RAW_CAPTURE_SCHEMA_VERSION = "wb-api-raw-capture-v1"
_CAPTURE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,99}$")
_CREDENTIAL_KEY_MARKERS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "client_secret",
    "secret",
    "password",
    "cookie",
    "credential",
    "signature",
)
_CREDENTIAL_VALUE_PREFIXES = ("bearer ", "basic ", "sk-")
_CREDENTIAL_QUERY_MARKERS = ("token", "secret", "credential", "signature", "api_key", "apikey", "password")


class RawCaptureError(RuntimeError):
    """Raised when an enabled raw capture cannot be safely persisted."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise RawCaptureError("capture timestamp must be UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _assert_credential_free(value: Any, *, location: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).strip().lower().replace("-", "_")
            if any(marker in key_text for marker in _CREDENTIAL_KEY_MARKERS):
                raise RawCaptureError(f"credential-like field is forbidden at {location}.{key}")
            _assert_credential_free(child, location=f"{location}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_credential_free(child, location=f"{location}[{index}]")
        return
    if not isinstance(value, str):
        return

    normalized = value.strip().lower()
    if normalized.startswith(_CREDENTIAL_VALUE_PREFIXES) or "wb_api_token" in normalized:
        raise RawCaptureError(f"credential-like value is forbidden at {location}")

    parsed = urlparse(value)
    if not parsed.query:
        return
    for query_key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = query_key.strip().lower().replace("-", "_")
        if any(marker in normalized_key for marker in _CREDENTIAL_QUERY_MARKERS):
            raise RawCaptureError(f"credential-like URL query parameter is forbidden at {location}")


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RawCaptureError("raw capture value must be JSON serializable") from error


class RawCaptureWriter:
    """Writes raw API responses to one explicit, isolated capture directory."""

    def __init__(
        self,
        *,
        destination: str | Path,
        capture_id: str,
        tenant_id: str,
        account_id: str,
        operational_date: str | None = None,
        source: str = "wildberries",
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not _CAPTURE_ID_PATTERN.fullmatch(capture_id):
            raise RawCaptureError("capture_id must be a stable lowercase directory name")
        if not str(tenant_id).strip() or not str(account_id).strip():
            raise RawCaptureError("tenant_id and account_id are required for raw capture")
        if not str(source).strip():
            raise RawCaptureError("source is required for raw capture")

        self._capture_id = capture_id
        self._source = str(source).strip()
        self._scope = {"tenant_id": str(tenant_id).strip(), "account_id": str(account_id).strip()}
        self._operational_date = str(operational_date).strip() or None
        self._clock = clock
        self._directory = Path(destination) / capture_id
        self._raw_directory = self._directory / "raw"
        self._created_at = _utc_timestamp(self._clock())
        self._objects: list[dict[str, Any]] = []

    def capture(
        self,
        *,
        endpoint_name: str,
        path: str,
        method: str,
        request_metadata: Mapping[str, Any],
        payload: Any,
        status_code: int,
        source_identifier: str | None = None,
    ) -> None:
        """Persist one raw decoded response or fail loudly before writing it."""

        _assert_credential_free(request_metadata, location="request_metadata")
        _assert_credential_free(payload, location="payload")
        _assert_credential_free(source_identifier, location="source_identifier")

        endpoint = str(endpoint_name).strip()
        endpoint_file_name = re.sub(r"[^a-z0-9_]+", "_", endpoint.lower()).strip("_")
        if not endpoint_file_name:
            raise RawCaptureError("endpoint_name must contain a safe filename character")
        if not str(path).startswith("/"):
            raise RawCaptureError("endpoint path must be relative")
        if "?" in str(path) or "#" in str(path):
            raise RawCaptureError("endpoint path must not contain a query or fragment")

        retrieved_at = _utc_timestamp(self._clock())
        payload_bytes = _json_bytes(payload)
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        sequence = len(self._objects) + 1
        payload_path = f"raw/{sequence:04d}_{endpoint_file_name}.json"
        object_id = hashlib.sha256(
            f"{self._capture_id}:{sequence}:{endpoint}:{path}:{payload_sha256}".encode("utf-8")
        ).hexdigest()
        entry = {
            "object_id": object_id,
            "payload_path": payload_path,
            "endpoint": {"name": endpoint, "path": str(path), "method": str(method).upper()},
            "request_metadata": dict(request_metadata),
            "source": self._source,
            "source_metadata": {
                "transport": "wb_api_core.client.WBApiClient.request_json",
                "schema_version": RAW_CAPTURE_SCHEMA_VERSION,
            },
            "source_identifier": str(source_identifier).strip() if source_identifier else None,
            "retrieved_at": retrieved_at,
            "operational_date": self._operational_date,
            "http": {"status_code": int(status_code)},
            "sha256": payload_sha256,
            "byte_length": len(payload_bytes),
        }
        _assert_credential_free(entry, location="capture_entry")

        self._ensure_output_directory()
        raw_path = self._directory / payload_path
        raw_path.write_bytes(payload_bytes)
        self._objects.append(entry)
        self._write_manifest()

    def _write_manifest(self) -> None:
        manifest = {
            "schema_version": RAW_CAPTURE_SCHEMA_VERSION,
            "capture_id": self._capture_id,
            "scope": self._scope,
            "created_at": self._created_at,
            "objects": self._objects,
        }
        _assert_credential_free(manifest, location="manifest")
        manifest_path = self._directory / "manifest.json"
        temporary_path = self._directory / "manifest.json.tmp"
        temporary_path.write_bytes(_json_bytes(manifest))
        temporary_path.replace(manifest_path)

    def _ensure_output_directory(self) -> None:
        if self._directory.exists():
            if self._objects:
                return
            raise RawCaptureError(f"capture destination already exists: {self._directory}")
        self._raw_directory.mkdir(parents=True, exist_ok=False)
