"""Processing state management"""

from dataclasses import dataclass
from datetime import datetime
import json
from dataclasses import asdict

from ..domain import CabinetContext


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


class StateManager:
    """Manages processing state in cabinet-scoped v5 memory."""
    
    def __init__(self, cabinet_ctx: CabinetContext):
        self.cabinet_ctx = cabinet_ctx
    
    def load_state(self) -> ProcessingState:
        """Load state from disk"""
        state_path = self.cabinet_ctx.state_file
        if not state_path.exists():
            return ProcessingState(cabinet_id=self.cabinet_ctx.cabinet.id)

        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            last_successful_daily_run = payload.get("last_successful_daily_run")
            last_successful_audit_run = payload.get("last_successful_audit_run")
            last_error_time = payload.get("last_error_time")
            return ProcessingState(
                cabinet_id=str(payload.get("cabinet_id") or self.cabinet_ctx.cabinet.id),
                last_successful_daily_run=(
                    datetime.fromisoformat(last_successful_daily_run)
                    if last_successful_daily_run
                    else None
                ),
                last_successful_audit_run=(
                    datetime.fromisoformat(last_successful_audit_run)
                    if last_successful_audit_run
                    else None
                ),
                last_error=str(payload.get("last_error")) if payload.get("last_error") else None,
                last_error_time=(
                    datetime.fromisoformat(last_error_time) if last_error_time else None
                ),
                runs_count=int(payload.get("runs_count", 0) or 0),
                errors_count=int(payload.get("errors_count", 0) or 0),
            )
        except Exception:
            # Reset to a safe default if state file is corrupted.
            return ProcessingState(cabinet_id=self.cabinet_ctx.cabinet.id)
    
    def save_state(self, state: ProcessingState) -> None:
        """Save state to disk"""
        state_path = self.cabinet_ctx.state_file
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        for key in (
            "last_successful_daily_run",
            "last_successful_audit_run",
            "last_error_time",
        ):
            value = payload.get(key)
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# Backward-compatible alias for older references.
StateStorage = StateManager
