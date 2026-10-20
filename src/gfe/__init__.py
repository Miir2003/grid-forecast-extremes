"""grid-forecast-extremes: day-ahead load forecasting under extreme weather."""

from pathlib import Path
import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"


def load_config(path: Path | None = None) -> dict:
    """Read config/study.toml (the single source of study settings)."""
    path = path or PROJECT_ROOT / "config" / "study.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)
