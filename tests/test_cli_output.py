from github_repo_auditor.cli_output import (
    HAS_RICH,
    create_progress,
    print_info,
    print_status,
    print_success,
    print_warning,
    redact_sensitive_text,
)


class TestRichAvailable:
    def test_has_rich(self):
        assert HAS_RICH is True

    def test_create_progress_returns_progress(self):
        progress = create_progress()
        assert progress is not None
        # Should have a console attached to stderr
        assert progress.console.stderr is True


class TestHelpers:
    def test_redacts_named_and_provider_credentials(self):
        github_token = "ghp_" + "a" * 36

        assert redact_sensitive_text("token=plain-secret") == "token=<redacted>"
        assert redact_sensitive_text(f"request failed for {github_token}") == (
            "request failed for <redacted>"
        )

    def test_redacts_complete_authorization_field_for_all_schemes(self):
        assert redact_sensitive_text("Authorization: token opaque-value") == (
            "Authorization: <redacted>"
        )
        assert redact_sensitive_text("Authorization: Basic dXNlcjpwYXNz") == (
            "Authorization: <redacted>"
        )
        assert redact_sensitive_text(
            'Authorization: Digest username="user", response="opaque"'
        ) == "Authorization: <redacted>"
        assert redact_sensitive_text(
            '{"Authorization": "Bearer opaque-value", "status": "failed"}'
        ) == '{"Authorization": "<redacted>", "status": "failed"}'

    def test_redacts_quoted_credential_keys_and_values(self):
        assert redact_sensitive_text('{"access_token": "opaque-secret"}') == (
            '{"access_token": "<redacted>"}'
        )
        assert redact_sensitive_text("{'client_secret': 'opaque-secret'}") == (
            "{'client_secret': '<redacted>'}"
        )
        assert redact_sensitive_text('password = "secret with spaces"') == (
            'password = "<redacted>"'
        )
        assert redact_sensitive_text("password = secret with spaces; status=failed") == (
            "password = <redacted>; status=failed"
        )
        assert redact_sensitive_text(r'{"token": "opaque\"tail"}') == (
            r'{"token": "<redacted>"}'
        )

    def test_preserves_noncredential_status_text(self):
        assert redact_sensitive_text("scanned=5 high=11 critical=0") == (
            "scanned=5 high=11 critical=0"
        )

    def test_print_status_no_crash(self, capsys):
        print_status("Testing status")
        # Should not raise

    def test_print_warning_no_crash(self, capsys):
        print_warning("Test warning")

    def test_print_info_no_crash(self, capsys):
        print_info("Test info")

    def test_print_success_no_crash(self, capsys):
        print_success("Test success")
