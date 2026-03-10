from pathlib import Path
import yaml


def load_config():
    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "config" / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)