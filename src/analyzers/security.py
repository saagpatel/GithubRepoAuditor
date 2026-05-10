"""Security surface analyzer — scans for exposed secrets, dangerous files, and security config."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

# Patterns that strongly suggest exposed secrets
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key", re.compile(r"(?P<value>AKIA[0-9A-Z]{16})")),
    ("GitHub Token", re.compile(r"(?P<value>ghp_[a-zA-Z0-9]{36})")),
    ("GitHub OAuth", re.compile(r"(?P<value>gho_[a-zA-Z0-9]{36})")),
    ("Slack Token", re.compile(r"(?P<value>xox[bpors]-[a-zA-Z0-9-]+)")),
    (
        "Generic API Key",
        re.compile(
            r"""(?:api[_-]?key|apikey)\s*[:=]\s*['"](?P<value>[a-zA-Z0-9]{20,})['"]""",
            re.IGNORECASE,
        ),
    ),
    (
        "Generic Secret",
        re.compile(
            r"""(?:secret|password|passwd)\s*[:=]\s*['"](?P<value>[^'"]{8,})['"]""",
            re.IGNORECASE,
        ),
    ),
    ("Private Key Header", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
]

# Files that should never be committed
DANGEROUS_FILES = frozenset({
    ".env", ".env.local", ".env.production",
    "credentials.json", "service-account.json",
    "id_rsa", "id_ed25519", "id_dsa",
    ".htpasswd", ".pgpass", ".netrc",
})

DANGEROUS_EXTENSIONS = frozenset({".pem", ".key", ".p12", ".pfx"})

# Security config files (good to have)
SECURITY_CONFIGS = [
    "SECURITY.md",
    ".github/SECURITY.md",
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
]

# Directories to skip during scanning
SKIP_DIRS = frozenset({
    ".git", "node_modules", "vendor", "__pycache__", ".venv",
    "venv", ".tox", "dist", "build", ".next", ".nuxt",
})

CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash",
    ".yml", ".yaml", ".toml", ".json", ".xml", ".env.example",
})

PLACEHOLDER_SECRET_VALUES = frozenset({
    "client-secret",
    "change-me",
    "dev-webhook-secret",
    "test-secret",
    "test-only-password",
    "dummy-secret",
    "example-secret",
    "placeholder-secret",
    "playwright-secret",
    "supersecretkey",
    "your-secret-here",
})


class SecurityAnalyzer(BaseAnalyzer):
    """Scans for security surface issues — exposed secrets, dangerous files, missing config."""

    name = "security"
    weight = 0.0  # Advisory dimension, not part of completeness score

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        score = 1.0  # Start perfect, deduct for issues
        findings: list[str] = []
        details: dict = {
            "secrets_found": 0,
            "dangerous_files": [],
            "has_security_md": False,
            "has_dependabot": False,
        }

        # 1. Scan for exposed secrets in code files
        secrets_found = _scan_secrets(repo_path)
        details["secrets_found"] = len(secrets_found)
        if secrets_found:
            score -= min(0.5, len(secrets_found) * 0.1)
            for label, secret_path in secrets_found[:5]:
                findings.append(f"Potential {label} in {secret_path}")

        # 2. Check for dangerous files
        dangerous = _find_dangerous_files(repo_path)
        details["dangerous_files"] = [str(p) for p in dangerous]
        if dangerous:
            score -= min(0.3, len(dangerous) * 0.1)
            for dangerous_path in dangerous[:5]:
                findings.append(f"Dangerous file committed: {dangerous_path.name}")

        # 3. Check for security config
        for config_path in SECURITY_CONFIGS:
            full = repo_path / config_path
            if full.is_file():
                if "SECURITY" in config_path:
                    details["has_security_md"] = True
                    findings.append("Has SECURITY.md")
                if "dependabot" in config_path:
                    details["has_dependabot"] = True
                    findings.append("Has Dependabot config")

        if not details["has_security_md"]:
            score -= 0.1
            findings.append("No SECURITY.md")
        if not details["has_dependabot"]:
            score -= 0.1
            findings.append("No Dependabot config")

        if not findings:
            findings.append("No security issues detected")

        return self._result(max(score, 0.0), findings, details)


def _scan_secrets(repo_path: Path, max_files: int = 200) -> list[tuple[str, str]]:
    """Scan code files for potential exposed secrets."""
    found: list[tuple[str, str]] = []
    scanned = 0

    for path in repo_path.rglob("*"):
        if scanned >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in CODE_EXTENSIONS:
            continue

        scanned += 1
        try:
            content = path.read_text(errors="replace")[:10_000]  # First 10KB
            for label, pattern in SECRET_PATTERNS:
                if any(
                    not _is_ignored_secret_match(match, path)
                    for match in pattern.finditer(content)
                ):
                    rel = path.relative_to(repo_path)
                    found.append((label, str(rel)))
                    break  # One finding per file is enough
        except OSError:
            continue

    return found


def _is_ignored_secret_match(match: re.Match, path: Path | None = None) -> bool:
    """Return true for safe secret-looking placeholders or runtime references."""
    try:
        value = match.group("value").strip()
    except IndexError:
        snippet = match.string[match.start(): match.start() + 120].lower()
        if "..." in snippet:
            return True
        return False

    normalized = value.strip("\"'").lower()
    normalized_token = re.sub(r"[\s_]+", "-", normalized)
    path_parts = {part.lower() for part in (path.parts if path else ())}
    is_test_path = bool(path_parts & {"test", "tests", "__tests__"})
    if normalized in PLACEHOLDER_SECRET_VALUES:
        return True
    if normalized_token in PLACEHOLDER_SECRET_VALUES:
        return True
    if normalized_token.startswith(("example-", "test-", "dummy-", "placeholder-")):
        return True
    if normalized.endswith("example") or "example" in normalized_token:
        return True
    if normalized.startswith(").strip()") or normalized.endswith(").strip()"):
        return True
    if normalized.endswith("..."):
        return True
    if is_test_path and re.fullmatch(r"[0-9a-f]{32,}", normalized):
        return True
    if normalized_token.startswith("xox") and any(
        marker in normalized_token for marker in ("fake", "test", "dummy", "your", "placeholder")
    ):
        return True
    if normalized_token.startswith("xox") and len(normalized_token) < 24:
        return True
    if "secret" in normalized_token and any(
        marker in normalized_token
        for marker in ("test", "fake", "mock", "fixture", "dev", "playwright")
    ):
        return True
    if normalized.startswith("{") and normalized.endswith("}") and re.fullmatch(
        r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", normalized
    ):
        return True
    if value.startswith("${") and ":-" in value:
        fallback = value.rsplit(":-", 1)[-1].rstrip("}").strip("\"'").lower()
        fallback_token = re.sub(r"[\s_]+", "-", fallback)
        if fallback_token in PLACEHOLDER_SECRET_VALUES:
            return True
    if value.startswith("${{") and "secrets." in value:
        return True
    if value.startswith("$("):
        return True
    return False


def _find_dangerous_files(repo_path: Path) -> list[Path]:
    """Find files that should never be committed."""
    dangerous: list[Path] = []

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in DANGEROUS_FILES:
            dangerous.append(path.relative_to(repo_path))
        elif path.suffix in DANGEROUS_EXTENSIONS:
            dangerous.append(path.relative_to(repo_path))

    return dangerous
