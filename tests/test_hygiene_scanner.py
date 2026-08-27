"""Positive and negative fixtures for metadata-only hygiene findings."""

from pathlib import Path

from scripts.check_open_source_hygiene import Finding, scan_repository


def test_scanner_flags_brand_private_address_and_secret_without_values(tmp_path: Path) -> None:
    legacy_brand = "op" + "po"
    private_address = ".".join(("192", "168", "8", "9"))
    key_name = "api_" + "key"
    sample_value = "-".join(("sensitive", "fixture", "value"))
    content = "\n".join(
        (
            f"brand={legacy_brand}",
            f"address={private_address}",
            f'{key_name} = "{sample_value}"',
        )
    )
    (tmp_path / "unsafe.txt").write_text(content, encoding="utf-8")

    findings = scan_repository(tmp_path)
    rules = {finding.rule for finding in findings}
    assert {"legacy_brand", "private_ipv4", "literal_secret"} <= rules
    rendered = "\n".join(f"{finding.rule} {finding.path}:{finding.line}" for finding in findings)
    assert sample_value not in rendered


def test_scanner_allows_public_examples_and_placeholder_values(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text(
        "RELIAFORGE_PROXY_SHARED_SECRET=replace-with-a-random-value\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "Use localhost and docs@example.com for examples, opportunities, and opponents.\n",
        encoding="utf-8",
    )
    assert scan_repository(tmp_path) == []


def test_scanner_flags_brand_identifiers_and_legacy_domain(tmp_path: Path) -> None:
    legacy_brand = "op" + "po"
    legacy_product = "to" + "wer"
    content = "\n".join(
        (
            f"{legacy_brand.upper()}_INTERNAL=true",
            f"{legacy_brand}_api=enabled",
            f"https://api.{legacy_brand}it.com/v1",
            f"{legacy_product}_api=enabled",
        )
    )
    (tmp_path / "compound.txt").write_text(content, encoding="utf-8")

    findings = scan_repository(tmp_path)
    assert [finding.line for finding in findings if finding.rule == "legacy_brand"] == [1, 2, 3]
    assert [finding.line for finding in findings if finding.rule == "legacy_product_name"] == [4]


def test_scanner_flags_non_example_environment_file(tmp_path: Path) -> None:
    (tmp_path / ".env.production").write_text(
        "RELIAFORGE_ENVIRONMENT=test\n",
        encoding="utf-8",
    )
    findings = scan_repository(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule == "committed_environment_file"


def test_scanner_ignores_local_build_cache_but_flags_publishable_risk_directory(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "module.pyc").write_bytes(b"\x00generated")
    mypy_cache = tmp_path / ".mypy_cache"
    mypy_cache.mkdir()
    (mypy_cache / "cache.db").write_bytes(b"\x00generated")
    (tmp_path / ".coverage").write_bytes(b"\x00generated")
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()
    (screenshots / "sample.txt").write_text("public fixture", encoding="utf-8")

    findings = scan_repository(tmp_path)
    assert findings == [Finding("risky_directory", "screenshots", 1)]
