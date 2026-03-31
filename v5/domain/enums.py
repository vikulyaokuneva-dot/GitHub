"""
Domain enumerations.
"""

from enum import Enum


class RunMode(Enum):
    """Execution mode"""
    DAILY_API = "daily"      # Pull from WB API
    REPORT_AUDIT = "audit"   # Process uploaded reports


class DataSource(Enum):
    """Data source identifier"""
    WB_API = "api"
    FILE_REPORT = "report"
    CACHED = "cache"


class ProcessingPhase(Enum):
    """Current processing phase"""
    LOADING = "loading"
    NORMALIZING = "normalizing"
    CALCULATING_METRICS = "calculating_metrics"
    GENERATING_FACTS = "generating_facts"
    GENERATING_REPORTS = "generating_reports"
    COMPLETED = "completed"
