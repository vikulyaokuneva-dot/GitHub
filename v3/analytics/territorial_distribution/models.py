from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class DistributionCoefficients:
    localization_range_min: float
    localization_range_max: float
    ktr: float
    krp: float


@dataclass
class SkuDistributionMetrics:
    sku: str
    total_orders: float
    local_orders: float
    localization_share: float | None
    ktr: float
    krp: float
    average_retail_price: float | None
    irp_penalty_per_order: float | None
    estimated_irp_penalty_total: float
    distribution_state: str
    distribution_state_label_ru: str
    effective_date_applied: bool
    confidence: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DistributionEngineOutput:
    seller_id: str
    report_date: str
    status: str
    warnings: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    summary: Dict[str, Any]
    signals: List[Dict[str, Any]]
    sku_metrics: List[SkuDistributionMetrics]

    def to_dict(self) -> Dict[str, Any]:
        items = [row.to_dict() for row in self.sku_metrics]
        return {
            'seller_id': self.seller_id,
            'report_date': self.report_date,
            'status': self.status,
            'warnings': list(self.warnings),
            'metadata': dict(self.metadata),
            'summary': dict(self.summary),
            'signals': list(self.signals),
            'sku_metrics': items,
            'skus': items,
            'items': items,
        }