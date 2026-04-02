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
    debug: bool = False


def get_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        cabinet_root=os.getenv("V5_CABINET_ROOT", "cabinets"),
        v5_namespace=os.getenv("V5_NAMESPACE", "v5"),
        shared_audit_input_root=os.getenv("V5_SHARED_AUDIT_INPUT", "v5/audit/input"),
        debug=str(os.getenv("V5_DEBUG", "false")).lower() in {"1", "true", "yes"},
    )
