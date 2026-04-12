from src.cli_output import (
    HAS_RICH,
    create_progress,
    print_info,
    print_status,
    print_success,
    print_warning,
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
    def test_print_status_no_crash(self, capsys):
        print_status("Testing status")
        # Should not raise

    def test_print_warning_no_crash(self, capsys):
        print_warning("Test warning")

    def test_print_info_no_crash(self, capsys):
        print_info("Test info")

    def test_print_success_no_crash(self, capsys):
        print_success("Test success")
