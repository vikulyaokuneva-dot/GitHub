from __future__ import annotations

from pathlib import Path


def test_daily_workflow_persists_history_and_uploads_only_report_v2() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "daily.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    upload_block = workflow.split("- name: Upload report V2", maxsplit=1)[1]

    assert "actions/cache/restore@v4" in workflow
    assert "actions/cache/save@v4" in workflow
    assert "cabinets/${{ env.WB_SELLER_ID }}/history" in workflow
    assert "cabinets/${{ env.WB_SELLER_ID }}/artifacts/wb_api_core/cache" in workflow
    assert 'python -m v3.history.api_history_backfill --seller "${WB_SELLER_ID}" --date "${CORE_RUN_DATE}"' in workflow
    assert workflow.index("python -m v3.history.api_history_backfill") < workflow.index("python -m v3.entry daily")
    assert "path: cabinets/${{ env.WB_SELLER_ID }}/artifacts/report_v2.pdf" in upload_block
    assert "artifacts/**" not in upload_block
    assert "report.pdf" not in upload_block.replace("report_v2.pdf", "")
    assert "audit" not in upload_block.lower()
