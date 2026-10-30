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


def _stock_popup_nodes() -> dict[str, Any]:
    """The popups every configuration has, as the shipped template defines them."""
    from fpdb_3_legacy.Configuration import _find_example_config, _parse_example_config  # noqa: PLC0415

    template = _parse_example_config(_find_example_config("HUD_config.xml"))
    if template is None:
        return {name: None for name in _stock_popups()}
    return {node.getAttribute("pu_name"): node for node in template.getElementsByTagName("pu")}


def _canonical(node: Any) -> Any:
    """A node as data: its tag, attributes and children, layout whitespace aside."""
    if node.nodeType == node.TEXT_NODE:
        return node.data.strip()
    if node.nodeType != node.ELEMENT_NODE:
        return ""
    children = tuple(child for child in (_canonical(child) for child in node.childNodes) if child)
    return (node.tagName, tuple(sorted(node.attributes.items())), children)


def _popups(document: Any, config_doc: Any, profile_node: Any, profile: str) -> Any | None:
    """The popups *profile_node* opens, and the ones those open, as a ``<popup_windows>``.

    A stock popup (``default``, ...) is left out while it is the stock one, since every
    configuration has it. One customised under its stock name goes in under a name of
    the profile's own, so it never meets the recipient's stock popup (Codex, #643);
    every reference to it, from the profile and from the other popups, follows.
    """
    popups = {node.getAttribute("pu_name"): node for node in config_doc.getElementsByTagName("pu")}
    stock = _stock_popup_nodes()
    renamed: dict[str, str] = {}
    wanted = [cell.getAttribute("popup") for cell in profile_node.getElementsByTagName("stat")]
    chosen: dict[str, Any] = {}
    while wanted:
        name = wanted.pop()
        if name in chosen or name not in popups:
            continue
        if name in stock:
            if stock[name] is None or _canonical(popups[name]) == _canonical(stock[name]):
                continue
            renamed[name] = _free_name(f"{name} ({profile})", popups)
        chosen[name] = popups[name]
        wanted.extend(row.getAttribute("pu_stat_submenu") for row in popups[name].getElementsByTagName("pu_stat"))
    _rename(profile_node.getElementsByTagName("stat"), "popup", renamed)
    if not chosen:
        return None
    container = document.createElement("popup_windows")
    for name in sorted(chosen):
        node = document.importNode(chosen[name], True)
        node.setAttribute("pu_name", renamed.get(name, name))
        _rename(node.getElementsByTagName("pu_stat"), "pu_stat_submenu", renamed)
        container.appendChild(document.createTextNode("\n  "))
        container.appendChild(node)
    container.appendChild(document.createTextNode("\n"))
    return container


def _rename(nodes: Any, attribute: str, renamed: Mapping[str, str]) -> None:
    for node in nodes:
        if node.getAttribute(attribute) in renamed:
            node.setAttribute(attribute, renamed[node.getAttribute(attribute)])


def _free_name(name: str, taken: Mapping[str, Any]) -> str:
    candidate, number = name, 2
    while candidate in taken:
        candidate, number = f"{name} {number}", number + 1
    return candidate


def _panel_rules(document: Any, config_doc: Any, profile: str) -> list[Any]:
    """The panel-rule sections that apply to *profile*, each scoped to it.

    A section scoped to the profile goes in as it is. A section for every profile --
    the one Preferences writes, its rules naming their profile one by one -- goes in
    with only the rules that apply to this profile, and scoped to it, so it changes
    nothing for the recipient's other profiles (Codex, #643).
    """
    from fpdb_3_legacy.hud_situation import profile_matches  # noqa: PLC0415

    wanted = profile.strip().casefold()
    sections = []
    for section in config_doc.getElementsByTagName("hud_panel_rules"):
        scope = section.getAttribute("profile").strip()
        if _is_panel_rule_placeholder(section) or (scope and scope.casefold() not in ("all", wanted)):
            continue
        copy = document.importNode(section, True)
        _materialise_source(document, copy)
        if scope.casefold() != wanted:
            for rule in list(copy.getElementsByTagName("hud_panel_rule")):
                if not profile_matches(rule.getAttribute("profile").strip(), profile):
                    rule.parentNode.removeChild(rule)
            if not copy.getElementsByTagName("hud_panel_rule") and not copy.getAttribute("source").strip():
                continue
            copy.setAttribute("profile", profile)
        sections.append(copy)
    return sections


def _materialise_source(document: Any, section: Any) -> None:
    """Write the rules of a section's file or folder ``source`` into it, path removed.

    The path is the sharer's own: a recipient without it could not load the
    configuration at all (Codex, #643). The shipped libraries (``builtin``,
    ``builtin_plo``) are in every fpdb and stay named. A source that cannot be
    read refuses the share rather than writing a package without its rules.
    """
    from fpdb_3_legacy import hud_situation  # noqa: PLC0415

    source = section.getAttribute("source").strip()
    if not source or source.casefold() in (hud_situation.BUILTIN_SOURCE, hud_situation.PLO_BUILTIN_SOURCE):
        return
    try:
        rules, fallback = hud_situation.load_source(source)
    except (OSError, ValueError) as exc:
        raise GalleryError([f"the panel rules in {source} cannot be read: {exc}"]) from exc
    section.removeAttribute("source")
    if fallback and not section.getAttribute("fallback").strip():
        section.setAttribute("fallback", fallback)
    # The source's rules come before the section's own, as the configuration reads them.
    first = section.firstChild
    for rule in rules:
        node = document.createElement("hud_panel_rule")
        for name, value in rule.as_xml_attributes().items():
            node.setAttribute(name, value)
        section.insertBefore(node, first)


def hud_package(config_doc: Any, profile: str) -> bytes:
    """The ``.fpdbhud`` package of *profile*: the profile, the popups it opens, and its panel rules.

    Game bindings and table layouts are the sharer's own, and are not shared: a
    gallery HUD never binds itself to a game.
    """
    source = next(
        (node for node in config_doc.getElementsByTagName("ss") if node.getAttribute("name") == profile), None
    )
    if source is None:
        raise GalleryError([f"there is no HUD profile named {profile!r}"])
    document = config_doc.implementation.createDocument(None, "fpdb_hud_package", None)
    root = document.documentElement
    root.setAttribute("version", "1.0")
    profile_node = document.importNode(source, True)
    popups = _popups(document, config_doc, profile_node, profile)
    parts = [profile_node, *([popups] if popups is not None else []), *_panel_rules(document, config_doc, profile)]
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
