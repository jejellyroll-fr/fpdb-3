"""Share this HUD / pack: write a package ready to submit to the pack gallery (#449).

The gallery's repository (``fpdb-3-packs``) takes a pack as a pull request:
the package where the repository keeps its kind, and the entry that lists it in
``index.json``. This module writes exactly that, in a folder laid out like the
repository::

    <id>/
      hud/<id>.fpdbhud                 a HUD profile
      stats/<id>.fpdbstats             or a stat pack, built as the repository builds it,
      sources/stats/<id>/...           with its readable files
      index-entry.json                 the entry to add to index.json

A contributor copies the folder's content into their copy of the repository,
adds the entry to ``index.json`` and opens the pull request.

Nothing is written for a package the gallery would refuse: the entry and the
package go through the checks an install runs
(:func:`pack_gallery.package_problems_for`) before the folder appears, and the
folder appears whole or not at all.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import defusedxml.minidom

from fpdb_3_legacy import pack_gallery, stat_packs
from fpdb_3_legacy.hud_package import _is_panel_rule_placeholder, _stock_popups
from fpdb_3_legacy.pack_gallery import GalleryError

#: The file beside the package that holds its index entry.
ENTRY_NAME: Final = "index-entry.json"


def profile_names(config_doc: Any) -> list[str]:
    """The HUD profiles of a configuration, as it lists them."""
    return [node.getAttribute("name") for node in config_doc.getElementsByTagName("ss") if node.getAttribute("name")]


def hud_package(config_doc: Any, profile: str) -> bytes:
    """The ``.fpdbhud`` package of *profile*: the profile, the popups it opens, and its panel rules.

    The popups are the ones of this configuration the profile's cells open,
    and the ones those open in turn; a stock popup (``default``, ...) is left
    out, since every configuration has it. The panel rules are the sections
    scoped to the profile. Game bindings and table layouts are the sharer's
    own, and are not shared: a gallery HUD never binds itself to a game.
    """
    source = next(
        (node for node in config_doc.getElementsByTagName("ss") if node.getAttribute("name") == profile), None
    )
    if source is None:
        raise GalleryError([f"there is no HUD profile named {profile!r}"])
    document = config_doc.implementation.createDocument(None, "fpdb_hud_package", None)
    root = document.documentElement
    root.setAttribute("version", "1.0")
    parts = [document.importNode(source, True)]

    popups = {node.getAttribute("pu_name"): node for node in config_doc.getElementsByTagName("pu")}
    stock = _stock_popups()
    wanted = [cell.getAttribute("popup") for cell in source.getElementsByTagName("stat")]
    chosen: dict[str, Any] = {}
    while wanted:
        name = wanted.pop()
        if name in chosen or name in stock or name not in popups:
            continue
        chosen[name] = popups[name]
        wanted.extend(row.getAttribute("pu_stat_submenu") for row in popups[name].getElementsByTagName("pu_stat"))
    if chosen:
        container = document.createElement("popup_windows")
        for name in sorted(chosen):
            container.appendChild(document.createTextNode("\n  "))
            container.appendChild(document.importNode(chosen[name], True))
        container.appendChild(document.createTextNode("\n"))
        parts.append(container)

    parts.extend(
        document.importNode(section, True)
        for section in config_doc.getElementsByTagName("hud_panel_rules")
        if section.getAttribute("profile").strip().casefold() == profile.strip().casefold()
        and not _is_panel_rule_placeholder(section)
    )
    for part in parts:
        root.appendChild(document.createTextNode("\n"))
        root.appendChild(part)
    root.appendChild(document.createTextNode("\n"))
    return document.toxml(encoding="utf-8") + b"\n"


def share_hud(
    config_doc: Any,
    profile: str,
    destination: Path,
    *,
    pack_id: str,
    name: str,
    version: str,
    author: str,
    license: str,  # noqa: A002 - the index's own field name
    description: str = "",
) -> Path:
    """Write *profile* as a HUD ready to submit; the folder written."""
    package = hud_package(config_doc, profile)
    cells = defusedxml.minidom.parseString(package).getElementsByTagName("stat")
    stats = list(dict.fromkeys(cell.getAttribute("_stat_name") for cell in cells if cell.getAttribute("_stat_name")))
    fields = {
        "id": pack_id,
        "kind": "hud",
        "name": name,
        "version": version,
        "author": author,
        "license": license,
        "description": description,
        "file": f"hud/{pack_id}{pack_gallery.KINDS['hud']}",
        "stats": stats,
    }
    return _write(Path(destination), fields, package)


def share_stat_pack(
    pack_id: str,
    destination: Path,
    *,
    license: str,  # noqa: A002 - the index's own field name
    name: str = "",
    author: str = "",
    description: str = "",
    packs_dir: Path | None = None,
) -> Path:
    """Write an installed stat pack ready to submit; the folder written.

    The id, the version and the minimum fpdb version are the pack's own, as
    the gallery requires; the name, author and description default to its
    manifest's.
    """
    pack = stat_packs.read_pack(stat_packs._pack_dir(stat_packs._root(packs_dir), pack_id))
    fields = {
        "id": pack.id,
        "kind": "stats",
        "name": name or pack.name,
        "version": pack.pack_version,
        "author": author or pack.author,
        "license": license,
        "description": description or pack.description,
        "file": f"stats/{pack.id}{stat_packs.PACK_SUFFIX}",
        "stats": [definition.name for definition in pack.definitions],
    }
    if pack.min_fpdb_version:
        fields["min_fpdb_version"] = pack.min_fpdb_version
    sources = {f"sources/stats/{pack.id}/{member}": data for member, data in pack.files.items()}
    return _write(Path(destination), fields, stat_packs.pack_archive(pack), sources)


def _write(
    destination: Path, fields: Mapping[str, Any], package: bytes, sources: Mapping[str, bytes] | None = None
) -> Path:
    """Check the entry and the package as an install would, then write the folder whole."""
    entry = {key: value for key, value in fields.items() if value not in ("", [])}
    entry |= {"sha256": hashlib.sha256(package).hexdigest(), "size": len(package)}
    checked = pack_gallery._entry(entry)  # raises GalleryError with every problem in the entry
    problems = pack_gallery.package_problems_for(checked, package)
    if problems:
        raise GalleryError(problems, checked.id)
    target = destination / checked.id
    if target.exists():
        raise GalleryError([f"{target} already exists: choose another folder, or remove it first"])
    staging = Path(tempfile.mkdtemp(prefix=f".{checked.id}.", dir=destination))
    try:
        for relative, data in {checked.file: package, **(sources or {})}.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        text = json.dumps(entry, indent=2, ensure_ascii=False) + "\n"
        (staging / ENTRY_NAME).write_text(text, encoding="utf-8")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target
