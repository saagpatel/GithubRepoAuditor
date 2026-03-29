"""Tests for src/dep_graph.py — cross-repo dependency graph."""
from __future__ import annotations

import pytest

from src.dep_graph import build_dependency_graph, find_vulnerability_impact


def _make_audit(name: str, dep_names: list[str]) -> dict:
    return {
        "metadata": {"name": name},
        "analyzer_results": [
            {
                "dimension": "dependencies",
                "score": 0.8,
                "details": {"dependency_names": dep_names},
            }
        ],
    }


class TestBuildDependencyGraph:
    def test_empty_audits_returns_empty_graph(self):
        result = build_dependency_graph([])
        assert result["shared_deps"] == []
        assert result["repo_dep_counts"] == {}

    def test_single_repo_no_shared_deps(self):
        audits = [_make_audit("RepoA", ["requests", "pytest"])]
        result = build_dependency_graph(audits)
        assert result["shared_deps"] == []
        assert result["repo_dep_counts"] == {"RepoA": 2}

    def test_shared_dep_appears_in_shared_list(self):
        audits = [
            _make_audit("RepoA", ["requests", "pytest"]),
            _make_audit("RepoB", ["requests", "flask"]),
        ]
        result = build_dependency_graph(audits)
        shared_names = [d["name"] for d in result["shared_deps"]]
        assert "requests" in shared_names
        assert "pytest" not in shared_names
        assert "flask" not in shared_names

    def test_shared_dep_has_correct_repo_list(self):
        audits = [
            _make_audit("RepoA", ["requests"]),
            _make_audit("RepoB", ["requests"]),
            _make_audit("RepoC", ["requests"]),
        ]
        result = build_dependency_graph(audits)
        dep = result["shared_deps"][0]
        assert dep["name"] == "requests"
        assert dep["count"] == 3
        assert sorted(dep["repos"]) == ["RepoA", "RepoB", "RepoC"]

    def test_sorted_by_count_descending(self):
        audits = [
            _make_audit("RepoA", ["pandas", "numpy", "requests"]),
            _make_audit("RepoB", ["pandas", "numpy"]),
            _make_audit("RepoC", ["pandas"]),
        ]
        result = build_dependency_graph(audits)
        counts = [d["count"] for d in result["shared_deps"]]
        assert counts == sorted(counts, reverse=True)

    def test_repo_without_dep_names_skipped(self):
        audits = [
            {"metadata": {"name": "Empty"}, "analyzer_results": []},
            _make_audit("RepoA", ["requests"]),
        ]
        result = build_dependency_graph(audits)
        assert "Empty" not in result["repo_dep_counts"]

    def test_repo_without_name_skipped(self):
        audits = [
            {"metadata": {}, "analyzer_results": [
                {"dimension": "dependencies", "score": 0.5, "details": {"dependency_names": ["x"]}}
            ]},
        ]
        result = build_dependency_graph(audits)
        assert result["repo_dep_counts"] == {}

    def test_caps_at_50_shared_deps(self):
        # Create 60 unique shared deps
        deps_a = [f"lib{i}" for i in range(60)]
        deps_b = [f"lib{i}" for i in range(60)]
        audits = [_make_audit("RepoA", deps_a), _make_audit("RepoB", deps_b)]
        result = build_dependency_graph(audits)
        assert len(result["shared_deps"]) <= 50


class TestFindVulnerabilityImpact:
    def test_finds_repos_using_dep(self):
        audits = [
            _make_audit("RepoA", ["log4j", "jackson"]),
            _make_audit("RepoB", ["log4j", "spring"]),
            _make_audit("RepoC", ["spring", "hibernate"]),
        ]
        affected = find_vulnerability_impact(audits, "log4j")
        assert sorted(affected) == ["RepoA", "RepoB"]

    def test_returns_empty_for_unknown_dep(self):
        audits = [_make_audit("RepoA", ["requests"])]
        affected = find_vulnerability_impact(audits, "nonexistent-lib")
        assert affected == []

    def test_finds_non_shared_dep(self):
        # dep used by only one repo — not in shared_deps, but find_vulnerability_impact should still find it
        audits = [
            _make_audit("RepoA", ["unique-lib"]),
            _make_audit("RepoB", ["other-lib"]),
        ]
        affected = find_vulnerability_impact(audits, "unique-lib")
        assert "RepoA" in affected

    def test_empty_audits(self):
        assert find_vulnerability_impact([], "anything") == []
