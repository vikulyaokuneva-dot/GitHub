from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResearchEngineSettings:
    project_root: Path
    artifacts_dir: Path
    scenarios_dir: Path
    default_scenario_path: Path


def get_settings() -> ResearchEngineSettings:
    project_root = Path(__file__).resolve().parents[1]
    artifacts_dir = project_root / "artifacts"
    scenarios_dir = project_root / "config" / "scenarios"
    default_scenario_path = scenarios_dir / "default_research_scenario.json"
    return ResearchEngineSettings(
        project_root=project_root,
        artifacts_dir=artifacts_dir,
        scenarios_dir=scenarios_dir,
        default_scenario_path=default_scenario_path,
    )
