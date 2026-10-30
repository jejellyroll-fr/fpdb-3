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
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

import defusedxml.minidom

from fpdb_3_legacy import pack_gallery, stat_packs
from fpdb_3_legacy.hud_package import _stock_popups
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


def _submenus(popup: Any) -> list[str]:
    return [row.getAttribute("pu_stat_submenu") for row in popup.getElementsByTagName("pu_stat")]


def _needed(popups: Mapping[str, Any], stock: Mapping[str, Any]) -> set[str]:
    """The popups a package must carry: the sharer's own, and every one leading to them.

    A popup of the sharer's own is one the stock template lacks, or a stock one they
    customised. A stock popup left as shipped still has to go in when one of its
    submenus does, since its copy must open the package's version (Codex, #643).
    Worked out to a fixed point, so a cycle of submenus is no trouble.
    """
    needed = {
        name
        for name, node in popups.items()
        if name not in stock or (stock[name] is not None and _canonical(node) != _canonical(stock[name]))
    }
    grew = True
    while grew:
        grew = False
        for name, node in popups.items():
            if name not in needed and any(child in needed for child in _submenus(node)):
                needed.add(name)
                grew = True
    return needed


def _popups(document: Any, config_doc: Any, profile_node: Any, profile: str) -> Any | None:
    """The popups *profile_node* opens, and the ones those open, as a ``<popup_windows>``.

    A stock popup (``default``, ...) is left out while it and everything it opens
    are as shipped, since every configuration has it. One that has to go in goes
    under a name of the profile's own, so it never meets the recipient's stock
    popup (Codex, #643); every reference to it, from the profile and from the other
    popups, follows.
    """
    popups = {node.getAttribute("pu_name"): node for node in config_doc.getElementsByTagName("pu")}
    stock = _stock_popup_nodes()
    needed = _needed(popups, stock)
    wanted = [cell.getAttribute("popup") for cell in profile_node.getElementsByTagName("stat")]
    chosen: list[str] = []
    while wanted:
        name = wanted.pop()
        if name in needed and name not in chosen:
            chosen.append(name)
            wanted.extend(_submenus(popups[name]))
    renamed: dict[str, str] = {}
    for name in sorted(name for name in chosen if name in stock):
        renamed[name] = _free_name(f"{name} ({profile})", {*popups, *renamed.values()})
    _rename(profile_node.getElementsByTagName("stat"), "popup", renamed)
    if not chosen:
        return None
    container = document.createElement("popup_windows")
    for name in sorted(chosen):
        node = document.importNode(popups[name], True)
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


def _free_name(name: str, taken: Iterable[str]) -> str:
    taken = set(taken)
    candidate, number = name, 2
    while candidate in taken:
        candidate, number = f"{name} {number}", number + 1
    return candidate


def _carries(section: Any) -> bool:
    """Whether *section* has anything to read: rules of its own or a ``source``.

    One with a ``source`` and no rule of its own counts, whether or not it says
    ``enabled``: the configuration reads an unstated ``enabled`` as on (Codex, #643).
    """
    return bool(section.getElementsByTagName("hud_panel_rule")) or bool(section.getAttribute("source").strip())


def _rules_for(section: Any, profile: str, scope: str) -> list[Any]:
    """The rules of *section* that belong to *profile*, read as the configuration reads them.

    A rule's own profile wins; a rule naming none takes its section's *scope*, as
    ``hud_situation.scope_rules`` gives it. Whatever section it sits in, a rule
    belongs to the profile when that comes out as the profile or as every profile
    (Codex, #643). Both sides are normalised as the resolver normalises them:
    Preferences save "My HUD" as "my hud".
    """
    from fpdb_3_legacy.hud_situation import _text, profile_matches  # noqa: PLC0415

    wanted, default = _text(profile, "all"), _text(scope, "all")
    kept = []
    for rule in section.getElementsByTagName("hud_panel_rule"):
        own = _text(rule.getAttribute("profile"), "all")
        if profile_matches(default if own == "all" else own, wanted):
            kept.append(rule)
    return kept


