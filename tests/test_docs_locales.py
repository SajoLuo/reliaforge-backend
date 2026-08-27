"""Bilingual documentation structure and reciprocal navigation."""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _heading_levels(markdown: str) -> list[int]:
    return [len(match) for match in re.findall(r"^(#{1,6})\s+", markdown, re.MULTILINE)]


def _executable_code_blocks(markdown: str) -> list[tuple[str, str]]:
    return [
        (language.strip(), body.replace("\r\n", "\n"))
        for language, body in re.findall(
            r"^```([^\r\n]*)\r?\n([\s\S]*?)^```[ \t]*$",
            markdown,
            re.MULTILINE,
        )
        if language.strip() != "text"
    ]


def _assert_structural_parity(english: str, chinese: str) -> None:
    assert _heading_levels(chinese) == _heading_levels(english)
    assert _executable_code_blocks(chinese) == _executable_code_blocks(english)


def test_substantive_backend_docs_have_chinese_counterparts() -> None:
    english_directory = REPOSITORY_ROOT / "docs"
    chinese_directory = english_directory / "zh"
    english_names = {path.name for path in english_directory.glob("*.md")}
    chinese_names = {path.name for path in chinese_directory.glob("*.md")}

    assert chinese_names == english_names
    for name in english_names:
        english = _read(f"docs/{name}")
        chinese = _read(f"docs/zh/{name}")
        assert f"(zh/{name})" in english
        assert f"(../{name})" in chinese
        _assert_structural_parity(english, chinese)


def test_repository_and_scaffold_readmes_link_both_languages() -> None:
    for english_path, chinese_path in (
        ("README.md", "README_CN.md"),
        ("templates/plugin/README.md", "templates/plugin/README_CN.md"),
    ):
        english = _read(english_path)
        chinese = _read(chinese_path)
        assert "(README_CN.md)" in english
        assert "(README.md)" in chinese
        _assert_structural_parity(english, chinese)
