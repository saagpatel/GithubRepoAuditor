from __future__ import annotations

from src.similarity import classify_similarity, compute_file_hashes, find_similar_repos


class TestComputeFileHashes:
    def test_hashes_code_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello world from this project')\n" * 5)
        (tmp_path / "utils.py").write_text("def helper(): return 42\n" * 5)
        hashes = compute_file_hashes(tmp_path)
        assert len(hashes) == 2

    def test_skips_tiny_files(self, tmp_path):
        (tmp_path / "tiny.py").write_text("x=1")  # < 50 bytes
        hashes = compute_file_hashes(tmp_path)
        assert len(hashes) == 0

    def test_skips_non_code(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Hello\n" * 20)
        (tmp_path / "data.csv").write_text("a,b,c\n" * 20)
        hashes = compute_file_hashes(tmp_path)
        assert len(hashes) == 0

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}\n" * 10)
        hashes = compute_file_hashes(tmp_path)
        assert len(hashes) == 0


class TestFindSimilarRepos:
    def test_identical_repos(self):
        hashes = {"RepoA": {"h1", "h2", "h3"}, "RepoB": {"h1", "h2", "h3"}}
        similar = find_similar_repos(hashes, threshold=0.5)
        assert len(similar) == 1
        assert similar[0]["overlap_pct"] == 100.0

    def test_no_overlap(self):
        hashes = {"RepoA": {"h1", "h2"}, "RepoB": {"h3", "h4"}}
        similar = find_similar_repos(hashes, threshold=0.5)
        assert len(similar) == 0

    def test_partial_overlap(self):
        hashes = {"RepoA": {"h1", "h2", "h3", "h4"}, "RepoB": {"h1", "h2", "h5", "h6"}}
        similar = find_similar_repos(hashes, threshold=0.5)
        assert len(similar) == 1
        assert similar[0]["shared_files"] == 2

    def test_below_threshold_excluded(self):
        hashes = {"RepoA": {"h1", "h2", "h3", "h4", "h5"}, "RepoB": {"h1", "h6", "h7", "h8", "h9"}}
        similar = find_similar_repos(hashes, threshold=0.5)
        assert len(similar) == 0

    def test_empty_hashes_handled(self):
        hashes = {"RepoA": set(), "RepoB": {"h1"}}
        similar = find_similar_repos(hashes, threshold=0.5)
        assert len(similar) == 0

    def test_sorted_by_overlap(self):
        hashes = {
            "A": {"h1", "h2", "h3"},
            "B": {"h1", "h2", "h3"},  # 100% overlap with A
            "C": {"h1", "h2", "h4"},  # 66% overlap with A
        }
        similar = find_similar_repos(hashes, threshold=0.5)
        assert similar[0]["overlap_pct"] >= similar[-1]["overlap_pct"]


class TestClassifySimilarity:
    def _pair(self, repo_a: str, repo_b: str, overlap_pct: float) -> dict:
        return {"repo_a": repo_a, "repo_b": repo_b, "overlap_pct": overlap_pct, "shared_files": 5}

    def test_fork_candidate_when_high_overlap_and_fork(self):
        pair = self._pair("OrigRepo", "ForkRepo", 95.0)
        metadata = {
            "OrigRepo": {"fork": False, "archived": False, "size_kb": 1000, "language": "Python"},
            "ForkRepo": {"fork": True, "archived": False, "size_kb": 1000, "language": "Python"},
        }
        result = classify_similarity(pair, metadata)
        assert result["classification"] == "fork_candidate"
        assert "fork" in result["suggestion"].lower()
        assert "ForkRepo" in result["suggestion"]

    def test_merge_candidate_when_medium_overlap_small_repos(self):
        pair = self._pair("RepoA", "RepoB", 75.0)
        metadata = {
            "RepoA": {"fork": False, "archived": False, "size_kb": 500, "language": "Python"},
            "RepoB": {"fork": False, "archived": False, "size_kb": 500, "language": "JavaScript"},
        }
        result = classify_similarity(pair, metadata)
        assert result["classification"] == "merge_candidate"
        assert "merging" in result["suggestion"].lower()

    def test_shared_boilerplate_when_same_language(self):
        pair = self._pair("RepoA", "RepoB", 65.0)
        metadata = {
            "RepoA": {"fork": False, "archived": False, "size_kb": 10000, "language": "TypeScript"},
            "RepoB": {"fork": False, "archived": False, "size_kb": 10000, "language": "TypeScript"},
        }
        result = classify_similarity(pair, metadata)
        assert result["classification"] == "shared_boilerplate"
        assert "boilerplate" in result["suggestion"].lower() or "template" in result["suggestion"].lower()

    def test_generic_similar_fallback(self):
        pair = self._pair("RepoA", "RepoB", 40.0)
        metadata = {
            "RepoA": {"fork": False, "archived": True, "size_kb": 500, "language": "Go"},
            "RepoB": {"fork": False, "archived": True, "size_kb": 500, "language": "Rust"},
        }
        result = classify_similarity(pair, metadata)
        assert result["classification"] == "similar"
        assert "RepoA" in result["suggestion"]
        assert "RepoB" in result["suggestion"]

    def test_preserves_original_pair_fields(self):
        pair = self._pair("A", "B", 55.0)
        result = classify_similarity(pair, {})
        assert result["repo_a"] == "A"
        assert result["repo_b"] == "B"
        assert result["overlap_pct"] == 55.0
        assert result["shared_files"] == 5

    def test_no_fork_when_overlap_below_90(self):
        pair = self._pair("RepoA", "ForkRepo", 85.0)
        metadata = {
            "RepoA": {"fork": False, "archived": False, "size_kb": 500, "language": "Python"},
            "ForkRepo": {"fork": True, "archived": False, "size_kb": 500, "language": "Python"},
        }
        result = classify_similarity(pair, metadata)
        assert result["classification"] != "fork_candidate"
