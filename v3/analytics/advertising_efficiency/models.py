from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class AdvertisingSignal:
    type: str
    entity: str
    severity: str
    impact: float
    confidence: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AdvertisingEfficiencyOutput:
    seller_id: str
    report_date: str
    status: str
    analysis_mode: str
    data_quality_status: str
    warnings: List[Dict[str, Any]]
    summary: Dict[str, Any]
    sku_performance: List[Dict[str, Any]]
    query_performance: List[Dict[str, Any]]
    signals: List[AdvertisingSignal]

    def to_dict(self) -> Dict[str, Any]:
        signal_rows = [row.to_dict() for row in self.signals]
        query_rows = list(self.query_performance)
        sku_rows = list(self.sku_performance)
        payload = {
            "seller_id": self.seller_id,
            "report_date": self.report_date,
            "status": self.status,
            "analysis_mode": self.analysis_mode,
            "data_quality_status": self.data_quality_status,
            "warnings": list(self.warnings),
            "summary": dict(self.summary),
            "sku_performance": sku_rows,
            "query_performance": query_rows,
            "signals": signal_rows,
        }
        payload["items"] = sku_rows
        payload["queries"] = query_rows
        return payload
