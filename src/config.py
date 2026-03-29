"""Config file support — loads audit-config.yaml and merges with CLI args."""
from __future__ import annotations

import sys
from pathlib import Path


def load_config(config_path: Path | None = None) -> dict:
    """Load audit config from YAML file. Returns empty dict if not found."""
    if config_path is None:
        config_path = Path("audit-config.yaml")
    if not config_path.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        print("  Config file requires PyYAML: pip install pyyaml", file=sys.stderr)
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


_CONFIG_MAP = {
    "username": "username",
    "token": "token",
    "output_dir": "output_dir",
    "skip_forks": "skip_forks",
    "skip_archived": "skip_archived",
    "skip_clone": "skip_clone",
    "incremental": "incremental",
    "verbose": "verbose",
    "graphql": "graphql",
    "badges": "badges",
    "upload_badges": "upload_badges",
    "html": "html",
    "notion": "notion",
    "notion_sync": "notion_sync",
    "notion_registry": "notion_registry",
    "portfolio_readme": "portfolio_readme",
    "readme_suggestions": "readme_suggestions",
    "scoring_profile": "scoring_profile",
    "auto_archive": "auto_archive",
    "narrative": "narrative",
    "repos": "repos",
}


def merge_config_with_args(args: object, config: dict) -> None:
    """Apply config values to args namespace. CLI flags take precedence."""
    for config_key, arg_name in _CONFIG_MAP.items():
        if config_key not in config:
            continue
        current = getattr(args, arg_name, None)
        config_val = config[config_key]
        if isinstance(config_val, bool):
            if not current:
                setattr(args, arg_name, config_val)
        elif current is None or (isinstance(current, list) and not current):
            setattr(args, arg_name, config_val)
