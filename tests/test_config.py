import argparse

import pytest

from src.config import load_config, merge_config_with_args


class TestLoadConfig:
    def test_returns_empty_for_missing_file(self, tmp_path):
        assert load_config(tmp_path / "nonexistent.yaml") == {}

    def test_parses_yaml(self, tmp_path):
        yaml = pytest.importorskip("yaml")
        cfg = tmp_path / "test.yaml"
        cfg.write_text("html: true\nskip_forks: true\noutput_dir: my-output\n")
        result = load_config(cfg)
        assert result["html"] is True
        assert result["skip_forks"] is True
        assert result["output_dir"] == "my-output"

    def test_returns_empty_for_empty_yaml(self, tmp_path):
        yaml = pytest.importorskip("yaml")
        cfg = tmp_path / "empty.yaml"
        cfg.write_text("")
        assert load_config(cfg) == {}

    def test_default_path_missing_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert load_config() == {}


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
