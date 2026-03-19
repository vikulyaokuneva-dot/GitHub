"""Raw ingestion contracts.

Input: run context and per-source raw payloads.
Output: RawBundle and IngestionResult.
Does not normalize records and does not compute KPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class RunMode(str, Enum):
    """Top-level execution modes for v4 runtime."""

    DAILY_API = "daily_api_mode"
    AUDIT_FILE = "audit_file_mode"


class SourceStatusCode(str, Enum):
    """Canonical source ingestion statuses."""

    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"
    ERROR = "error"
    NOT_IMPLEMENTED = "not_implemented"


class SourceKind(str, Enum):
    """Source transport family used to load payload."""

    API = "api"
    FILE = "file"
    FALLBACK = "fallback"
    UNKNOWN = "unknown"


def coerce_iso_date(value: date | str | None) -> str | None:
    """Convert date-like values to ISO string.

    Keeps None as None to preserve missing semantics.
    """

    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


@dataclass(frozen=True)
class RunContext:
    """Execution context shared across ingestion pipeline.

    Rule: missing values remain None and are not coerced to 0.
    """

    seller_id: str
    cabinet_name: str | None
    mode: RunMode
    requested_date: date | str | None
    resolved_date: date | str | None
    timezone: str
    wb_api_token_present: bool
    cabinet_id: str | None = None
    dry_run: bool = False
    output_dir: str | None = None
    feature_flags: dict[str, bool] = field(default_factory=dict)
    path_labels: dict[str, str] = field(default_factory=dict)
    input_path_label: str | None = None

    @property
    def requested_date_iso(self) -> str | None:
        return coerce_iso_date(self.requested_date)

    @property
    def resolved_date_iso(self) -> str | None:
        return coerce_iso_date(self.resolved_date)


@dataclass
class SourceStatus:
    """Health and debug metadata for a single source load."""

    source_name: str
    kind: SourceKind
    status: SourceStatusCode
    is_required: bool
    rows_loaded: int | None = None
    endpoint: str | None = None
    requested_date: str | None = None
    resolved_date: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawSourcePayload:
    """Raw payload + source status for one contour."""

    source_name: str
    payload: Any
    status: SourceStatus


@dataclass
class RawBundle:
    """Raw ingestion output.

    Contains source payloads exactly as loaded; no normalization or KPI.
    """

    run_context: RunContext
    sources: dict[str, RawSourcePayload] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def context(self) -> RunContext:
        """Back-compat alias for previous skeleton naming."""

        return self.run_context

    @property
    def source_status(self) -> dict[str, SourceStatus]:
        """Back-compat alias: source_name -> SourceStatus."""

        return {name: payload.status for name, payload in self.sources.items()}

    @property
    def payloads(self) -> dict[str, Any]:
        """Back-compat alias: source_name -> raw payload."""

        return {name: payload.payload for name, payload in self.sources.items()}


@dataclass
class IngestionResult:
    """Result object returned by input stage and bundle builders."""

    raw_bundle: RawBundle
    source_flags: dict[str, SourceStatusCode] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
