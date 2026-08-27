"""Deterministic repository hygiene gate that never prints matched values."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

MAX_TEXT_BYTES = 2 * 1024 * 1024
SKIPPED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
}
RISK_DIRECTORIES = {"backup", "screenshots", "test-results"}
SKIPPED_FILES = {".coverage"}
RISK_SUFFIXES = {
    ".bak",
    ".db",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".sqlite",
    ".zip",
}
RISK_NAMES = {"credentials.json", "credentials.yaml", "credentials.yml"}


@dataclass(frozen=True, order=True)
class Finding:
    """A safe finding containing location metadata only."""

    rule: str
    path: str
    line: int


@dataclass(frozen=True)
class AllowlistEntry:
    """An exact, documented exception."""

    rule: str
    path: str
    reason: str


def _pattern_rules() -> tuple[tuple[str, re.Pattern[str]], ...]:
    legacy_brand_one = "op" + "po"
    legacy_brand_pattern = rf"(?<![a-z]){legacy_brand_one}(?:it(?=\.com\b)|(?![a-z]))"
    legacy_brand_two = r"(?<![a-z])to" + r"wer(?![a-z])"
    legacy_product_prefix = "TO" + "WER_"
    legacy_non_latin_brand = "\u706b" + "\u773c"
    return (
        ("legacy_brand", re.compile(legacy_brand_pattern, re.IGNORECASE)),
        ("legacy_product_name", re.compile(legacy_brand_two, re.IGNORECASE)),
        ("legacy_environment_prefix", re.compile(legacy_product_prefix)),
        ("legacy_non_latin_brand", re.compile(legacy_non_latin_brand)),
        (
            "private_ipv4",
            re.compile(
                r"\b(?:10\.\d{1,3}(?:\.\d{1,3}){2}|"
                r"192\.168\.\d{1,3}\.\d{1,3}|"
                r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
            ),
        ),
        (
            "internal_domain",
            re.compile(r"\b[a-z0-9.-]+\.(?:corp|internal|local)\b", re.IGNORECASE),
        ),
        (
            "document_identifier",
            re.compile(
                r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
                r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
                re.IGNORECASE,
            ),
        ),
    )


SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:password|secret|token|api[_-]?key)\s*[:=]\s*['\"]([^'\"]+)['\"]"
)
ENV_ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    return (
        not normalized
        or normalized.startswith(("replace-", "example", "placeholder", "${", "<"))
        or normalized.endswith("-here")
    )


def _load_allowlist(path: Path) -> set[AllowlistEntry]:
    if not path.exists():
        return set()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1 or not isinstance(raw.get("entries"), list):
        raise ValueError("invalid hygiene allowlist schema")
    entries: set[AllowlistEntry] = set()
    for item in raw["entries"]:
        if set(item) != {"rule", "path", "reason"}:
            raise ValueError("allowlist entries require rule, path, and reason")
        entry = AllowlistEntry(**item)
        if not entry.rule or not entry.path or not entry.reason.strip():
            raise ValueError("allowlist entries must be non-empty")
        entries.add(entry)
    return entries


def scan_repository(root: Path, allowlist_path: Path | None = None) -> list[Finding]:
    """Scan a repository and return sorted metadata-only findings."""

    root = root.resolve()
    configured_allowlist = allowlist_path or root / "scripts" / "hygiene_allowlist.json"
    allowlist = _load_allowlist(configured_allowlist)
    findings: list[Finding] = []

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        parts = set(path.relative_to(root).parts)
        if parts & SKIPPED_DIRECTORIES:
            continue
        if path.is_dir():
            if path.name in RISK_DIRECTORIES:
                findings.append(Finding("risky_directory", relative, 1))
            continue
        if path.name in SKIPPED_FILES:
            continue
        findings.extend(_scan_path(path, relative))

    allowed_pairs = {(entry.rule, entry.path) for entry in allowlist}
    return sorted(
        finding for finding in findings if (finding.rule, finding.path) not in allowed_pairs
    )


def _scan_path(path: Path, relative: str) -> list[Finding]:
    findings = _scan_file_metadata(path, relative)
    if any(finding.rule in {"large_file", "binary_file", "non_utf8_file"} for finding in findings):
        return findings
    text = path.read_text(encoding="utf-8")
    findings.extend(_scan_text(text, relative))
    return findings


def _scan_file_metadata(path: Path, relative: str) -> list[Finding]:
    findings: list[Finding] = []
    lower_name = path.name.lower()
    if lower_name == ".env" or (lower_name.startswith(".env.") and lower_name != ".env.example"):
        findings.append(Finding("committed_environment_file", relative, 1))
    if lower_name in RISK_NAMES or path.suffix.lower() in RISK_SUFFIXES:
        findings.append(Finding("risky_file", relative, 1))

    if path.stat().st_size > MAX_TEXT_BYTES:
        findings.append(Finding("large_file", relative, 1))
        return findings
    raw = path.read_bytes()
    if b"\x00" in raw:
        findings.append(Finding("binary_file", relative, 1))
        return findings
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        findings.append(Finding("non_utf8_file", relative, 1))
        return findings

    return findings


def _scan_text(text: str, relative: str) -> list[Finding]:
    findings: list[Finding] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in _pattern_rules():
            if pattern.search(line):
                findings.append(Finding(rule, relative, line_number))
        email = EMAIL.search(line)
        if email and email.group(1).lower() != "example.com":
            findings.append(Finding("personal_or_internal_email", relative, line_number))
        secret_match = SECRET_ASSIGNMENT.search(line)
        if secret_match and not _is_placeholder(secret_match.group(1)):
            findings.append(Finding("literal_secret", relative, line_number))
        env_match = ENV_ASSIGNMENT.match(line.strip())
        if (
            env_match
            and any(
                marker in env_match.group(1)
                for marker in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")
            )
            and not _is_placeholder(env_match.group(2))
        ):
            findings.append(Finding("literal_secret", relative, line_number))
    return findings


def main() -> int:
    """Run the gate and print location metadata only."""

    parser = argparse.ArgumentParser(description="Check open-source repository hygiene")
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--allowlist", type=Path)
    args = parser.parse_args()
    try:
        findings = scan_repository(args.root, args.allowlist)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"scanner_error <repository>:1 {type(exc).__name__}")
        return 2
    for finding in findings:
        print(f"{finding.rule} {finding.path}:{finding.line}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
