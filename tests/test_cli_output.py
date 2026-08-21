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
        assert redact_sensitive_text("Authorization: Bearer opaque-value") == (
            "authorization: <redacted>"
        )
        assert redact_sensitive_text(f"request failed for {github_token}") == (
            "request failed for <redacted>"
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
