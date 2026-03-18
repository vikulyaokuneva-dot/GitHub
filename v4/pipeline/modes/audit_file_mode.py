"""Audit file mode descriptor and policy helpers.

Input: none.
Output: static mode capabilities and source/file policies.
Does not execute file parsing.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.contracts import RunMode


@dataclass(frozen=True)
class ModeDescriptor:
    """Declarative mode profile used by orchestration layers."""

    mode: RunMode
    required_file_inputs: tuple[str, ...]
    optional_file_inputs: tuple[str, ...]
    required_raw_sources: tuple[str, ...]
    optional_raw_sources: tuple[str, ...]
    available_blocks: tuple[str, ...]
    disclaimer: str


MODE_DESCRIPTOR = ModeDescriptor(
    mode=RunMode.AUDIT_FILE,
    required_file_inputs=("daily_report",),
    optional_file_inputs=("funnel_report", "ads_report"),
    required_raw_sources=("realization",),
    optional_raw_sources=("orders", "sales", "stocks", "funnel", "ads"),
    available_blocks=(
        "file_ingestion",
        "normalization",
        "metrics",
        "facts",
        "decisions",
        "outputs",
        "diagnostics",
    ),
    disclaimer="Отчет построен в audit_file_mode; выводы ограничены доступными файлами.",
)


def describe() -> dict[str, object]:
    return {
        "mode": MODE_DESCRIPTOR.mode.value,
        "required_file_inputs": list(MODE_DESCRIPTOR.required_file_inputs),
        "optional_file_inputs": list(MODE_DESCRIPTOR.optional_file_inputs),
        "required_raw_sources": list(MODE_DESCRIPTOR.required_raw_sources),
        "optional_raw_sources": list(MODE_DESCRIPTOR.optional_raw_sources),
        "available_blocks": list(MODE_DESCRIPTOR.available_blocks),
        "disclaimer": MODE_DESCRIPTOR.disclaimer,
    }


def get_required_file_inputs() -> tuple[str, ...]:
    return MODE_DESCRIPTOR.required_file_inputs


def get_optional_file_inputs() -> tuple[str, ...]:
    return MODE_DESCRIPTOR.optional_file_inputs


def get_required_raw_sources() -> tuple[str, ...]:
    return MODE_DESCRIPTOR.required_raw_sources


def get_optional_raw_sources() -> tuple[str, ...]:
    return MODE_DESCRIPTOR.optional_raw_sources


def is_allowed_source(source_name: str) -> bool:
    allowed = set(MODE_DESCRIPTOR.required_raw_sources) | set(MODE_DESCRIPTOR.optional_raw_sources)
    return str(source_name).strip() in allowed


def get_audit_mode_flags() -> dict[str, object]:
    return {
        "mode": MODE_DESCRIPTOR.mode.value,
        "api_ingestion_enabled": False,
        "file_ingestion_only": True,
        "limited_mode": True,
        "disclaimer": MODE_DESCRIPTOR.disclaimer,
        "required_file_inputs": list(MODE_DESCRIPTOR.required_file_inputs),
        "optional_file_inputs": list(MODE_DESCRIPTOR.optional_file_inputs),
        "required_raw_sources": list(MODE_DESCRIPTOR.required_raw_sources),
        "optional_raw_sources": list(MODE_DESCRIPTOR.optional_raw_sources),
    }
