"""Small, testable helpers for merging FPDB HUD packages into a config."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _direct_children(node: Any, tag_name: str) -> list[Any]:
    """Return element children named *tag_name*, excluding nested matches."""
    return [child for child in node.childNodes if child.nodeType == child.ELEMENT_NODE and child.tagName == tag_name]


def _container(doc: Any, tag_name: str) -> Any:
    """Return a top-level config container, creating it when absent."""
    nodes = doc.getElementsByTagName(tag_name)
    if nodes:
        return nodes[0]
    node = doc.createElement(tag_name)
    doc.documentElement.appendChild(doc.createTextNode("\n    "))
    doc.documentElement.appendChild(node)
    doc.documentElement.appendChild(doc.createTextNode("\n"))
    return node


def _append_imported(target_doc: Any, parent: Any, source: Any) -> Any:
    parent.appendChild(target_doc.createTextNode("\n        "))
    imported = target_doc.importNode(source, True)
    parent.appendChild(imported)
    return imported


def _named_node(doc: Any, tag_name: str, attribute: str, value: str) -> Any | None:
    return next(
        (node for node in doc.getElementsByTagName(tag_name) if node.getAttribute(attribute) == value),
        None,
    )


def merge_package_game_bindings(
    config_doc: Any,
    package_root: Any,
    *,
    profile_names: Mapping[str, str] | None = None,
    overwrite: bool,
) -> bool:
    """Merge direct package ``<game>`` bindings into a HUD configuration.

    ``profile_names`` rewrites stat-set references when an imported profile was
    renamed by the user. Explicit package imports pass ``overwrite=True`` so
    the requested profile becomes active. Automatic migrations pass
    ``overwrite=False`` and therefore preserve an existing user's choice.
    """
    changed = False
    names = profile_names or {}
    supported_games = _container(config_doc, "supported_games")

    for source_game in _direct_children(package_root, "game"):
        game_name = source_game.getAttribute("game_name")
        if not game_name:
            continue
        existing_game = _named_node(config_doc, "game", "game_name", game_name)
        if existing_game is None:
            imported_game = _append_imported(config_doc, supported_games, source_game)
            for game_stat_set in imported_game.getElementsByTagName("game_stat_set"):
                source_name = game_stat_set.getAttribute("stat_set")
                if source_name in names:
                    game_stat_set.setAttribute("stat_set", names[source_name])
            changed = True
            continue

        existing_by_type = {
            node.getAttribute("game_type"): node for node in _direct_children(existing_game, "game_stat_set")
        }
        for source_mapping in _direct_children(source_game, "game_stat_set"):
            game_type = source_mapping.getAttribute("game_type")
            source_name = source_mapping.getAttribute("stat_set")
            target_name = names.get(source_name, source_name)
            existing_mapping = existing_by_type.get(game_type)
            if existing_mapping is None:
                imported_mapping = _append_imported(config_doc, existing_game, source_mapping)
                imported_mapping.setAttribute("stat_set", target_name)
                changed = True
            elif overwrite and existing_mapping.getAttribute("stat_set") != target_name:
                existing_mapping.setAttribute("stat_set", target_name)
                changed = True

    return changed


def install_missing_hud_package(config_doc: Any, package_root: Any) -> bool:
    """Install missing profiles, popups and bindings without overwriting users."""
    changed = False
    stat_sets = _container(config_doc, "stat_sets")

    for source_profile in _direct_children(package_root, "ss"):
        profile_name = source_profile.getAttribute("name")
        if profile_name and _named_node(config_doc, "ss", "name", profile_name) is None:
            _append_imported(config_doc, stat_sets, source_profile)
            changed = True

    popup_windows = _container(config_doc, "popup_windows")
    for source_popup in _direct_children(package_root, "pu"):
        popup_name = source_popup.getAttribute("pu_name")
        if popup_name and _named_node(config_doc, "pu", "pu_name", popup_name) is None:
            _append_imported(config_doc, popup_windows, source_popup)
            changed = True

    return (
        merge_package_game_bindings(
            config_doc,
            package_root,
            overwrite=False,
        )
        or changed
    )


def merge_missing_profile_stats(
    config_doc: Any,
    package_root: Any,
    *,
    profile_name: str,
    stat_names: set[str],
    recognized_dimensions: set[tuple[int, int]],
) -> bool:
    """Extend a shipped profile without overwriting a customized one.

    Automatic HUD migrations normally leave existing profiles untouched. A
    later package version may nevertheless add cells that did not exist in the
    original shipped grid. Only profiles whose dimensions match a known
    shipped version are extended, and an occupied cell is never replaced.
    """
    source = _named_node(package_root, "ss", "name", profile_name)
    target = _named_node(config_doc, "ss", "name", profile_name)
    if source is None or target is None:
        return False
    try:
        dimensions = (int(target.getAttribute("rows")), int(target.getAttribute("cols")))
    except ValueError:
        return False
    if dimensions not in recognized_dimensions:
        return False

    existing_names = {node.getAttribute("_stat_name") for node in _direct_children(target, "stat")}
    occupied = {node.getAttribute("_rowcol") for node in _direct_children(target, "stat")}
    changed = False
    for source_stat in _direct_children(source, "stat"):
        name = source_stat.getAttribute("_stat_name")
        position = source_stat.getAttribute("_rowcol")
        if name not in stat_names or name in existing_names or position in occupied:
            continue
        _append_imported(config_doc, target, source_stat)
        existing_names.add(name)
        occupied.add(position)
        changed = True

    if changed:
        target.setAttribute(
            "rows",
            str(max(dimensions[0], int(source.getAttribute("rows")))),
        )
    return changed
