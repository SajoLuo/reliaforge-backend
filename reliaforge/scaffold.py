"""Generate a new plugin from the versioned public template."""

from __future__ import annotations

import argparse
import re
import shutil
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory

PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def scaffold_plugin(plugin_id: str, destination: Path) -> Path:
    """Copy and specialize the plugin template without overwriting files."""

    if not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
        raise ValueError("plugin id must use lowercase snake case")
    output = destination.resolve() / plugin_id
    if output.exists():
        raise FileExistsError(f"plugin destination already exists: {output}")

    source_checkout = Path(__file__).parents[1] / "templates" / "plugin"
    plugin_name = plugin_id.replace("_", " ").title()
    if source_checkout.is_dir():
        return _stage_template(source_checkout, output, plugin_id, plugin_name)

    packaged_template = files("reliaforge").joinpath("plugin_template")
    with as_file(packaged_template) as source_package:
        return _stage_template(source_package, output, plugin_id, plugin_name)


def _stage_template(source: Path, output: Path, plugin_id: str, plugin_name: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{plugin_id}-", dir=output.parent) as temporary:
        staged = Path(temporary) / plugin_id
        _copy_template(source, staged, plugin_id, plugin_name)
        if output.exists():
            raise FileExistsError(f"plugin destination already exists: {output}")
        staged.rename(output)
    return output


def _copy_template(source: Path, output: Path, plugin_id: str, plugin_name: str) -> None:
    shutil.copytree(
        source,
        output,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    replacements = {
        "{{plugin_id}}": plugin_id,
        "{{plugin_name}}": plugin_name,
    }
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        content = path.read_text(encoding="utf-8")
        for marker, replacement in replacements.items():
            content = content.replace(marker, replacement)
        path.write_text(content, encoding="utf-8")


def main() -> None:
    """Run the scaffold command."""

    parser = argparse.ArgumentParser(description="Create a ReliaForge plugin")
    parser.add_argument("plugin_id")
    parser.add_argument("--destination", type=Path, default=Path("local-plugins"))
    args = parser.parse_args()
    scaffold_plugin(args.plugin_id, args.destination)


if __name__ == "__main__":
    main()
