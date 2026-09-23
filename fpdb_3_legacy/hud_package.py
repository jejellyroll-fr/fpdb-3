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


def merge_package_profile_rules(
    config_doc: Any,
    package_root: Any,
    *,
    profile_names: Mapping[str, str] | None = None,
    overwrite: bool,
) -> bool:
    """Merge ``<hud_profile_rule>`` entries carried by a package.

    A rule is what lets a profile apply to some tables and not others -- a
    Fast-Fold stat set is only wanted on Fast-Fold tables, and binding it to the
    game instead would replace the profile every ordinary cash table uses.

    Rules are matched on what they select, not on their id, so importing the
    same package twice does not stack duplicates. ``profile_names`` rewrites the
    profile reference when the imported profile was renamed on conflict.
    """
    changed = False
    names = profile_names or {}
    source_rules = package_root.getElementsByTagName("hud_profile_rule")
    if not source_rules:
        return False

    section = _container(config_doc, "hud_profile_rules")
    # HUD profile rules serialize the betting limit as `limit`; accept the
    # in-memory spelling too, so re-importing a package replaces its selector
    # instead of accumulating duplicate rules.
    selectors = ("site", "game", "game_type", "limit", "seats", "players", "speed")

    for source_rule in source_rules:
        profile = source_rule.getAttribute("profile")
        if not profile:
            continue
        wanted = {name: source_rule.getAttribute(name) for name in selectors}
        existing = next(
            (
                node
                for node in config_doc.getElementsByTagName("hud_profile_rule")
                if all(
                    (node.getAttribute(name) or (node.getAttribute("limit_type") if name == "limit" else "")) == value
                    for name, value in wanted.items()
                )
            ),
            None,
        )
        if existing is not None and not overwrite:
            continue

        imported = _append_imported(config_doc, section, source_rule)
        imported.setAttribute("profile", names.get(profile, profile))
        if existing is not None:
            existing.parentNode.removeChild(existing)
        changed = True

    return changed


def _is_panel_rule_placeholder(section: Any) -> bool:
    """Whether a ``<hud_panel_rules>`` section is the shipped empty one.

    ``HUD_config.xml.example`` carries a disabled, rule-less section so the
    option is discoverable before it is used. That section is not a user's
    configuration: refusing to import over it left dynamic panels off on every
    standard install, which is the opposite of what the reference package is
    for. A section the user enabled, or one carrying rules of their own, is
    preserved exactly as before.
    """
    enabled = str(section.getAttribute("enabled") or "").strip().lower()
    if enabled in ("1", "true", "yes", "on"):
        return False
    return not section.getElementsByTagName("hud_panel_rule")


def merge_package_panel_rules(
    config_doc: Any,
    package_root: Any,
    *,
    overwrite: bool = False,
    profile_names: Mapping[str, str] | None = None,
) -> bool:
    """Merge a package's ``<hud_panel_rules>`` section into a configuration.

    Dynamic panels (#298) are configured once for the whole application, so a
    package that ships blocks for them has to be careful: importing the
    Dynamic reference HUD (#332) must not silently turn dynamic panels on for
    every other profile. Three rules keep that honest.

    * Profile-scoped sections from different packages coexist. Reimporting a
      package only replaces the section for the same profile when overwrite is
      requested; unrelated profiles and user rules remain intact.
    * The section may scope the shipped library to one profile with a
      ``profile`` attribute, so enabling the reference blocks enables them for
      the packaging profile only.
    * ``profile_names`` rewrites that scope when the imported profile had to be
      renamed: left behind, the section would enable the panels for the profile
      that already existed -- the very reason for the rename -- while the newly
      imported one resolved no rule at all.
    """
    sources = _direct_children(package_root, "hud_panel_rules")
    if not sources:
        # Also accept the section nested in a wrapper, the way popups are.
        sources = package_root.getElementsByTagName("hud_panel_rules")
    if not sources:
        return False

    existing = list(config_doc.getElementsByTagName("hud_panel_rules"))
    changed = False
    names = profile_names or {}
    for source in sources:
        imported = config_doc.importNode(source, True)
        _repoint_panel_rule_profile(imported, names)
        imported_scope = imported.getAttribute("profile").strip().casefold()
        matching = [
            node for node in existing
            if node.getAttribute("profile").strip().casefold() == imported_scope
            and not _is_panel_rule_placeholder(node)
        ]
        if matching and not overwrite:
            continue
        for old in matching:
            old.parentNode.removeChild(old)
            existing.remove(old)
        # The stock disabled/empty section is a placeholder, not user state.
        for old in list(existing):
            if _is_panel_rule_placeholder(old):
                old.parentNode.removeChild(old)
                existing.remove(old)
        config_doc.documentElement.appendChild(config_doc.createTextNode("\n    "))
        config_doc.documentElement.appendChild(imported)
        existing.append(imported)
        changed = True
    if changed:
        config_doc.documentElement.appendChild(config_doc.createTextNode("\n"))
    return changed


