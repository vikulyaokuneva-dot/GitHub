"""Read-only verified loader for captured WB raw replay bundles."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final, Mapping, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import EndpointMetadata, RawObject, TenantAccountScope

REPLAY_BUNDLE_SCHEMA_VERSION: Final = "replay-bundle-v1"
REPLAY_FIXTURES_ROOT: Final = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay"


class ReplayBundleError(ValueError):
    """Base error for an invalid or unavailable replay bundle."""


class ReplayBundleNotFoundError(ReplayBundleError):
    """Raised when a requested captured bundle directory is absent."""


class ReplayBundleIntegrityError(ReplayBundleError):
    """Raised when a captured file differs from the declared SHA-256 manifest."""


class ReplayBundleSchemaError(ReplayBundleError):
    """Raised when replay metadata cannot form the declared raw-object contract."""


class ReplayPayloadManifestEntry(BaseModel):
    """Integrity record for a single immutable raw endpoint payload file."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(pattern=r"^raw/[a-z][a-z0-9_]*\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(ge=1)


class ReplayRawObjectMetadata(BaseModel):
    """Metadata needed to recreate one immutable RawObject without interpretation."""

    model_config = ConfigDict(frozen=True)

    object_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload_path: str = Field(pattern=r"^raw/[a-z][a-z0-9_]*\.json$")
    endpoint: EndpointMetadata
    source: str = Field(min_length=1, max_length=100)
    schema_version: str = Field(min_length=1, max_length=50)
    retrieved_at: datetime
    operational_date: date
    request_scope: dict[str, Any]
    source_identifier: str = Field(min_length=1, max_length=300)

    @field_validator("retrieved_at")
    @classmethod
    def require_utc_retrieval_timestamp(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
            raise ValueError("retrieved_at must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def require_raw_object_endpoint_consistency(self) -> ReplayRawObjectMetadata:
        if self.source != self.endpoint.source:
            raise ValueError("source must match endpoint.source")
        if self.schema_version != self.endpoint.schema_version:
            raise ValueError("schema_version must match endpoint.schema_version")
        return self


class ReplayBundleMetadata(BaseModel):
    """Capture-level identity and complete raw-object provenance."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(default=REPLAY_BUNDLE_SCHEMA_VERSION)
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    classification: str = Field(pattern=r"^real_raw_capture$")
    scope: TenantAccountScope
    captured_at: datetime
    raw_objects: tuple[ReplayRawObjectMetadata, ...]

    @field_validator("captured_at")
    @classmethod
    def require_utc_capture_timestamp(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
            raise ValueError("captured_at must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def require_unique_raw_object_ids_and_paths(self) -> ReplayBundleMetadata:
        object_ids = {item.object_id for item in self.raw_objects}
        paths = {item.payload_path for item in self.raw_objects}
        if not self.raw_objects:
            raise ValueError("a replay bundle requires at least one raw object")
        if len(object_ids) != len(self.raw_objects):
            raise ValueError("raw object IDs must be unique")
        if len(paths) != len(self.raw_objects):
            raise ValueError("raw payload paths must be unique")
        return self


class ReplayBundleManifest(BaseModel):
    """Versioned manifest binding metadata and raw endpoint payloads by hash."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(default=REPLAY_BUNDLE_SCHEMA_VERSION)
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    files: tuple[ReplayPayloadManifestEntry, ...]

    @model_validator(mode="after")
    def require_unique_payload_paths(self) -> ReplayBundleManifest:
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("manifest payload paths must be unique")
        return self


class ReplayBundle(BaseModel):
    """Verified capture bundle with immutable RawObjects; no pipeline stage is executed."""

    model_config = ConfigDict(frozen=True)

    metadata: ReplayBundleMetadata
    manifest: ReplayBundleManifest
    raw_objects: tuple[RawObject, ...]

    @model_validator(mode="after")
    def require_metadata_and_raw_objects_to_match(self) -> ReplayBundle:
        if self.metadata.case_id != self.manifest.case_id:
            raise ValueError("metadata and manifest case_id must match")
        if len(self.raw_objects) != len(self.metadata.raw_objects):
            raise ValueError("raw objects must match metadata entries")
        return self


def _read_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayBundleSchemaError(f"{label} must be valid UTF-8 JSON: {path.name}") from error
    if not isinstance(value, Mapping):
        raise ReplayBundleSchemaError(f"{label} must be a JSON object: {path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_directory(case_id: str, fixtures_root: Path) -> Path:
    if Path(case_id).name != case_id or not case_id or case_id in {".", ".."}:
        raise ReplayBundleNotFoundError("case_id must name one replay bundle directory")
    directory = fixtures_root / case_id
    if not directory.is_dir():
        raise ReplayBundleNotFoundError(f"replay bundle not found: {case_id}")
    return directory


def _load_manifest(case_directory: Path, case_id: str) -> ReplayBundleManifest:
    try:
        manifest = ReplayBundleManifest.model_validate(_read_json(case_directory / "manifest.json", label="manifest"))
    except Exception as error:
        if isinstance(error, ReplayBundleSchemaError):
            raise
        raise ReplayBundleSchemaError("manifest schema is invalid") from error
    if manifest.schema_version != REPLAY_BUNDLE_SCHEMA_VERSION or manifest.case_id != case_id:
        raise ReplayBundleSchemaError("manifest schema_version or case_id does not match the requested bundle")
    return manifest


def _load_metadata(case_directory: Path, case_id: str) -> ReplayBundleMetadata:
    try:
        metadata = ReplayBundleMetadata.model_validate(_read_json(case_directory / "metadata.json", label="metadata"))
    except Exception as error:
        if isinstance(error, ReplayBundleSchemaError):
            raise
        raise ReplayBundleSchemaError("metadata schema is invalid") from error
    if metadata.schema_version != REPLAY_BUNDLE_SCHEMA_VERSION or metadata.case_id != case_id:
        raise ReplayBundleSchemaError("metadata schema_version or case_id does not match the requested bundle")
    return metadata


def _verify_manifest(case_directory: Path, manifest: ReplayBundleManifest, metadata: ReplayBundleMetadata) -> None:
    metadata_payload_paths = {item.payload_path for item in metadata.raw_objects}
    manifest_paths = {item.path for item in manifest.files}
    if metadata_payload_paths != manifest_paths:
        raise ReplayBundleSchemaError("metadata payload paths must exactly match manifest files")
    for entry in manifest.files:
        file_path = case_directory / entry.path
        if not file_path.is_file():
            raise ReplayBundleIntegrityError(f"manifest payload is missing: {entry.path}")
        if file_path.stat().st_size != entry.byte_length:
            raise ReplayBundleIntegrityError(f"payload byte length does not match manifest: {entry.path}")
        if _sha256(file_path) != entry.sha256:
            raise ReplayBundleIntegrityError(f"payload SHA-256 does not match manifest: {entry.path}")


def _raw_objects(case_directory: Path, metadata: ReplayBundleMetadata) -> tuple[RawObject, ...]:
    objects: list[RawObject] = []
    for item in metadata.raw_objects:
        payload = _read_json(case_directory / item.payload_path, label="raw payload")
        try:
            objects.append(
                RawObject(
                    object_id=item.object_id,
                    scope=metadata.scope,
                    endpoint=item.endpoint,
                    object_type=item.endpoint.object_type,
                    source=item.source,
                    retrieved_at=item.retrieved_at,
                    operational_date=item.operational_date,
                    request_scope=item.request_scope,
                    payload=cast(dict[str, Any], dict(payload)),
                    schema_version=item.schema_version,
                )
            )
        except Exception as error:
            raise ReplayBundleSchemaError(f"raw object metadata is invalid: {item.payload_path}") from error
    return tuple(sorted(objects, key=lambda item: item.object_id))


def load_replay_bundle(case_id: str, *, fixtures_root: Path = REPLAY_FIXTURES_ROOT) -> ReplayBundle:
    """Load one verified immutable capture bundle without importing legacy or running any pipeline stage."""

    case_directory = _case_directory(case_id, fixtures_root)
    manifest = _load_manifest(case_directory, case_id)
    metadata = _load_metadata(case_directory, case_id)
    _verify_manifest(case_directory, manifest, metadata)
    return ReplayBundle(metadata=metadata, manifest=manifest, raw_objects=_raw_objects(case_directory, metadata))