def _panel_rules(document: Any, config_doc: Any, profile: str) -> list[Any]:
    """The panel rules that apply to *profile*, as one section scoped to it.

    Each rule goes in when it belongs to the profile, whichever section holds it, so
    the package changes nothing for the recipient's other profiles. Several sections
    become one, in the order the configuration reads them: an install keeps a single
    section per profile, and would drop the others (Codex, #643).
    """
    # A disabled section is not read, however many there are (Codex, #643).
    enabled = [section for section in config_doc.getElementsByTagName("hud_panel_rules") if _enabled(section)]
    sections = [section for section in enabled if _carries(section)]
    wanted = profile.strip().casefold()
    prepared = []
    for section in sections:
        scope = section.getAttribute("profile").strip()
        foreign = scope.casefold() not in ("", "all", wanted)
        copy = document.importNode(section, True)
        # Another profile's library is not this one's: only its rules naming this profile can come.
        _materialise_source(document, copy, shipped=foreign)
        prepared.append((copy, scope))
    contributing = [
        (copy, scope)
        for copy, scope in prepared
        if _rules_for(copy, profile, scope) or copy.getAttribute("source").strip()
    ]
    if not contributing:
        return []
    if len(contributing) > 1:
        # The shipped library is written out too, so its rules keep their place among the others.
        for copy, _scope in contributing:
            _materialise_source(document, copy, shipped=True)
    merged = document.createElement("hud_panel_rules")
    merged.setAttribute("enabled", "true")
    own_scope = next((scope for _copy, scope in contributing if scope.casefold() == wanted), profile)
    merged.setAttribute("profile", own_scope)
    # The fallback is the first one read, from any enabled section, one with nothing
    # else in it included (Codex, #643); a section's file source gave it its own.
    copies = {id(section): copy for section, (copy, _scope) in zip(sections, prepared, strict=True)}
    for section in enabled:
        _carry_attributes(merged, copies.get(id(section), section), source=False)
    for copy, scope in contributing:
        _carry_attributes(merged, copy, source=True)
        for rule in _rules_for(copy, profile, scope):
            merged.appendChild(document.createTextNode("\n  "))
            merged.appendChild(rule)
    merged.appendChild(document.createTextNode("\n"))
    return [merged]


def _carry_attributes(merged: Any, section: Any, *, source: bool) -> None:
    """The first fallback read, or the shipped library a lone section still names."""
    if not source:
        if merged.getAttribute("fallback").strip():
            return
        fallback = section.getAttribute("fallback").strip()
        if not fallback and section.getAttribute("source").strip():
            # A library still named by its source brings its own fallback, read in its turn (Codex, #643).
            from fpdb_3_legacy import hud_situation  # noqa: PLC0415

            fallback = hud_situation.load_source(section.getAttribute("source").strip())[1]
        if fallback:
            merged.setAttribute("fallback", fallback)
        return
    if section.getAttribute("source").strip():
        merged.setAttribute("source", section.getAttribute("source").strip())


def _enabled(section: Any) -> bool:
    return section.getAttribute("enabled").strip().lower() not in ("false", "no", "0", "off")


def _materialise_source(document: Any, section: Any, *, shipped: bool = False) -> None:
    """Write the rules of a section's file or folder ``source`` into it, path removed.

    The path is the sharer's own: a recipient without it could not load the
    configuration at all (Codex, #643). The shipped libraries (``builtin``,
    ``builtin_plo``) are in every fpdb and stay named, unless *shipped* asks for
    their rules too. A source that cannot be read refuses the share rather than
    writing a package without its rules.
    """
    from fpdb_3_legacy import hud_situation  # noqa: PLC0415

    source = section.getAttribute("source").strip()
    library = source.casefold() in (hud_situation.BUILTIN_SOURCE, hud_situation.PLO_BUILTIN_SOURCE)
    if not source or (library and not shipped):
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
