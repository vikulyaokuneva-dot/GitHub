from __future__ import annotations

from pathlib import Path


def test_daily_workflow_persists_history_and_uploads_only_report_v2() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "daily.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    upload_block = workflow.split("- name: Upload report V2", maxsplit=1)[1]

    assert "actions/cache/restore@v4" in workflow
    assert "actions/cache/save@v4" in workflow
    assert "path: cabinets/${{ env.WB_SELLER_ID }}/history" in workflow
    assert "path: cabinets/${{ env.WB_SELLER_ID }}/artifacts/report_v2.pdf" in upload_block
    assert "artifacts/**" not in upload_block
    assert "report.pdf" not in upload_block.replace("report_v2.pdf", "")
    assert "audit" not in upload_block.lower()
