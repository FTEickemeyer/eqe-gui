from pathlib import Path
import yaml


CONFIG_DIR = Path(__file__).resolve().parent


def merge_dict(base, override):
    """
    Recursively merge override into base.
    """
    result = dict(base)

    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value

    return result


def _expand_paths_in_config(config):
    """
    Expand ~ in config['paths'] entries and return them as Path objects.
    Relative paths are resolved relative to the repository root.
    """
    if "paths" not in config:
        return config

    repo_root = CONFIG_DIR.parent.parent  # adjust if needed

    for key, value in config["paths"].items():
        if value is None:
            continue

        p = Path(value).expanduser()

        if not p.is_absolute():
            p = (repo_root / p).resolve()

        config["paths"][key] = p

    return config


def load_config():
    default_file = CONFIG_DIR / "config_default.yaml"
    local_file = CONFIG_DIR / "config_local.yaml"

    with open(default_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if local_file.exists():
        with open(local_file, "r", encoding="utf-8") as f:
            local_config = yaml.safe_load(f) or {}

        config = merge_dict(config, local_config)

    config = _expand_paths_in_config(config)

    return config