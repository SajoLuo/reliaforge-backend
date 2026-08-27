"""New-developer path from scaffold to discovered running plugin."""

import subprocess
import sys
from pathlib import Path

import pytest

import reliaforge.scaffold as scaffold_module
from reliaforge.plugins.manager import PluginManager
from reliaforge.scaffold import scaffold_plugin


async def test_scaffolded_plugin_is_discovered_and_started(tmp_path: Path) -> None:
    plugin_id = "sample_tool"
    output = scaffold_plugin(plugin_id, tmp_path)
    assert output.name == plugin_id
    assert (output / "manifest.json").is_file()
    starter_test = (output / "tests" / "test_plugin.py").read_text(encoding="utf-8")
    assert "@pytest.mark.asyncio" in starter_test
    assert "pytest-asyncio" in (output / "README.md").read_text(encoding="utf-8")

    manager = PluginManager((tmp_path,), 5.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    view = manager.get_view(plugin_id)
    assert view.state == "running"
    assert view.health.status == "healthy"
    assert view.capabilities == ["sample_tool.message"]
    await manager.stop_all()


def test_scaffolded_starter_runs_under_pytest_asyncio_strict(tmp_path: Path) -> None:
    output = scaffold_plugin("strict_starter", tmp_path)
    strict_config = tmp_path / "strict-pytest.ini"
    strict_config.write_text("[pytest]\nasyncio_mode = strict\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--strict-markers",
            "-W",
            "error",
            "-c",
            str(strict_config),
            str(output / "tests" / "test_plugin.py"),
        ],
        cwd=output,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_scaffold_rejects_invalid_identity_and_overwrite(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        scaffold_plugin("Invalid Name", tmp_path)
    scaffold_plugin("sample_tool", tmp_path)
    with pytest.raises(FileExistsError):
        scaffold_plugin("sample_tool", tmp_path)


def test_scaffold_failure_leaves_destination_retriable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_copy = scaffold_module._copy_template

    def fail_after_copy(
        source: Path,
        output: Path,
        plugin_id: str,
        plugin_name: str,
    ) -> None:
        original_copy(source, output, plugin_id, plugin_name)
        raise RuntimeError("specialization failed")

    monkeypatch.setattr(scaffold_module, "_copy_template", fail_after_copy)
    with pytest.raises(RuntimeError, match="specialization failed"):
        scaffold_plugin("sample_tool", tmp_path)
    assert not (tmp_path / "sample_tool").exists()

    monkeypatch.setattr(scaffold_module, "_copy_template", original_copy)
    assert scaffold_plugin("sample_tool", tmp_path).is_dir()
