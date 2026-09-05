"""Fail CI when a shipped template changes without a schema version increase."""

from __future__ import annotations

import argparse
import ast
import subprocess
from pathlib import Path
from xml.etree import ElementTree

TEMPLATES = ("HUD_config.xml", "HUD_config.xml.example")


def version(xml: str) -> int:
    general = ElementTree.fromstring(xml).find("general")
    if general is None:
        raise ValueError("Configuration template is missing its general version")
    return int(general.attrib["version"])


def check(base: str, root: Path) -> None:
    tree = ast.parse((root / "fpdb_3_legacy/Configuration.py").read_text())
    current = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CONFIG_VERSION" for target in node.targets)
    )
    for name in TEMPLATES:
        xml = (root / name).read_text()
        if version(xml) != current:
            raise ValueError(f"{name}: version must equal CONFIG_VERSION ({current})")
        old = subprocess.check_output(["git", "show", f"{base}:{name}"], cwd=root, text=True)
        if xml != old and version(xml) <= version(old):
            raise ValueError(f"{name} changed: increment CONFIG_VERSION and both template versions")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    check(args.base, Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
