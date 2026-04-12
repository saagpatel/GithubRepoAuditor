import argparse

import pytest

from src.config import inspect_config, load_config, merge_config_with_args, validate_config_data


class TestLoadConfig:
    def test_returns_empty_for_missing_file(self, tmp_path):
        assert load_config(tmp_path / "nonexistent.yaml") == {}

    def test_parses_yaml(self, tmp_path):
        pytest.importorskip("yaml")
        cfg = tmp_path / "test.yaml"
        cfg.write_text("html: true\nskip_forks: true\noutput_dir: my-output\n")
        result = load_config(cfg)
        assert result["html"] is True
        assert result["skip_forks"] is True
        assert result["output_dir"] == "my-output"

    def test_returns_empty_for_empty_yaml(self, tmp_path):
        pytest.importorskip("yaml")
        cfg = tmp_path / "empty.yaml"
        cfg.write_text("")
        assert load_config(cfg) == {}

    def test_default_path_missing_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert load_config() == {}

    def test_inspect_reports_malformed_yaml(self, tmp_path):
        pytest.importorskip("yaml")
        cfg = tmp_path / "broken.yaml"
        cfg.write_text("html: [unterminated\n")
        inspection = inspect_config(cfg)
        assert inspection.exists is True
        assert inspection.data == {}
        assert inspection.errors

    def test_inspect_reports_non_mapping_root(self, tmp_path):
        pytest.importorskip("yaml")
        cfg = tmp_path / "list.yaml"
        cfg.write_text("- html\n- notion\n")
        inspection = inspect_config(cfg)
        assert inspection.errors == ["Config root must be a YAML mapping of option names to values."]


class TestMergeConfig:
    def test_cli_overrides_config(self):
        args = argparse.Namespace(
            html=True, skip_forks=False, output_dir="cli-out", username="cli-user"
        )
        config = {
            "html": False,
            "skip_forks": True,
            "output_dir": "config-out",
            "username": "config-user",
        }
        merge_config_with_args(args, config)
        assert args.html is True  # CLI True stays
        assert args.output_dir == "cli-out"  # CLI string stays

    def test_fills_none_defaults(self):
        args = argparse.Namespace(
            html=False, skip_forks=False, output_dir=None, scoring_profile=None
        )
        config = {
            "html": True,
            "skip_forks": True,
            "output_dir": "from-config",
            "scoring_profile": "custom.json",
        }
        merge_config_with_args(args, config)
        assert args.html is True
        assert args.skip_forks is True
        assert args.output_dir == "from-config"
        assert args.scoring_profile == "custom.json"

    def test_empty_config_is_noop(self):
        args = argparse.Namespace(html=False, output_dir=None)
        merge_config_with_args(args, {})
        assert args.html is False
        assert args.output_dir is None

    def test_fills_empty_list(self):
        args = argparse.Namespace(repos=[])
        merge_config_with_args(args, {"repos": ["repo-a", "repo-b"]})
        assert args.repos == ["repo-a", "repo-b"]

    def test_does_not_overwrite_existing_list(self):
        args = argparse.Namespace(repos=["my-repo"])
        merge_config_with_args(args, {"repos": ["other-repo"]})
        assert args.repos == ["my-repo"]

    def test_unknown_config_key_is_ignored(self):
        args = argparse.Namespace(html=False)
        merge_config_with_args(args, {"nonexistent_key": "value"})
        assert not hasattr(args, "nonexistent_key")

    def test_config_overrides_known_string_defaults(self):
        args = argparse.Namespace(excel_mode="standard", preflight_mode="auto", watch_strategy="adaptive")
        merge_config_with_args(args, {"excel_mode": "template", "preflight_mode": "strict", "watch_strategy": "full"})
        assert args.excel_mode == "template"
        assert args.preflight_mode == "strict"
        assert args.watch_strategy == "full"


class TestValidateConfigData:
    def test_flags_unknown_key_as_warning(self):
        issues = validate_config_data({"mystery_flag": True})
        assert issues[0]["severity"] == "warning"

    def test_flags_wrong_type_as_error(self):
        issues = validate_config_data({"watch_interval": "fast"})
        assert issues[0]["severity"] == "error"

    def test_flags_bad_choice_as_error(self):
        issues = validate_config_data({"excel_mode": "native"})
        assert issues[0]["severity"] == "error"

    def test_accepts_new_operator_choices(self):
        issues = validate_config_data({"preflight_mode": "strict", "triage_view": "urgent", "watch_strategy": "adaptive"})
        assert issues == []
