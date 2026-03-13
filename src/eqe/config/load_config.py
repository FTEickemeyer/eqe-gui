from pathlib import Path
import yaml

CONFIG_DIR = Path(__file__).parent

def load_config():

    default_file = CONFIG_DIR / "config_default.yaml"
    local_file = CONFIG_DIR / "config_local.yaml"

    with open(default_file) as f:
        config = yaml.safe_load(f)

    if local_file.exists():
        with open(local_file) as f:
            local_config = yaml.safe_load(f)

        config = merge_dict(config, local_config)

    return config


def merge_dict(base, override):
    for k, v in override.items():
        if isinstance(v, dict) and k in base:
            base[k] = merge_dict(base[k], v)
        else:
            base[k] = v
    return base