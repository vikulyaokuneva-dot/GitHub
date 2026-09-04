from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from packages.compat.legacy_snapshot_parity import (
    DEFAULT_FIXTURE_DIRECTORY,
    FixtureIntegrityError,
    FixtureParityError,
    assert_snapshot_parity,
    canonical_sha256,
    load_golden_fixture,
)

SENSITIVE_FIELD_PATTERN = re.compile(r"(?:api[_-]?key|authorization|password|secret|token)", re.IGNORECASE)
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?:bearer\s+|sk-[A-Za-z0-9]|(?:api[_-]?key|authorization|password|secret|token)\s*[:=])",
    re.IGNORECASE,
)


def _json_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield str(key)
            yield from _json_keys(nested_value)


def _json_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested_value in value.values():
            yield from _json_strings(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _json_strings(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _json_keys(nested_value)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def test_golden_fixture_is_synthetic_and_has_no_credential_field_names() -> None:
    fixture = load_golden_fixture()

    manifest = cast(dict[str, Any], fixture.manifest)
    assert manifest["classification"] == "synthetic"
    field_names = [*_json_keys(fixture.manifest), *_json_keys(fixture.raw_bundle), *_json_keys(fixture.expected_snapshot)]
    assert not [name for name in field_names if SENSITIVE_FIELD_PATTERN.search(name)]
    string_values = [*_json_strings(fixture.manifest), *_json_strings(fixture.raw_bundle), *_json_strings(fixture.expected_snapshot)]
    assert not [value for value in string_values if SENSITIVE_VALUE_PATTERN.search(value)]


def test_golden_fixture_manifest_hashes_validate() -> None:
    fixture = load_golden_fixture()
    manifest = cast(dict[str, Any], fixture.manifest)

    assert manifest["fixture_id"] == "wb_core_snapshot_v1"
    assert manifest["snapshot_context"]["timezone"] == "Europe/Moscow"


def test_legacy_snapshot_replay_matches_immutable_expected_snapshot() -> None:
    snapshot = cast(dict[str, Any], assert_snapshot_parity())

    assert snapshot["seller_id"] == "synthetic_seller_001"
    assert snapshot["cabinet_commerce_daily"]["orders_count"] == 5.0
    assert snapshot["finance_final_daily"]["seller_payout"] == 1410.0
    assert snapshot["funnel_daily"]["status"] == "partial"


def test_raw_fixture_change_without_manifest_hash_update_fails_integrity_check(tmp_path: Path) -> None:
    fixture_directory = tmp_path / "fixture"
    shutil.copytree(DEFAULT_FIXTURE_DIRECTORY, fixture_directory)
    raw_path = fixture_directory / "raw_bundle.json"
    raw_bundle = json.loads(raw_path.read_text(encoding="utf-8"))
    raw_bundle["orders"]["rows_raw"][0]["priceWithDisc"] = 801.0
    _write_json(raw_path, raw_bundle)

    with pytest.raises(FixtureIntegrityError, match="raw_bundle"):
        load_golden_fixture(fixture_directory)


def test_expected_snapshot_change_with_updated_hash_fails_legacy_parity(tmp_path: Path) -> None:
    fixture_directory = tmp_path / "fixture"
    shutil.copytree(DEFAULT_FIXTURE_DIRECTORY, fixture_directory)
    expected_path = fixture_directory / "expected_snapshot.json"
    expected_snapshot = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_snapshot["finance_final_daily"]["seller_payout"] = 1409.0
    _write_json(expected_path, expected_snapshot)

    manifest_path = fixture_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"]["expected_snapshot"] = canonical_sha256(expected_snapshot)
    _write_json(manifest_path, manifest)

    with pytest.raises(FixtureParityError, match=r"\$\.finance_final_daily\.seller_payout"):
        assert_snapshot_parity(load_golden_fixture(fixture_directory))