def _repoint_panel_rule_profile(section: Any, names: Mapping[str, str]) -> None:
    """Rewrite the profile a panel-rule section is scoped to, after a rename."""
    scope = section.getAttribute("profile")
    if scope and scope in names:
        section.setAttribute("profile", names[scope])
    for rule in section.getElementsByTagName("hud_panel_rule"):
        target = rule.getAttribute("profile")
        if target and target in names:
            rule.setAttribute("profile", names[target])


def install_missing_hud_package(config_doc: Any, package_root: Any) -> bool:
    """Install missing profiles, popups, bindings and panel rules.

    Additive by construction: an existing profile, popup, binding or panel-rule
    section is the user's, and stays.
    """
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
        or merge_package_panel_rules(config_doc, package_root, overwrite=False)
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


def _is_untouched_legacy_popup(target: Any, source: Any, legacy_classes: frozenset[str]) -> bool:
    if target.getAttribute("pu_class") not in legacy_classes:
        return False
    presentation_attributes = {
        name for name in target.attributes.keys() if name.startswith("pu_") and name not in {"pu_name", "pu_class"}
    }
    if presentation_attributes:
        return False

    source_names = {
        node.getAttribute("pu_stat_name")
        for node in _direct_children(source, "pu_stat")
        if node.getAttribute("pu_stat_name")
    }
    target_stats = _direct_children(target, "pu_stat")
    if not target_stats:
        return False
    return all(
        stat.getAttribute("pu_stat_name") in source_names and set(stat.attributes.keys()) == {"pu_stat_name"}
        for stat in target_stats
    )


def upgrade_legacy_popup_presentation(
    config_doc: Any,
    package_root: Any,
    *,
    popup_name: str,
    legacy_classes: frozenset[str] = frozenset({"", "default"}),
) -> bool:
    """Upgrade an untouched legacy popup to the package's rich presentation.

    Existing named popups normally belong to the user and must not be
    overwritten. There is one safe exception: an old stock popup whose class
    is still ``default`` and whose rows contain only known bare stat names.
    Any presentation attribute, custom row attribute or unknown statistic
    makes the popup user-owned and leaves it untouched.

    The helper is package-driven and contains no game or stat names, so future
    HUD packages can reuse the same migration contract.
    """
    source = _named_node(package_root, "pu", "pu_name", popup_name)
    target = _named_node(config_doc, "pu", "pu_name", popup_name)
    if source is None or target is None or not _is_untouched_legacy_popup(target, source, legacy_classes):
        return False

    for name in list(target.attributes.keys()):
        if name != "pu_name":
            target.removeAttribute(name)
    for name in source.attributes.keys():
        if name != "pu_name":
            target.setAttribute(name, source.getAttribute(name))
    while target.firstChild:
        target.removeChild(target.firstChild)
    for source_stat in _direct_children(source, "pu_stat"):
        _append_imported(config_doc, target, source_stat)
    if _direct_children(target, "pu_stat"):
        target.appendChild(config_doc.createTextNode("\n    "))
    return True
