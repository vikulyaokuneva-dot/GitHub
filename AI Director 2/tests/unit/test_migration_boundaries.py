from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_LEGACY_IMPORTS = ("wb_api_core", "v3", "report_v2", "src")


def test_new_domain_packages_do_not_import_legacy_code() -> None:
    package_root = PROJECT_ROOT / "packages"
    violations: list[str] = []

    for path in package_root.rglob("*.py"):
        if "compat" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for legacy_module in FORBIDDEN_LEGACY_IMPORTS:
            if f"import {legacy_module}" in source or f"from {legacy_module}" in source:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {legacy_module}")

    assert violations == []


def test_migration_inventory_keeps_writes_out_of_legacy_action_orchestrator() -> None:
    inventory = (PROJECT_ROOT / "docs" / "MIGRATION_INVENTORY.md").read_text(encoding="utf-8")

    assert "Policy, approval, dry-run and audit exist" in inventory
    assert "Reuse candidates only" in inventory
