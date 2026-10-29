"""A pack gallery laid out as the packs repository will be: index.json beside the packages (#449)."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from fpdb_3_legacy import popup_packs, stat_packs
from fpdb_3_legacy.pack_gallery import INDEX_NAME, INDEX_SCHEMA, index_entry

ROOT = Path(__file__).resolve().parents[2]
HUDS = ("nlhe_6max_basic", "nlhe_6max_advanced", "nlhe_6max_dynamic")
EXAMPLE_PACK = ROOT / "docs" / "examples" / "example-preflop-pack"
LICENSE = "AGPL-3.0-or-later"


def stat_pack(target: Path, pack_id: str, version: str = "1.0.0") -> Path:
    """The example stat pack as a ``.fpdbstats`` archive, renamed to *pack_id*."""
    manifest = json.loads((EXAMPLE_PACK / "manifest.json").read_text(encoding="utf-8"))
    old = manifest["id"]
    archive = target / f"{pack_id}{stat_packs.PACK_SUFFIX}"
    with zipfile.ZipFile(archive, "w") as out:
        for path in sorted(EXAMPLE_PACK.rglob("*")):
            name = path.relative_to(EXAMPLE_PACK).as_posix()
            if path.is_file() and name != "manifest.json":
                # Every name the pack adds is namespaced by its id.
                out.writestr(name, path.read_text(encoding="utf-8").replace(old, pack_id))
        manifest_text = json.dumps({**json.loads(json.dumps(manifest).replace(old, pack_id)), "pack_version": version})
        out.writestr("manifest.json", manifest_text)
    return archive


def library_popups() -> set[str]:
    registry = popup_packs.load_default_registry()
    return {name for pack in registry.names() for name in registry.packs[pack].nodes}


def write_index(root: Path, entries: list[dict[str, Any]]) -> None:
    (root / INDEX_NAME).write_text(
        json.dumps({"schema": INDEX_SCHEMA, "version": 1, "packs": entries}), encoding="utf-8"
    )


def build_gallery(root: Path) -> Path:
    """A packs repository at *root* holding the three reference HUDs and two stat packs."""
    (root / "hud").mkdir(parents=True)
    (root / "stats").mkdir()
    entries = []
    for hud in HUDS:
        path = root / "hud" / f"{hud}.fpdbhud"
        shutil.copy(ROOT / "hud-packages" / path.name, path)
        entries.append(
            index_entry(
                path, pack_id=f"fpdb-3.{hud}", kind="hud", name=hud, version="1.0.0", author="fpdb-3", license=LICENSE
            )
        )
    for pack_id in ("example.steals", "example.blinds"):
        path = stat_pack(root / "stats", pack_id)
        entries.append(
            index_entry(
                path, pack_id=pack_id, kind="stats", name=pack_id, version="1.0.0", author="example", license=LICENSE
            )
        )
    write_index(root, entries)
    return root
