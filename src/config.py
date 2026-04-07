"""Config file support — loads audit-config.yaml and merges with CLI args."""
from __future__ import annotations

from dataclasses import dataclass, field
import sys
from pathlib import Path


@dataclass(frozen=True)
class ConfigInspection:
    path: Path
    exists: bool
    data: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def inspect_config(config_path: Path | None = None) -> ConfigInspection:
    """Inspect audit config without throwing parse errors into the CLI."""
    if config_path is None:
        config_path = Path("audit-config.yaml")
    if not config_path.is_file():
        return ConfigInspection(path=config_path, exists=False)
    try:
        import yaml
    except ImportError:
        message = "Config file requires PyYAML: pip install pyyaml"
        print(f"  {message}", file=sys.stderr)
        return ConfigInspection(path=config_path, exists=True, errors=[message])
    try:
        with open(config_path) as f:
            loaded = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        return ConfigInspection(
            path=config_path,
            exists=True,
            errors=[f"Failed to parse config file: {exc}"],
        )

    if loaded is None:
        return ConfigInspection(path=config_path, exists=True, data={})
    if not isinstance(loaded, dict):
        return ConfigInspection(
            path=config_path,
            exists=True,
            errors=["Config root must be a YAML mapping of option names to values."],
        )
    return ConfigInspection(path=config_path, exists=True, data=loaded)


def load_config(config_path: Path | None = None) -> dict:
    """Load audit config from YAML file. Returns empty dict if not found."""
    return inspect_config(config_path).data


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
    "pdf": "pdf",
    "excel_mode": "excel_mode",
    "notion": "notion",
    "notion_sync": "notion_sync",
    "notion_registry": "notion_registry",
    "portfolio_readme": "portfolio_readme",
    "readme_suggestions": "readme_suggestions",
    "scoring_profile": "scoring_profile",
    "portfolio_profile": "portfolio_profile",
    "collection": "collection",
    "review_pack": "review_pack",
    "scorecard": "scorecard",
    "security_offline": "security_offline",
    "campaign": "campaign",
    "writeback_target": "writeback_target",
    "writeback_apply": "writeback_apply",
    "campaign_sync_mode": "campaign_sync_mode",
    "max_actions": "max_actions",
    "governance_view": "governance_view",
    "auto_archive": "auto_archive",
    "narrative": "narrative",
    "watch": "watch",
    "watch_interval": "watch_interval",
    "preflight_mode": "preflight_mode",
    "triage_view": "triage_view",
    "create_issues": "create_issues",
    "dry_run": "dry_run",
    "summary": "summary",
    "resume": "resume",
    "vuln_check": "vuln_check",
    "repos": "repos",
}


_EXPECTED_TYPES = {
    "username": str,
    "token": str,
    "output_dir": str,
    "skip_forks": bool,
    "skip_archived": bool,
    "skip_clone": bool,
    "incremental": bool,
    "verbose": bool,
    "graphql": bool,
    "badges": bool,
    "upload_badges": bool,
    "html": bool,
    "pdf": bool,
    "excel_mode": str,
    "notion": bool,
    "notion_sync": bool,
    "notion_registry": bool,
    "portfolio_readme": bool,
    "readme_suggestions": bool,
    "scoring_profile": str,
    "portfolio_profile": str,
    "collection": str,
    "review_pack": bool,
    "scorecard": bool,
    "security_offline": bool,
    "campaign": str,
    "writeback_target": str,
    "writeback_apply": bool,
    "campaign_sync_mode": str,
    "max_actions": int,
    "governance_view": str,
    "auto_archive": bool,
    "narrative": bool,
    "watch": bool,
    "watch_interval": int,
    "preflight_mode": str,
    "triage_view": str,
    "create_issues": bool,
    "dry_run": bool,
    "summary": bool,
    "resume": bool,
    "vuln_check": bool,
    "repos": list,
}

_CHOICE_VALIDATORS = {
    "excel_mode": {"template", "standard"},
    "campaign": {"security-review", "promotion-push", "archive-sweep", "showcase-publish", "maintenance-cleanup"},
    "writeback_target": {"github", "notion", "all"},
    "campaign_sync_mode": {"reconcile", "append-only", "close-missing"},
    "governance_view": {"all", "ready", "drifted", "approved", "applied"},
    "preflight_mode": {"auto", "off", "strict"},
    "triage_view": {"all", "urgent", "ready", "blocked", "deferred"},
}

_ARG_DEFAULTS = {
    "output_dir": "output",
    "incremental": False,
    "verbose": False,
    "graphql": False,
    "badges": False,
    "upload_badges": False,
    "html": False,
    "pdf": False,
    "excel_mode": "template",
    "notion": False,
    "notion_sync": False,
    "notion_registry": False,
    "portfolio_readme": False,
    "readme_suggestions": False,
    "portfolio_profile": "default",
    "review_pack": False,
    "scorecard": False,
    "security_offline": False,
    "campaign_sync_mode": "reconcile",
    "max_actions": 20,
    "governance_view": "all",
    "watch": False,
    "watch_interval": 3600,
    "preflight_mode": "auto",
    "triage_view": "all",
}


def validate_config_data(config: dict) -> list[dict]:
    """Return normalized config validation issues."""
    issues: list[dict] = []
    for key, value in config.items():
        expected_type = _EXPECTED_TYPES.get(key)
        if expected_type is None:
            issues.append(
                {
                    "severity": "warning",
                    "key": key,
                    "summary": f"Unknown config key: {key}",
                    "details": "This option is not recognized and will be ignored.",
                }
            )
            continue
        if expected_type is list:
            if not isinstance(value, list):
                issues.append(
                    {
                        "severity": "error",
                        "key": key,
                        "summary": f"Config key '{key}' must be a list.",
                        "details": f"Received {type(value).__name__}.",
                    }
                )
                continue
        elif not isinstance(value, expected_type):
            issues.append(
                {
                    "severity": "error",
                    "key": key,
                    "summary": f"Config key '{key}' must be {expected_type.__name__}.",
                    "details": f"Received {type(value).__name__}.",
                }
            )
            continue

        allowed = _CHOICE_VALIDATORS.get(key)
        if allowed and value not in allowed:
            issues.append(
                {
                    "severity": "error",
                    "key": key,
                    "summary": f"Config key '{key}' has an unsupported value.",
                    "details": f"Allowed values: {', '.join(sorted(allowed))}.",
                }
            )
    return issues


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
        elif arg_name in _ARG_DEFAULTS and current == _ARG_DEFAULTS[arg_name]:
            setattr(args, arg_name, config_val)
