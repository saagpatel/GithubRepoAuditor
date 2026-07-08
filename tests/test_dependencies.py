"""Focused coverage for dependency manifest parsing and analyzer edge cases."""

from __future__ import annotations

import sys
import types

import pytest

from src.analyzers.dependencies import DependenciesAnalyzer, _count_dependencies


class TestDependenciesCacheInputsHash:
    def test_hashes_present_lockfiles_and_manifests(self, tmp_repo, sample_metadata):
        """Cache fingerprints include present dependency lockfiles and manifests."""
        (tmp_repo / "package-lock.json").write_text('{"lockfileVersion": 3}\n')
        analyzer = DependenciesAnalyzer()

        digest = analyzer.cache_inputs_hash(tmp_repo, sample_metadata)

        assert isinstance(digest, str)
        assert len(digest) == 64

    def test_hash_ignores_unreadable_dependency_file(self, tmp_repo, sample_metadata):
        """Unreadable dependency files are skipped instead of failing fingerprinting."""
        unreadable = tmp_repo / "package-lock.json"
        unreadable.write_text("locked\n")
        readable = tmp_repo / "package.json"
        readable.write_text('{"dependencies": {"click": "^8.0.0"}}\n')
        unreadable.chmod(0)
        try:
            digest = DependenciesAnalyzer().cache_inputs_hash(tmp_repo, sample_metadata)
        finally:
            unreadable.chmod(0o644)

        assert isinstance(digest, str)
        assert len(digest) == 64

    def test_hash_returns_none_without_dependency_files(self, empty_repo, sample_metadata):
        """Repos without dependency files do not receive a cache fingerprint."""
        assert DependenciesAnalyzer().cache_inputs_hash(empty_repo, sample_metadata) is None

    def test_hash_returns_none_without_repo_path(self, sample_metadata):
        """Missing local repo paths run uncached because there are no inputs to hash."""
        assert DependenciesAnalyzer().cache_inputs_hash(None, sample_metadata) is None


class TestCountDependencies:
    def test_counts_package_json_dependencies_and_dev_dependencies(self, tmp_path):
        """package.json counts dependencies and devDependencies together."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "package.json").write_text(
            '{"dependencies": {"react": "^19.0.0"}, "devDependencies": {"vite": "^6.0.0"}}'
        )

        assert _count_dependencies(repo, ["package.json"]) == 2

    def test_invalid_package_json_falls_through_to_requirements(self, tmp_path):
        """Invalid package.json is ignored so a later manifest can provide the count."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "package.json").write_text("{not-json")
        (repo / "requirements.txt").write_text("requests\n")

        assert _count_dependencies(repo, ["package.json", "requirements.txt"]) == 1

    def test_package_json_oserror_falls_through_to_requirements(self, tmp_path):
        """Unreadable package.json is ignored so requirements.txt can be parsed."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "package.json").symlink_to(repo / "missing-package.json")
        (repo / "requirements.txt").write_text("requests\nclick\n")

        assert _count_dependencies(repo, ["package.json", "requirements.txt"]) == 2

    def test_counts_requirements_txt_install_lines_only(self, tmp_path):
        """requirements.txt ignores comments, blanks, and option lines."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text(
            "\n# comment\n-r base.txt\n--extra-index-url https://example.test\nrequests\nclick>=8\n"
        )

        assert _count_dependencies(repo, ["requirements.txt"]) == 2

    def test_requirements_oserror_falls_through_to_cargo(self, tmp_path):
        """Unreadable requirements.txt is ignored so Cargo.toml can be parsed."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").symlink_to(repo / "missing-requirements.txt")
        (repo / "Cargo.toml").write_text('[dependencies]\nserde = "1"\n')

        assert _count_dependencies(repo, ["requirements.txt", "Cargo.toml"]) == 1

    def test_counts_cargo_dependencies_section_until_next_section(self, tmp_path):
        """Cargo.toml counts assignments in [dependencies] and stops at the next section."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "Cargo.toml").write_text(
            '[package]\nname = "demo"\n[dependencies]\nserde = "1"\ntokio = "1"\n[dev-dependencies]\npretty_assertions = "1"\n'
        )

        assert _count_dependencies(repo, ["Cargo.toml"]) == 2

    def test_cargo_without_dependencies_section_returns_zero(self, tmp_path):
        """Cargo.toml without [dependencies] is parseable as zero dependencies."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "Cargo.toml").write_text('[package]\nname = "demo"\n')

        assert _count_dependencies(repo, ["Cargo.toml"]) == 0

    def test_cargo_oserror_falls_through_to_go_mod(self, tmp_path):
        """Unreadable Cargo.toml is ignored so go.mod can be parsed."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "Cargo.toml").symlink_to(repo / "missing-cargo.toml")
        (repo / "go.mod").write_text("module example.test/demo\n\nrequire (\ngolang.org/x/text v0.14.0\n)\n")

        assert _count_dependencies(repo, ["Cargo.toml", "go.mod"]) == 1

    def test_counts_go_mod_require_block(self, tmp_path):
        """go.mod counts nonblank entries inside a require block."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "go.mod").write_text(
            "module example.test/demo\n\nrequire (\ngolang.org/x/text v0.14.0\ngithub.com/google/uuid v1.6.0\n)\n"
        )

        assert _count_dependencies(repo, ["go.mod"]) == 2

    def test_go_mod_without_require_returns_zero(self, tmp_path):
        """go.mod without a require section is parseable as zero dependencies."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "go.mod").write_text("module example.test/demo\n")

        assert _count_dependencies(repo, ["go.mod"]) == 0

    def test_go_mod_oserror_falls_through_to_pyproject(self, tmp_path):
        """Unreadable go.mod is ignored so pyproject.toml can be parsed."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "go.mod").symlink_to(repo / "missing-go.mod")
        (repo / "pyproject.toml").write_text('[project]\ndependencies = [\n"requests",\n]\n')

        assert _count_dependencies(repo, ["go.mod", "pyproject.toml"]) == 1

    def test_counts_pyproject_dependencies_list(self, tmp_path):
        """pyproject.toml counts quoted dependency entries in a dependencies list."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text('[project]\ndependencies = [\n"requests",\n"click",\n]\n')

        assert _count_dependencies(repo, ["pyproject.toml"]) == 2

    def test_pyproject_without_dependencies_found_returns_none(self, tmp_path):
        """pyproject.toml without counted dependency entries returns an unknown count."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')

        assert _count_dependencies(repo, ["pyproject.toml"]) is None

    def test_pyproject_oserror_returns_none(self, tmp_path):
        """Unreadable pyproject.toml leaves dependency count unknown."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").symlink_to(repo / "missing-pyproject.toml")

        assert _count_dependencies(repo, ["pyproject.toml"]) is None


