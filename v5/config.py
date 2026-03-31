"""Configuration management"""

from dataclasses import dataclass


@dataclass
class Config:
    """Global configuration"""
    cabinet_root: str = "d:/cabinets"
    debug: bool = False


def get_config() -> Config:
    """Load configuration from environment/files"""
    # TODO: Implement config loading
    return Config()
