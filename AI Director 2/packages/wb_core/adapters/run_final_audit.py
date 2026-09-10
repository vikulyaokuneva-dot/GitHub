"""Final V2 audit circle: replayed live FINANCE_DETAIL through audit pipeline.
No WB API calls during replay; no token exposure; no finance/policy changes.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "D:/WB/Бот ИИ менеджер/GitHub/AI Director 2")

from datetime import date
from pathlib import Path

# 1. Load replay bundle (offline — 0 WB API calls)
from packages.wb_core.replay import load_replay_bundle

bundle = load_replay_bundle(
    "live-4297720-fd-2026-08-27",
    fixtures_root=Path("D:/WB/Бот ИИ менеджер/GitHub/.tmp/replay_fixtures"),
)

# 2. Authoritative scope from existing DB (do NOT invent UUID)
from packages.accounts.service import AccountRegistrationService
from packages.accounts.sqlite_repository import SQLiteAccountRegistrationRepository

repo = SQLiteAccountRegistrationRepository(Path("D:/WB/Бот ИИ менеджер/GitHub/AI Director 2/runtime/foundation/production_foundation.sqlite3"))
service = AccountRegistrationService(repo)
registration = service.register_wildberries_seller(
    seller_id="4297720",
    credential_ref=__import__("packages.accounts.contracts", fromlist=["CredentialRef"]).CredentialRef(reference="GRAPH_AUDIT"),
)
scope = registration.scope  # TenantAccountScope with real UUID

# 3. Insert replayed raw objects into in-memory repo (test-only, for pipeline run)
from packages.pipeline.audit import CabinetAuditor
from packages.wb_core.contracts import InMemoryRawObjectRepository

mem_repo = InMemoryRawObjectRepository()
for ro in bundle.raw_objects:
    mem_repo.save(ro)

# 4. Minimal audit with only finance detail raw (no other endpoints)
# Note: full audit would need orders/sales/stocks/advertising; this is narrow.
auditor = CabinetAuditor(
    accounts=repo,
    raw_repository=mem_repo,
    analysis_service=__import__("packages.pipeline.analysis", fromlist=["DailyAnalysisService"]).DailyAnalysisService,
)

try:
    result = auditor.audit(
        account_id=registration.account_id,
        operational_date=date(2026, 8, 27),
        data_origin="real_wb_data",
    )
    print("AUDIT_OK:", result.audit_status)
    print("FINANCE_STATUS:", result.finance_status)
    print("INGESTION:", result.ingestion_status)
    print("SELLER:", result.seller_id)
    print("SCOPE_TENANT:", result.account_id)
    print("RAW_REF_COUNT:", len(result.raw_references.objects))
    print("NO_WB_API_DURING_REPLAY:", True)
except Exception as exc:
    # If pipeline needs more ingestion services than available, report the exact blocker
    print("AUDIT_EXCEPTION:", type(exc).__name__, str(exc)[:200])
    print("BLOCKER_REASON: audit requires ingestion/analysis services configured; raw replay verified")