class TestDependenciesAnalyzerFindings:
    def test_excessive_dependencies_finding_for_large_package_json(self, tmp_path, sample_metadata):
        """More than 500 dependencies emits the excessive dependency finding."""
        repo = tmp_path / "repo"
        repo.mkdir()
        deps = ",".join(f'"dep{i}": "1.0.0"' for i in range(501))
        (repo / "package.json").write_text(f'{{"dependencies": {{{deps}}}}}')

        result = DependenciesAnalyzer().analyze(repo, sample_metadata)

        assert result.details["dep_count"] == 501
        assert "Excessive dependencies: 501" in result.findings

    def test_zero_dependencies_finding_for_empty_cargo_manifest(self, tmp_path, sample_metadata):
        """A parseable manifest with zero dependencies emits the zero-dependencies finding."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "Cargo.toml").write_text('[package]\nname = "demo"\n')

        result = DependenciesAnalyzer().analyze(repo, sample_metadata)

        assert result.details["dep_count"] == 0
        assert "Zero dependencies declared" in result.findings

    def test_unknown_dependency_count_finding_without_parseable_manifest(self, empty_repo, sample_metadata):
        """No supported manifest count emits the could-not-determine finding."""
        result = DependenciesAnalyzer().analyze(empty_repo, sample_metadata)

        assert result.details["dep_count"] is None
        assert "Could not determine dependency count" in result.findings

    def test_libyears_merge_preserves_existing_dependency_count(
        self, tmp_path, sample_metadata, monkeypatch
    ):
        """Libyears details are merged while preserving the analyzer's dependency count."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("requests\nclick\n")

        fake_cache_module = types.ModuleType("src.cache")
        fake_cache_module.ResponseCache = lambda ttl: {"ttl": ttl}
        fake_libyears_module = types.ModuleType("src.libyears")
        fake_libyears_module.compute_libyears = lambda repo_path, manifests, cache: {
            "dep_count": 999,
            "total_libyears": 4.5,
        }
        monkeypatch.setitem(sys.modules, "src.cache", fake_cache_module)
        monkeypatch.setitem(sys.modules, "src.libyears", fake_libyears_module)

        result = DependenciesAnalyzer().analyze(repo, sample_metadata)

        assert result.details["dep_count"] == 2
        assert result.details["total_libyears"] == 4.5
        assert "Libyears: 4.5" in result.findings

    def test_libyears_failure_is_non_fatal(self, tmp_path, sample_metadata, monkeypatch):
        """Libyears exceptions are swallowed so dependency analysis still returns."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("requests\n")

        fake_cache_module = types.ModuleType("src.cache")
        fake_cache_module.ResponseCache = lambda ttl: {"ttl": ttl}
        fake_libyears_module = types.ModuleType("src.libyears")

        def fail_compute_libyears(repo_path, manifests, cache):
            raise RuntimeError("registry unavailable")

        fake_libyears_module.compute_libyears = fail_compute_libyears
        monkeypatch.setitem(sys.modules, "src.cache", fake_cache_module)
        monkeypatch.setitem(sys.modules, "src.libyears", fake_libyears_module)

        result = DependenciesAnalyzer().analyze(repo, sample_metadata)

        assert result.details["dep_count"] == 1
        assert "Dependency count: 1" in result.findings
        assert "total_libyears" not in result.details
