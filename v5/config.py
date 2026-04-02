"""Configuration management."""

from dataclasses import dataclass
import os


@dataclass
class Config:
    """Global v5 runtime configuration."""

    # Base cabinets root in repository (shared with older versions).
    cabinet_root: str = "cabinets"
    # Dedicated namespace to avoid collisions with v3/v4 artifacts.
    v5_namespace: str = "v5"
    # Shared audit input root (fallback if cabinet-specific input is empty).
    shared_audit_input_root: str = "v5/audit/input"
    # Use v2-compatible ingestion path as active daily source layer.
    use_v2_compat_ingestion: bool = True
    # v2-compatible manual ads fallback folder.
    v2_manual_ads_dir: str = "data/manual_ads"
    # v2-compatible finance lag behavior.
    wb_max_finance_lag_days: int = 3
    # Financial tax rate used by v2 metrics for comparison counts.
    wb_tax_rate: float = 0.06
    debug: bool = False


def get_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        cabinet_root=os.getenv("V5_CABINET_ROOT", "cabinets"),
        v5_namespace=os.getenv("V5_NAMESPACE", "v5"),
        shared_audit_input_root=os.getenv("V5_SHARED_AUDIT_INPUT", "v5/audit/input"),
        use_v2_compat_ingestion=str(
            os.getenv("V5_USE_V2_COMPAT_INGESTION", "true")
        ).lower() in {"1", "true", "yes"},
        v2_manual_ads_dir=os.getenv("V5_V2_MANUAL_ADS_DIR", "data/manual_ads"),
        wb_max_finance_lag_days=int(os.getenv("WB_MAX_FINANCE_LAG_DAYS", "3")),
        wb_tax_rate=float(os.getenv("WB_TAX_RATE", "0.06")),
        debug=str(os.getenv("V5_DEBUG", "false")).lower() in {"1", "true", "yes"},
    )
