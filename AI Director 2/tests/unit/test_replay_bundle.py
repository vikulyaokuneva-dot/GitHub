from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from packages.wb_core.replay import (
    REPLAY_BUNDLE_SCHEMA_VERSION,
    ReplayBundleIntegrityError,
    ReplayBundleNotFoundError,
    ReplayBundleSchemaError,
    load_replay_bundle,
)

CASE_ID = "captured-wb-case"
OBJECT_ID = "a" * 64


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")


def _capture_fixture(root: Path) -> Path:
    directory = root / CASE_ID
    raw_directory = directory / "raw"
    raw_directory.mkdir(parents=True)
    payload_path = raw_directory / "sales_funnel_products.json"
    _write_json(
        payload_path,
        {
            "data": {
                "products": [
                    {
                        "product": {"nmId": 1001, "vendorCode": "CAPTURED-ART-1001"},
                        "statistic": {"selected": {"openCount": 42, "cartCount": 7, "orderCount": 2}},
                    }
                ]
            }
        },
    )
    _write_json(
        directory / "metadata.json",
        {
            "schema_version": REPLAY_BUNDLE_SCHEMA_VERSION,
            "case_id": CASE_ID,
            "classification": "real_raw_capture",
            "scope": {
                "tenant_id": "00000000-0000-0000-0000-000000000101",
                "account_id": "00000000-0000-0000-0000-000000000201",
            },
            "captured_at": "2026-08-24T10:31:00Z",
            "raw_objects": [
                {
                    "object_id": OBJECT_ID,
                    "payload_path": "raw/sales_funnel_products.json",
                    "endpoint": {
                        "name": "sales_funnel_products",
                        "http_method": "POST",
                        "logical_domain": "analytics",
                        "object_type": "sales_funnel_products",
                        "source": "wildberries",
                        "expected_payload_kind": "object",
                        "operational_date_semantics": "requested_business_day",
                        "pagination_semantics": "offset_limit",
                        "data_class": "operational",
                        "schema_version": "analytics-v3",
                    },
                    "source": "wildberries",
                    "schema_version": "analytics-v3",
                    "retrieved_at": "2026-08-24T10:30:00Z",
                    "operational_date": "2026-08-20",
                    "request_scope": {"selected_period": {"start": "2026-08-20", "end": "2026-08-20"}},
                    "source_identifier": "capture-request-0001",
                }
            ],
        },
    )
    _write_json(
        directory / "manifest.json",
        {
            "schema_version": REPLAY_BUNDLE_SCHEMA_VERSION,
            "case_id": CASE_ID,
            "files": [
                {
                    "path": "raw/sales_funnel_products.json",
                    "sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(),
                    "byte_length": payload_path.stat().st_size,
                }
            ],
        },
    )
    return directory


def test_loader_returns_verified_immutable_raw_objects_without_running_a_pipeline(tmp_path: Path) -> None:
    _capture_fixture(tmp_path)

    bundle = load_replay_bundle(CASE_ID, fixtures_root=tmp_path)

    assert bundle.metadata.classification == "real_raw_capture"
    assert bundle.manifest.schema_version == REPLAY_BUNDLE_SCHEMA_VERSION
    assert len(bundle.raw_objects) == 1
    raw_object = bundle.raw_objects[0]
    assert raw_object.object_id == OBJECT_ID
    assert raw_object.endpoint.name == "sales_funnel_products"
    assert raw_object.operational_date is not None
    assert raw_object.operational_date.isoformat() == "2026-08-20"
    assert raw_object.retrieved_at.isoformat() == "2026-08-24T10:30:00+00:00"
    assert isinstance(raw_object.payload, Mapping)
    with pytest.raises(TypeError):
        raw_object.payload["data"] = {}
    with pytest.raises(TypeError):
        cast(dict[str, Any], raw_object.payload["data"])["products"] = []


def test_loader_rejects_changed_raw_payload_by_sha256(tmp_path: Path) -> None:
    directory = _capture_fixture(tmp_path)
    (directory / "raw" / "sales_funnel_products.json").write_text('{"data":{"products":[]}}', encoding="utf-8")

    with pytest.raises(ReplayBundleIntegrityError, match="byte length|SHA-256"):
        load_replay_bundle(CASE_ID, fixtures_root=tmp_path)


def test_loader_rejects_metadata_manifest_payload_path_mismatch(tmp_path: Path) -> None:
    directory = _capture_fixture(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "raw/other_payload.json"
    _write_json(directory / "manifest.json", manifest)

    with pytest.raises(ReplayBundleSchemaError, match="payload paths"):
        load_replay_bundle(CASE_ID, fixtures_root=tmp_path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda metadata: metadata.__setitem__("classification", "synthetic"), "metadata schema"),
        (lambda metadata: metadata["raw_objects"][0].__setitem__("retrieved_at", "2026-08-24T10:30:00"), "metadata schema"),
        (lambda metadata: metadata["raw_objects"][0].__setitem__("source", "other"), "metadata schema"),
    ],
)
def test_loader_rejects_invalid_capture_metadata(tmp_path: Path, change: object, message: str) -> None:
    directory = _capture_fixture(tmp_path)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    cast(Any, change)(metadata)
    _write_json(directory / "metadata.json", metadata)

    with pytest.raises(ReplayBundleSchemaError, match=message):
        load_replay_bundle(CASE_ID, fixtures_root=tmp_path)


def test_loader_is_read_only_and_rejects_nonexistent_or_path_like_case_ids(tmp_path: Path) -> None:
    directory = _capture_fixture(tmp_path)
    before = {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}

    load_replay_bundle(CASE_ID, fixtures_root=tmp_path)

    after = {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    assert after == before
    with pytest.raises(ReplayBundleNotFoundError):
        load_replay_bundle("missing-case", fixtures_root=tmp_path)
    with pytest.raises(ReplayBundleNotFoundError):
        load_replay_bundle("../outside", fixtures_root=tmp_path)
