from github_repo_auditor.portfolio_truth_reconcile import _derive_readme_char_count


def test_fallback_readme_selection_is_independent_of_directory_order(
    tmp_path, monkeypatch
):
    first, second = tmp_path / "README.en", tmp_path / "README.fr"
    first.write_text("first")
    second.write_text("second")
    for order in ([first, second], [second, first]):
        monkeypatch.setattr(type(tmp_path), "iterdir", lambda self: iter(order))
        assert _derive_readme_char_count(tmp_path, has_git=True) == len("first")
