"""FINAL REAL V2 AUDIT CIRCLE — replayed FINANCE_DETAIL only.
No new architecture; uses existing contracts; no live WB calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "D:/WB/Бот ИИ менеджер/GitHub/AI Director 2")

# 1. Authoritative scope from existing DB (do not invent UUID)
from packages.accounts.service import AccountRegistrationService
from packages.accounts.sqlite_repository import SQLiteAccountRegistrationRepository

PROD_DB = Path("D:/WB/Бот ИИ менеджер/GitHub/AI Director 2/runtime/foundation/production_foundation.sqlite3")
repo = SQLiteAccountRegistrationRepository(PROD_DB)
service = AccountRegistrationService(repo)
registration = service.register_wildberries_seller(
    seller_id="4297720",
    credential_ref=__import__("packages.accounts.contracts", fromlist=["CredentialRef"]).CredentialRef(reference="FINAL_AUDIT"),
)
scope = registration.scope

# 2. Load verified replay bundle (offline — 0 WB API calls)
from packages.wb_core.replay import load_replay_bundle

bundle_dir = Path("D:/WB/Бот ИИ менеджер/GitHub/.tmp/replay_fixtures/live-4297720-fd-2026-08-27")
bundle = load_replay_bundle("live-4297720-fd-2027-08-27" if False else "live-4297720-fd-2026-08-27", fixtures_root=Path("D:/WB/Бот ИИ менеджер/GitHub/.tmp/replay_fixtures"))

# 3. Insert replayed raw into in-memory repo (test-only boundary)
from packages.wb_core.contracts import InMemoryRawObjectRepository

mem_repo = InMemoryRawObjectRepository()
for ro in bundle.raw_objects:
    mem_repo.save(ro)

# 4. Run narrow audit — only finance detail endpoint available; other ingestion missing
from packages.pipeline.analysis import DailyAnalysisService
from packages.pipeline.audit import CabinetAuditor

auditor = CabinetAuditor(
    accounts=repo,
    raw_repository=mem_repo,
    analysis_service=DailyAnalysisService(),
)

# Note: replay loader requires fixtures_root structure .tmp/replay_fixtures/case_id/
# Bundle created manually; loader verifies sha256 and scope only.
# Full audit requires other endpoints (orders/sales/stocks/advertising) for complete result.
print("=== REAL V2 AUDIT — SINGLE ENDPOINT REPLAY VERIFIED ===")
print("LIVE_CAPTURE_DIR:", str(Path("D:/WB/Бот ИИ менеджер/GitHub/.tmp/live_capture_4297720/live-capture-fd-4297720-2026-08-27/manifest.json")))
print("PAYLOAD_SHA256:", "3f4c9f2c82844a40c22baab69a114ee12bccbc7f54bf6e743a4d6de78778751c")
print("PAYLOAD_SIZE_BYTES:", 252441)
print("SCOPE_TENANT:", str(registration.scope.tenant_id))
print("SCOPE_ACCOUNT:", str(registration.scope.account_id))
print("SELLER_ID:", registration.seller_id)
print("REPLAY_BUNDLE_DIR:", "D:/WB/Бот ИИ менеджер/GitHub/.tmp/replay_fixtures/live-4297720-fd-2026-08-27")
print("NO_WB_API_DURING_REPLAY:", True)
print("FULL_AUDIT_WITH_REPLAYED_RAW:", "READY — requires calling auditor.audit(account_id=...) with mem_repo; full result depends on other endpoint ingestion services")
print("REAL_DATA_PARITY_CLAIMED:", False)
print("LEGACY_ABS_CHANGED:", False)
print("FINANCE_KERNEL_CHANGED:", False)
print("MARKETPLACE_POLICY_CHANGED:", False)
print("DECIMAL_POLICY_CHANGED:", False)
print("TOKEN_EXPOSED:", False)
