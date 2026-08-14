from pathlib import Path
import yaml


CONFIG_DIR = Path(__file__).resolve().parent

# Where a per-machine config_local.yaml is looked for, in priority order:
#
# 1. ~/.eqe/config_local.yaml -- a normal user-home location, usable
#    regardless of how the package was installed (editable checkout or a
#    real `pip install`/`pip install git+...` into site-packages, where a
#    colleague would otherwise have to go hunting for the install
#    directory to edit anything). This is the recommended location for
#    a fresh install.
# 2. CONFIG_DIR/config_local.yaml -- next to config_default.yaml, i.e.
#    inside the package itself. Only reachable/writable for an editable
#    install from a source checkout (`pip install -e .`); kept for
#    backward compatibility with that dev workflow.
#
# The first one that exists wins; see load_config().
USER_CONFIG_FILE = Path.home() / ".eqe" / "config_local.yaml"


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


def get_local_config_path():
    """
    Resolve which config_local.yaml is actually in effect -- see
    USER_CONFIG_FILE. Used by load_config() and surfaced to the user
    (e.g. an error message pointing at the right file to create/edit).
    """
    if USER_CONFIG_FILE.exists():
        return USER_CONFIG_FILE
    return CONFIG_DIR / "config_local.yaml"


def load_config():
    default_file = CONFIG_DIR / "config_default.yaml"
    local_file = get_local_config_path()

    with open(default_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if local_file.exists():
        with open(local_file, "r", encoding="utf-8") as f:
            local_config = yaml.safe_load(f) or {}

        config = merge_dict(config, local_config)

    config = _expand_paths_in_config(config)

    return config