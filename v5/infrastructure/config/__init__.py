"""Infrastructure config – path management and configuration"""

from pathlib import Path
from typing import Optional
from domain.cabinet import CabinetContext


def create_cabinet_directories(cabinet_ctx: CabinetContext) -> None:
    """Create all required directories for cabinet"""
    directories = [
        cabinet_ctx.raw_data_dir,
        cabinet_ctx.normalized_data_dir,
        cabinet_ctx.metrics_dir,
        cabinet_ctx.facts_dir,
        cabinet_ctx.reports_dir,
        cabinet_ctx.inputs_dir,
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def ensure_cabinet_paths(cabinet_ctx: CabinetContext) -> None:
    """Ensure all cabinet paths exist"""
    create_cabinet_directories(cabinet_ctx)
