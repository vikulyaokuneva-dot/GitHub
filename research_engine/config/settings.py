from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResearchEngineSettings:
    project_root: Path
    artifacts_dir: Path


def get_settings() -> ResearchEngineSettings:
    project_root = Path(__file__).resolve().parents[1]
    artifacts_dir = project_root / "artifacts"
    return ResearchEngineSettings(project_root=project_root, artifacts_dir=artifacts_dir)
