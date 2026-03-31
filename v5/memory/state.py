"""Processing state management"""

from dataclasses import dataclass, field
from datetime import datetime

from domain import CabinetContext


@dataclass
class ProcessingState:
    """State of processing for a cabinet"""
    cabinet_id: str
    last_successful_daily_run: datetime | None = None
    last_successful_audit_run: datetime | None = None
    
    last_error: str | None = None
    last_error_time: datetime | None = None
    
    runs_count: int = 0
    errors_count: int = 0


class StateStorage:
    """Manages processing state"""
    
    def __init__(self, cabinet_ctx: CabinetContext):
        self.cabinet_ctx = cabinet_ctx
    
    def load_state(self) -> ProcessingState:
        """Load state from disk"""
        # TODO: Implement state loading from .state.json
        pass
    
    def save_state(self, state: ProcessingState) -> None:
        """Save state to disk"""
        # TODO: Implement state saving to .state.json
        pass
