from __future__ import annotations

from typing import NotRequired, TypedDict


class WarningItemV2(TypedDict, total=False):
    code: str
    message: str
    level: str
    block: str


class MetaBlockV2(TypedDict, total=False):
    contract_version: str
    seller_id: str
    report_date: str
    operational_date: str
    snapshot_source_mode: str
    debug_available: bool


class CabinetCommerceBlockV2(TypedDict, total=False):
    available: bool
    source: str
    owner_block: str
    target_date: str | None
    orders_count: int | None
    orders_amount: float | None
    buyouts_count: int | None
    buyouts_amount: float | None


class FinanceFinalBlockV2(TypedDict, total=False):
    available: bool
    source: str
    owner_block: str
    status: str
    target_date: str | None
    actual_date: str | None
    date_aligned: bool | None
    gross_revenue: float | None
    seller_payout: float | None
    wb_commission: float | None
    logistics: float | None
    storage: float | None
    acquiring: float | None
    penalties: float | None
    deductions: float | None
    tax: float | None


class FinanceAlignmentNoticeV2(TypedDict, total=False):
    state: str
    title: str
    lines: list[str]
    source: str
    target_date: str | None
    actual_date: str | None


class HeroKpiCardV2(TypedDict, total=False):
    label: str
    value: str
    subvalue: str
    status: str


class HeroBlockV2(TypedDict, total=False):
    title: str
    subtitle: str
    cards: list[HeroKpiCardV2]
    data_status: str
    data_status_message: str


class DisplayRowV2(TypedDict, total=False):
    label: str
    value: str
    note: str
    status: str


class SectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    rows: list[DisplayRowV2]
    status: str


class FunnelStageRowV2(TypedDict, total=False):
    stage: str
    value: str
    source: str
    status: str
    note: str


class FunnelSectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    rows: list[FunnelStageRowV2]
    status: str
    message: str


class LiveMetricBlockV2(TypedDict, total=False):
    available: bool
    source: str
    target_date: str | None
    count: int | None
    amount: float | None
    total_units: int | None
    snapshot_date: str | None
    snapshot_kind: str | None
    operational_date_reference: str | None


class LiveOperationalBlockV2(TypedDict, total=False):
    status: str
    orders: LiveMetricBlockV2
    sales: LiveMetricBlockV2
    stocks: LiveMetricBlockV2


class SourceFlagsV2(TypedDict, total=False):
    snapshot_present: bool
    debug_present: bool
    snapshot_source_mode: str
    buyouts_owner: str
    buyouts_source: str
    warnings_count: int


class DiagnosticsRowV2(TypedDict, total=False):
    code: str
    level: str
    block: str
    message: str


class SourceFlagRowV2(TypedDict, total=False):
    name: str
    value: str
    status: str


class DiagnosticsV2(TypedDict, total=False):
    warnings: list[DiagnosticsRowV2]
    source_flags: list[SourceFlagRowV2]
    warnings_count: int


class ReportPayloadV2(TypedDict):
    meta: MetaBlockV2
    hero: HeroBlockV2
    cabinet_commerce: CabinetCommerceBlockV2
    commerce_section: SectionV2
    funnel_section: FunnelSectionV2
    finance_final: FinanceFinalBlockV2
    finance_section: SectionV2
    finance_alignment_notice: FinanceAlignmentNoticeV2
    live_operational: LiveOperationalBlockV2
    live_section: SectionV2
    warnings: list[WarningItemV2]
    source_flags: SourceFlagsV2
    diagnostics: DiagnosticsV2
    debug_summary: NotRequired[dict[str, object]]
