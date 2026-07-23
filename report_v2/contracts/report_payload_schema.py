from __future__ import annotations

from typing import Any, NotRequired, TypedDict


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
    status: str
    source: str
    owner_block: str
    target_date: str | None
    orders_count: int | None
    orders_amount: float | None
    orders_source: str
    orders_note: str
    orders_status: str
    orders_fallback: bool
    buyouts_count: int | None
    buyouts_amount: float | None
    buyouts_source: str
    buyouts_note: str
    buyouts_status: str
    sales_count: int | None
    sales_amount: float | None
    sales_source: str
    sales_note: str
    sales_status: str
    sales_fallback: bool


class FinanceFinalBlockV2(TypedDict, total=False):
    available: bool
    source: str
    owner_block: str
    status: str
    target_date: str | None
    actual_date: str | None
    date_aligned: bool | None
    gross_revenue: float | None
    sale_customer_revenue: float | None
    wb_realized_revenue: float | None
    realized_sales_qty: float | None
    realized_sales_revenue: float | None
    seller_payout: float | None
    wb_commission: float | None
    deliveries_qty: float | None
    returns_qty: float | None
    logistics: float | None
    logistics_amount: float | None
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
    history_comparison: dict[str, dict[str, str]]
    status: str
    message: str


class AdsRowV2(TypedDict, total=False):
    label: str
    value: str
    source: str
    status: str
    note: str


class AdsSectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    rows: list[AdsRowV2]
    status: str
    message: str


class AdsEfficiencySectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    status: str
    source: str
    message: str
    spend: float | None
    impressions: int | None
    clicks: int | None
    ctr: float | None
    cpc: float | None
    cpm: float | None
    ad_orders: float | None
    ad_revenue: float | None
    ad_buyouts: float | None
    drr: float | None
    roas: float | None
    romi: float | None
    cpo: float | None
    profit_from_ads: float | None
    wasted_spend: float | None
    inefficient_items_count: int | None
    top_profitable_queries: list[dict[str, Any]]
    top_unprofitable_queries: list[dict[str, Any]]
    high_potential_queries: list[dict[str, Any]]
    warnings: list[WarningItemV2]
    metric_rows: list[AdsRowV2]
    loss_rows: list[dict[str, Any]]
    opportunity_rows: list[dict[str, Any]]
    recommendations: list[str]


class QueryProfitabilitySectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    status: str
    source: str
    message: str
    top_loss_queries: list[dict[str, Any]]
    weak_queries: list[dict[str, Any]]
    top_performing_queries: list[dict[str, Any]]
    growth_hypotheses: list[dict[str, Any]]
    recommendations: list[str]


class SkuHealthItemV2(TypedDict, total=False):
    sku: str
    nm_id: str | None
    article: str | None
    name: str | None
    score: float | None
    attention_score: float | None
    health_score: float | None
    reason: str
    metric_value: float | str | None
    recommended_action: str
    status: str
    source: str


class SkuHealthSummaryV2(TypedDict, total=False):
    total_skus: int | None
    healthy_count: int | None
    growth_count: int | None
    risk_count: int | None
    liquidation_count: int | None
    dead_stock_count: int | None
    ad_inefficiency_count: int | None
    conversion_drop_count: int | None
    logistics_risk_count: int | None


class SkuHealthScoreV2(TypedDict, total=False):
    value: float | None
    status: str
    comment: str


class SkuHealthWatchlistsV2(TypedDict, total=False):
    top_growth: list[SkuHealthItemV2]
    top_risk: list[SkuHealthItemV2]
    dead_stock: list[SkuHealthItemV2]
    ad_inefficiency: list[SkuHealthItemV2]
    conversion_drop: list[SkuHealthItemV2]
    logistics_risk: list[SkuHealthItemV2]


class SkuHealthSectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    status: str
    source: str
    message: str
    summary: SkuHealthSummaryV2
    health_score: SkuHealthScoreV2
    watchlists: SkuHealthWatchlistsV2
    alerts: list[SkuHealthItemV2]
    daily_dynamics: dict[str, Any]
    warnings: list[WarningItemV2]
    summary_rows: list[DisplayRowV2]
    risk_rows: list[SkuHealthItemV2]
    growth_rows: list[SkuHealthItemV2]
    attention_rows: list[SkuHealthItemV2]


