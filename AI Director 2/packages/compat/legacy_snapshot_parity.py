"""Read-only parity harness for the frozen legacy WB Core snapshot contract."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeAlias, cast

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

TARGET_ROOT: Final = Path(__file__).resolve().parents[2]
LEGACY_REPOSITORY_ROOT: Final = TARGET_ROOT.parent
DEFAULT_FIXTURE_DIRECTORY: Final = TARGET_ROOT / "tests" / "fixtures" / "golden" / "wb_core_snapshot_v1"


class FixtureIntegrityError(RuntimeError):
    """Raised when a golden fixture differs from its recorded manifest hash."""


class FixtureParityError(AssertionError):
    """Raised when the legacy replay differs from the immutable expected snapshot."""


@dataclass(frozen=True)
class GoldenSnapshotFixture:
    """Validated fixture files and the context required to replay the legacy pipeline."""

    directory: Path
    manifest: JsonObject
    raw_bundle: JsonObject
    expected_snapshot: JsonObject


def canonical_json_bytes(value: object) -> bytes:
    """Encode JSON deterministically so fixture hashes do not depend on formatting."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def canonical_sha256(value: object) -> str:
    """Return the SHA-256 digest for a parsed JSON document."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load_json_object(path: Path) -> JsonObject:
    try:
        with path.open("r", encoding="utf-8") as fixture_file:
            value = json.load(fixture_file)
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureIntegrityError(f"Cannot load JSON fixture {path}: {error}") from error

    if not isinstance(value, dict):
        raise FixtureIntegrityError(f"Fixture {path} must contain a JSON object")
    return cast(JsonObject, value)


def _required_object(container: Mapping[str, JsonValue], key: str) -> JsonObject:
    value = container.get(key)
    if not isinstance(value, dict):
        raise FixtureIntegrityError(f"Manifest field {key!r} must be an object")
    return value


def _required_string(container: Mapping[str, JsonValue], key: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value:
        raise FixtureIntegrityError(f"Manifest field {key!r} must be a non-empty string")
    return value


def _fixture_file(directory: Path, filename: str) -> Path:
    path = directory / filename
    if Path(filename).name != filename or path.parent != directory:
        raise FixtureIntegrityError(f"Manifest fixture filename {filename!r} must not contain a path")
    return path


def _validate_manifest_shape(manifest: JsonObject) -> tuple[JsonObject, JsonObject]:
    if _required_string(manifest, "fixture_id") != "wb_core_snapshot_v1":
        raise FixtureIntegrityError("Manifest fixture_id must be 'wb_core_snapshot_v1'")
    if _required_string(manifest, "classification") != "synthetic":
        raise FixtureIntegrityError("Golden fixture must be explicitly classified as synthetic")
    if _required_string(manifest, "schema_version") != "1":
        raise FixtureIntegrityError("Unsupported golden fixture schema version")

    context = _required_object(manifest, "snapshot_context")
    for key in ("seller_id", "run_date", "operational_date", "timezone"):
        _required_string(context, key)
    if _required_string(context, "timezone") != "Europe/Moscow":
        raise FixtureIntegrityError("Golden fixture business timezone must be Europe/Moscow")

    return _required_object(manifest, "files"), _required_object(manifest, "sha256")


def load_golden_fixture(directory: Path = DEFAULT_FIXTURE_DIRECTORY) -> GoldenSnapshotFixture:
    """Load a golden fixture and verify its canonical JSON hashes before replaying it."""

    manifest = _load_json_object(directory / "manifest.json")
    files, hashes = _validate_manifest_shape(manifest)
    raw_filename = _required_string(files, "raw_bundle")
    expected_filename = _required_string(files, "expected_snapshot")
    raw_bundle = _load_json_object(_fixture_file(directory, raw_filename))
    expected_snapshot = _load_json_object(_fixture_file(directory, expected_filename))

    documents = {
        "raw_bundle": raw_bundle,
        "expected_snapshot": expected_snapshot,
    }
    for name, document in documents.items():
        expected_hash = _required_string(hashes, name)
        actual_hash = canonical_sha256(document)
        if actual_hash != expected_hash:
            raise FixtureIntegrityError(
                f"Fixture integrity mismatch for {name}: expected {expected_hash}, got {actual_hash}"
            )

    return GoldenSnapshotFixture(
        directory=directory,
        manifest=manifest,
        raw_bundle=raw_bundle,
        expected_snapshot=expected_snapshot,
    )


LegacyNormalize: TypeAlias = Callable[[dict[str, Any]], dict[str, Any]]
LegacyReconcile: TypeAlias = Callable[..., dict[str, Any]]
LegacySnapshotBuilder: TypeAlias = Callable[..., dict[str, Any]]


def _legacy_pipeline() -> tuple[LegacyNormalize, LegacyReconcile, LegacySnapshotBuilder]:
    """Resolve legacy imports locally; this is the only allowed target-side import path."""

    legacy_root = str(LEGACY_REPOSITORY_ROOT)
    if legacy_root not in sys.path:
        sys.path.insert(0, legacy_root)

    normalize_module = importlib.import_module("wb_api_core.normalize")
    reconcile_module = importlib.import_module("wb_api_core.reconcile")
    snapshot_module = importlib.import_module("wb_api_core.snapshot")
    normalize_bundle = cast(LegacyNormalize, normalize_module.normalize_bundle)
    reconcile_bundle = cast(LegacyReconcile, reconcile_module.reconcile_bundle)
    build_snapshot = cast(LegacySnapshotBuilder, snapshot_module.build_snapshot)

    return normalize_bundle, reconcile_bundle, build_snapshot


def replay_legacy_snapshot(fixture: GoldenSnapshotFixture) -> JsonObject:
    """Run the known legacy normalize -> reconcile -> snapshot chain without I/O."""

    context = _required_object(fixture.manifest, "snapshot_context")
    normalize_bundle, reconcile_bundle, build_snapshot = _legacy_pipeline()
    raw_bundle = cast(dict[str, Any], fixture.raw_bundle)
    normalized_bundle = normalize_bundle(raw_bundle)
    reconcile_result = reconcile_bundle(
        raw_bundle=raw_bundle,
        normalized_bundle=normalized_bundle,
        target_date=_required_string(context, "operational_date"),
    )
    snapshot = build_snapshot(
        seller_id=_required_string(context, "seller_id"),
        run_date=_required_string(context, "run_date"),
        operational_date=_required_string(context, "operational_date"),
        timezone_name=_required_string(context, "timezone"),
        reconcile_result=reconcile_result,
    )
    return cast(JsonObject, snapshot)


def _first_difference(expected: object, actual: object, path: str = "$") -> str | None:
    if type(expected) is not type(actual):
        return f"{path}: expected {type(expected).__name__}, got {type(actual).__name__}"
    if isinstance(expected, dict) and isinstance(actual, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            return f"{path}.{key}: key is missing from actual snapshot"
        for key in sorted(actual_keys - expected_keys):
            return f"{path}.{key}: unexpected key in actual snapshot"
        for key in sorted(expected_keys):
            difference = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path}: expected list length {len(expected)}, got {len(actual)}"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            difference = _first_difference(expected_item, actual_item, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if expected != actual:
        return (
            f"{path}: expected {json.dumps(expected, ensure_ascii=True)}, "
            f"got {json.dumps(actual, ensure_ascii=True)}"
        )
    return None


def assert_snapshot_parity(fixture: GoldenSnapshotFixture | None = None) -> JsonObject:
    """Replay legacy behavior and fail with the first deterministic snapshot difference."""

    resolved_fixture = fixture or load_golden_fixture()
    actual_snapshot = replay_legacy_snapshot(resolved_fixture)
    difference = _first_difference(resolved_fixture.expected_snapshot, actual_snapshot)
    if difference is not None:
        raise FixtureParityError(f"Legacy snapshot parity failed: {difference}")
    return actual_snapshot
