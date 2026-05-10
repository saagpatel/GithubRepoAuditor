from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.analyzers.security import SecurityAnalyzer, _find_dangerous_files, _scan_secrets
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

    def test_ignores_github_actions_secret_references(self, tmp_path):
        workflow = tmp_path / ".github" / "workflows"
        workflow.mkdir(parents=True)
        (workflow / "release.yml").write_text(
            'env:\n  APPLE_CERTIFICATE: "${{ secrets.APPLE_CERTIFICATE }}"\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_ignores_runtime_generated_shell_values(self, tmp_path):
        (tmp_path / "release.sh").write_text(
            'KEYCHAIN_PASSWORD="$(openssl rand -base64 24)"\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_ignores_common_test_placeholder_values(self, tmp_path):
        (tmp_path / "oauth.test.ts").write_text(
            'const config = { client_secret: "client-secret" };\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_ignores_test_secret_fixture_values(self, tmp_path):
        (tmp_path / "test_slack.py").write_text(
            'SIGNING_SECRET = "test_signing_secret_abc"\n'
            'SLASH_SECRET = "slash_test_signing_secret_xyz"\n'
            'WEBHOOK_SECRET = "supersecretkey"\n'
            'DEFAULT_WEBHOOK_SECRET = "dev-webhook-secret"\n'
            'TEST_ADMIN_PASSWORD = "test-only-password"\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_ignores_fake_slack_tokens_and_placeholders(self, tmp_path):
        (tmp_path / "settings.tsx").write_text(
            'const fakeToken = "xoxb-fake-token";\n'
            'const placeholder = "xoxb-your-bot-token";\n'
            'const wrongKind = "xoxp-not-bot-token";\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_ignores_example_keys_and_safe_prompt_labels(self, tmp_path):
        (tmp_path / "detector.rs").write_text(
            'let text = "My key is AKIAIOSFODNN7EXAMPLE and here it is.";\n'
        )
        (tmp_path / "setup_keyring.py").write_text(
            'client_secret = getpass.getpass("Client Secret: ").strip()\n'
            "if not client_secret:\n"
            '    print("Error: client_secret is required")\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_ignores_truncated_private_key_detector_fixture(self, tmp_path):
        (tmp_path / "detector.rs").write_text(
            'let text = "-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKCAQEA...";\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_ignores_hex_test_encryption_secret_fixture(self, tmp_path):
        tests = tmp_path / "src" / "__tests__"
        tests.mkdir(parents=True)
        (tests / "encryption.test.ts").write_text(
            "const secret = "
            "'0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';\n"
        )
        found = _scan_secrets(tmp_path)
        assert found == []

    def test_detects_real_looking_aws_key_outside_examples(self, tmp_path):
        (tmp_path / "config.py").write_text(
            'AWS_KEY = "AKIA1234567890ABCDEF"\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == [("AWS Access Key", "config.py")]

    def test_ignores_shell_fallback_and_template_secret_values(self, tmp_path):
        (tmp_path / "smoke.sh").write_text(
            'export AUTH_SECRET="${E2E_AUTH_SECRET:-playwright-secret}"\n'
            'PGPASSWORD="${POSTGRES_PASSWORD:-change-me}"\n'
        )
        (tmp_path / "get_refresh_token.py").write_text(
            'line = f\'VAS_YT_CLIENT_SECRET="{client_secret}"\'\n'
        )
        found = _scan_secrets(tmp_path)
        assert found == []

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
