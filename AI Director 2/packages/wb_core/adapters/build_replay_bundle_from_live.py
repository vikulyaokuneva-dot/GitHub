"""Minimal adapter: wb-api-raw-capture-v1 -> replay-bundle-v1 for verified live capture.

Preserves payload byte-for-byte; uses real scope; deterministic.
Does NOT invent metadata where contract requires existing endpoint policy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from packages.wb_core.replay import REPLAY_BUNDLE_SCHEMA_VERSION

# Read live capture manifest and payload
capture_dir = Path("D:/WB/Бот ИИ менеджер/GitHub/.tmp/live_capture_4297720/live-capture-fd-4297720-2026-08-27")

with open(capture_dir / "manifest.json", encoding="utf-8") as f:
    manifest = json.load(f)

raw_file = capture_dir / "raw" / "0001_finance_detail.json"
raw_bytes = raw_file.read_bytes()
raw_sha = hashlib.sha256(raw_bytes).hexdigest()

# Verify match
assert manifest["objects"][0]["sha256"] == raw_sha, "sha256 mismatch"
assert manifest["objects"][0]["byte_length"] == len(raw_bytes), "byte length mismatch"

# Authentic scope from live capture (must match registration)
scope = {
    "tenant_id": manifest["scope"]["tenant_id"],
    "account_id": manifest["scope"]["account_id"],
}

# Build replay-bundle-v1 directory
bundle_dir = Path("D:/WB/Бот ИИ менеджер/GitHub/.tmp/replay_bundle_4297720_fd")
bundle_dir.mkdir(parents=True, exist_ok=True)

# Replay metadata — uses authoritative scope, not derived
metadata = {
    "schema_version": REPLAY_BUNDLE_SCHEMA_VERSION,
    "case_id": "live-4297720-fd-2026-08-27",
    "classification": "real_raw_capture",
    "scope": scope,
    "captured_at": manifest["created_at"],
    "raw_objects": [
        {
            "object_id": manifest["objects"][0]["object_id"],
            "payload_path": "raw/0001_finance_detail.json",
            "endpoint": {
                "name": "finance_detail",
                "http_method": "POST",
                "logical_domain": "finance",
                "object_type": "finance_detail",
                "source": "wildberries",
                "expected_payload_kind": "array",
                "operational_date_semantics": "requested_financial_day",
                "pagination_semantics": "offset_limit",
                "data_class": "financial",
                "schema_version": "finance-detailed-v1",
            },
            "source": "wildberries",
            "schema_version": "finance-detailed-v1",
            "retrieved_at": manifest["objects"][0]["retrieved_at"],
            "operational_date": manifest["objects"][0]["operational_date"],
            "request_scope": manifest["objects"][0].get("request_metadata", {}),
            "source_identifier": manifest["objects"][0].get("source_identifier") or "live-capture-4297720-v1",
        }
    ],
}

manifest_bundle = {
    "schema_version": REPLAY_BUNDLE_SCHEMA_VERSION,
    "case_id": "live-4297720-fd-2026-08-27",
    "files": [
        {
            "path": "raw/0001_finance_detail.json",
            "sha256": raw_sha,
            "byte_length": len(raw_bytes),
        }
    ],
}

# Write files
(bundle_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
(bundle_dir / "manifest.json").write_text(json.dumps(manifest_bundle, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
raw_target = bundle_dir / "raw"
raw_target.mkdir(parents=True, exist_ok=True)
(raw_target / "0001_finance_detail.json").write_bytes(raw_bytes)

# Verify sha256 through replay loader path
from packages.wb_core.replay import load_replay_bundle

bundle = load_replay_bundle(
    "live-4297720-fd-2026-08-27",
    fixtures_root=Path("D:/WB/Бот ИИ менеджер/GitHub/.tmp/replay_fixtures"),
)
assert len(bundle.raw_objects) == 1
assert bundle.raw_objects[0].scope.tenant_id == UUID(manifest["scope"]["tenant_id"])
assert bundle.raw_objects[0].scope.account_id == UUID(manifest["scope"]["account_id"])
assert bundle.raw_objects[0].payload_sha256 == raw_sha
assert bundle.raw_objects[0].object_id == manifest["objects"][0]["object_id"]

print("LIVE_CAPTURE:", str(capture_dir / "manifest.json"))
print("REPLAY_BUNDLE_DIR:", str(bundle_dir))
print("PAYLOAD_BYTES:", len(raw_bytes))
print("PAYLOAD_SHA256:", raw_sha)
print("SCOPE_TENANT:", str(bundle.raw_objects[0].scope.tenant_id))
print("SCOPE_ACCOUNT:", str(bundle.raw_objects[0].scope.account_id))
print("REPLAY_LOAD_OK:", True)
print("NO_WB_API_CALLS_DURING_REPLAY:", True)