class ProfitSkuItemV2(TypedDict, total=False):
    sku: str
    nm_id: str | None
    name: str | None
    revenue: float | None
    profit: float | None
    profit_margin: float | None
    contribution_share: float | None
    status: str
    recommended_action: str
    source: str


class ProfitContributionSummaryV2(TypedDict, total=False):
    total_profit: float | None
    total_revenue: float | None
    top_sku_share: float | None
    loss_sku_count: int | None


class ProfitContributionSectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    status: str
    source: str
    message: str
    summary: ProfitContributionSummaryV2
    top_profit_skus: list[ProfitSkuItemV2]
    loss_skus: list[ProfitSkuItemV2]
    sku_pnl: list[ProfitSkuItemV2]
    warnings: list[WarningItemV2]
    summary_rows: list[DisplayRowV2]


class AbcSkuItemV2(TypedDict, total=False):
    sku: str
    nm_id: str | None
    name: str | None
    category: str
    metric_value: float | None
    cumulative_share: float | None
    status: str


class AbcSectionSkuItemV2(TypedDict, total=False):
    sku: str
    nm_id: str | None
    name: str | None
    abc_class: str
    revenue: float | None
    profit: float | None
    profit_margin: float | None
    ad_spend: float | None
    reason: str
    recommended_action: str
    source: str


class AbcAnalysisSummaryV2(TypedDict, total=False):
    total_skus: int | None
    category_A_count: int | None
    category_B_count: int | None
    category_C_count: int | None
    category_A_share: float | None
    category_B_share: float | None
    category_C_share: float | None
    c_skus_with_ads_count: int | None
    low_margin_skus_count: int | None
    critical_a_skus_count: int | None


class AbcAnalysisSectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    status: str
    source: str
    message: str
    summary: AbcAnalysisSummaryV2
    categories: dict[str, list[AbcSkuItemV2]]
    warnings: list[WarningItemV2]
    summary_rows: list[DisplayRowV2]


class AbcSectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    status: str
    source: str
    message: str
    summary: AbcAnalysisSummaryV2
    top_a_skus: list[AbcSectionSkuItemV2]
    critical_a_skus: list[AbcSectionSkuItemV2]
    c_skus_with_ads: list[AbcSectionSkuItemV2]
    low_margin_skus: list[AbcSectionSkuItemV2]
    all_skus: list[AbcSectionSkuItemV2]
    recommendations: list[str]
    warnings: list[WarningItemV2]
    summary_rows: list[DisplayRowV2]


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
    stale: bool
    stale_reason: str | None
    source_actual_date: str | None
    cache_age_seconds: float | None
    cache_path: str | None
    cache_fallback_used: bool


class LiveOperationalBlockV2(TypedDict, total=False):
    status: str
    orders: LiveMetricBlockV2
    sales: LiveMetricBlockV2
    stocks: LiveMetricBlockV2


class StockSectionV2(TypedDict, total=False):
    title: str
    subtitle: str
    available: bool
    status: str
    source: str
    message: str
    stock_wb_qty: int | None
    stock_mp_qty: int | None
    stock_total_qty: int | None
    stock_value: float | None
    sku_rows_count: int | None
    rows: list[DisplayRowV2]
    warnings: list[WarningItemV2]


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
    ads_efficiency_section: AdsEfficiencySectionV2
    ads_section: AdsSectionV2
    query_profitability_section: NotRequired[QueryProfitabilitySectionV2]
    sku_health_section: NotRequired[SkuHealthSectionV2]
    profit_contribution_section: NotRequired[ProfitContributionSectionV2]
    abc_section: NotRequired[AbcSectionV2]
    abc_analysis_section: NotRequired[AbcAnalysisSectionV2]
    finance_final: FinanceFinalBlockV2
    finance_section: SectionV2
    finance_alignment_notice: FinanceAlignmentNoticeV2
    live_operational: LiveOperationalBlockV2
    live_section: SectionV2
    stock_section: NotRequired[StockSectionV2]
    warnings: list[WarningItemV2]
    source_flags: SourceFlagsV2
    diagnostics: DiagnosticsV2
    debug_summary: NotRequired[dict[str, object]]
