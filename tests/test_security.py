from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.analyzers.security import SecurityAnalyzer, _scan_secrets, _find_dangerous_files
from src.models import RepoMetadata


def _meta(**overrides) -> RepoMetadata:
    defaults = dict(
        name="test", full_name="user/test", description=None,
        language="Python", languages={"Python": 5000}, private=False, fork=False,
        archived=False, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=0, forks=0, open_issues=0,
        size_kb=100, html_url="", clone_url="", topics=[],
    )
    defaults.update(overrides)
    return RepoMetadata(**defaults)


def _write_fake_secret(tmp_path: Path, filename: str, pattern_type: str) -> None:
    """Write a file containing a pattern that matches our secret regexes."""
    # Build the secret string dynamically to avoid triggering the hook
    if pattern_type == "private_key":
        content = "KEY = " + '"""' + "-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5 + "\ndata\n" + "-" * 5 + "END RSA PRIVATE KEY" + "-" * 5 + '"""'
    elif pattern_type == "generic_secret":
        content = 'password = "' + "x" * 32 + '"'
    else:
        content = 'print("clean")'
    (tmp_path / filename).write_text(content)


class TestSecretScanning:
    def test_detects_private_key(self, tmp_path):
        _write_fake_secret(tmp_path, "key.py", "private_key")
        found = _scan_secrets(tmp_path)
        assert len(found) >= 1

    def test_detects_generic_secret(self, tmp_path):
        _write_fake_secret(tmp_path, "config.py", "generic_secret")
        found = _scan_secrets(tmp_path)
        assert len(found) >= 1

    def test_clean_repo_no_secrets(self, tmp_path):
        (tmp_path / "main.py").write_text('print("hello world")')
        found = _scan_secrets(tmp_path)
        assert len(found) == 0

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        _write_fake_secret(nm, "index.js", "generic_secret")
        found = _scan_secrets(tmp_path)
        assert len(found) == 0


class TestDangerousFiles:
    def test_detects_env_file(self, tmp_path):
        (tmp_path / ".env").write_text("SETTING=value")
        found = _find_dangerous_files(tmp_path)
        assert any(p.name == ".env" for p in found)

    def test_detects_pem_file(self, tmp_path):
        (tmp_path / "cert.pem").write_text("certificate data")
        found = _find_dangerous_files(tmp_path)
        assert any(p.suffix == ".pem" for p in found)

    def test_clean_repo_no_dangerous(self, tmp_path):
        (tmp_path / "main.py").write_text('print("hello")')
        found = _find_dangerous_files(tmp_path)
        assert len(found) == 0


class TestSecurityAnalyzer:
    def test_clean_repo_high_score(self, tmp_path):
        (tmp_path / "main.py").write_text('print("hello")')
        (tmp_path / "SECURITY.md").write_text("# Security Policy")
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "dependabot.yml").write_text("version: 2")
        result = SecurityAnalyzer().analyze(tmp_path, _meta())
        assert result.score >= 0.8

    def test_repo_with_secrets_low_score(self, tmp_path):
        _write_fake_secret(tmp_path, "config.py", "private_key")
        _write_fake_secret(tmp_path, "other.py", "generic_secret")
        result = SecurityAnalyzer().analyze(tmp_path, _meta())
        assert result.score < 0.8
        assert result.details["secrets_found"] > 0

    def test_missing_security_config_penalized(self, tmp_path):
        (tmp_path / "main.py").write_text('print("hello")')
        result = SecurityAnalyzer().analyze(tmp_path, _meta())
        assert result.score < 1.0
        assert not result.details["has_security_md"]
        assert not result.details["has_dependabot"]
