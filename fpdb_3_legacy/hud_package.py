"""Small, testable helpers for merging FPDB HUD packages into a config."""

from __future__ import annotations

import re
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
    # A user-created global section governs every profile. Adding a package's
    # scoped rules beside it would silently change the global panel behavior.
    # Preserve it; package-scoped sections may still coexist with each other.
    if any(not node.getAttribute("profile").strip() and not _is_panel_rule_placeholder(node) for node in existing):
        return False
    changed = False
    names = profile_names or {}
    for source in sources:
        imported = config_doc.importNode(source, True)
        _repoint_panel_rule_profile(imported, names)
        imported_scope = imported.getAttribute("profile").strip().casefold()
        matching = [
            node
            for node in existing
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


def _stock_popups() -> set[str]:
    """The popups every configuration has: the ones the shipped template defines (``default``, ...)."""
    from fpdb_3_legacy.Configuration import _find_example_config, _parse_example_config  # noqa: PLC0415

    template = _parse_example_config(_find_example_config("HUD_config.xml"))
    if template is None:
        return set()
    return {node.getAttribute("pu_name") for node in template.getElementsByTagName("pu")}


# The most rows or columns a grid may have. No HUD panel comes near it, and it bounds what a
# package can make the checker and the HUD lay out: a colspan of a billion is refused, not
# expanded (Codex, #640).
_MAX_GRID = 100

# The numbers the configuration loader reads with int() or float(), by element: one it cannot
# read stops the whole configuration from loading (Codex, #640).
_LOADER_NUMBERS: dict[str, dict[str, type]] = {
    "ss": {"xpad": int, "ypad": int},
    "block": {"cell_width": int, "x": int, "y": int, "title_font_scale": float, "heading_font_scale": float},
}


def _grid_number(node: Any, attribute: str, default: int, minimum: int = 1) -> int | None:
    """A whole number attribute from *minimum* to ``_MAX_GRID``, *default* when absent, ``None`` otherwise."""
    text = node.getAttribute(attribute)
    if not text:
        return default
    return int(text) if re.fullmatch("[0-9]{1,3}", text) and minimum <= int(text) <= _MAX_GRID else None


def _number_problems(node: Any) -> list[str]:
    """The attributes of *node* the configuration loader converts to a number and could not."""
    problems = []
    for attribute, convert in _LOADER_NUMBERS.get(node.tagName, {}).items():
        text = node.getAttribute(attribute)
        try:
            if text:
                convert(text)
        except ValueError:
            problems.append(f"{attribute} {text!r} is not a number")
    return problems


def _rowcol(text: str) -> tuple[int, int] | None:
    """``"(r,c)"``, both from 1 to ``_MAX_GRID``, as numbers; ``None`` when it is not one."""
    parts = [part.strip() for part in text[1:-1].split(",")] if text.startswith("(") and text.endswith(")") else []
    if len(parts) != 2 or not all(re.fullmatch("[0-9]{1,3}", part) and 0 < int(part) <= _MAX_GRID for part in parts):
        return None
    return int(parts[0]), int(parts[1])


_SIZE_PROBLEM = f"rows and cols must be whole numbers up to {_MAX_GRID}"


def _grid_problems(grid: Any) -> list[str]:  # noqa: C901 - one rule per item kind, each with its reason
    """Why the items of one grid would not load as placed (Codex, #640).

    The rules are the configuration loader's: a stat must say where it sits, as
    ``(row,col)`` from 1 -- it fails to load otherwise -- and two items on one
    cell overwrite each other. ``<text>`` headers and ``<hline>`` separators may
    span columns, and sit on the first cell when they do not say where. A grid
    that states its size keeps its items inside it; one that does not (or says
    0) takes its size from its items. Empty cells are allowed.
    """
    rows, cols = _grid_number(grid, "rows", 0, minimum=0), _grid_number(grid, "cols", 0, minimum=0)
    if rows is None or cols is None:
        return [_SIZE_PROBLEM]
    problems = []
    occupied: dict[tuple[int, int], str] = {}
    items = [node for node in grid.getElementsByTagName("*") if node.tagName in ("stat", "text", "hline")]
    for item in items:
        name = item.getAttribute("_stat_name") or item.getAttribute("label") or item.tagName
        text = item.getAttribute("_rowcol")
        if not text and item.tagName != "stat":
            text = "(1,1)"  # where the loader places a header or separator that does not say
        position = _rowcol(text)
        if position is None:
            found = f"an invalid _rowcol {text!r}" if text else "no _rowcol"
            problems.append(f"{name} has {found}; write where it sits as (row,col), counted from 1")
            continue
        separator = item.tagName == "hline"
        span = _grid_number(item, "colspan", 0 if separator else 1, minimum=0 if separator else 1)
        if separator and span == 0:
            span = cols or 1  # a separator with no span, or a span of 0, crosses the whole block (Codex, #640)
        if span is None:
            problems.append(f"{name} at {text}: colspan must be a whole number from 1 to {_MAX_GRID}")
            continue
        row, col = position
        if (rows and row > rows) or col + span - 1 > (cols or _MAX_GRID):
            problems.append(f"{name} at {text} is outside the {rows or '?'}x{cols or '?'} grid")
            continue
        if separator:
            continue  # a separator draws between rows rather than filling cells
        for column in range(col, col + span):
            other = occupied.get((row, column))
            if other is not None:
                problems.append(f"{name} at {text} overlaps {other}")
                break
            occupied[(row, column)] = f"{name} at {text}"
    return problems


def package_problems(root: Any) -> list[str]:
    """Why the ``<fpdb_hud_package>`` element *root* cannot be installed, or ``[]`` (#449).

    The checks a shared package must pass before anything is written: it is a
    package, every profile has a name, every item of every grid sits on a
    cell of its own inside the grid, every stat it names exists, and every popup it opens is defined in it or
    in the shipped library or the stock configuration. A stat or a popup that does not resolve would be a
    permanently empty cell, so the package is refused with the names instead.
    """
    if getattr(root, "tagName", "") != "fpdb_hud_package":
        return ["the root element must be <fpdb_hud_package>"]
    profiles = _direct_children(root, "ss")
    if not profiles:
        return ["the package holds no HUD profile (<ss>)"]
    problems = [
        f"profile {position} has no name"
        for position, profile in enumerate(profiles, 1)
        if not profile.getAttribute("name")
    ]
    for profile in profiles:
        name = profile.getAttribute("name")
        # The loader reads a profile's own size whether or not it has blocks (Codex, #640).
        if not (profile.getAttribute("rows") and profile.getAttribute("cols")):
            problems.append(f"{name}: a profile needs rows and cols")
        # As the loader finds them: blocks at any depth.
        blocks = profile.getElementsByTagName("block")
        size = [_grid_number(profile, attribute, 0, minimum=0) for attribute in ("rows", "cols")]
        if blocks and None in size:
            problems.append(f"{name}: {_SIZE_PROBLEM}")  # without blocks, the profile is the grid checked below
        problems.extend(f"{name}: {problem}" for problem in _number_problems(profile))
        for grid in blocks or [profile]:
            where = grid.getAttribute("name") or grid.getAttribute("label") or name
            found = (_number_problems(grid) if grid is not profile else []) + _grid_problems(grid)
            problems.extend(f"{where}: {problem}" for problem in found)

    from fpdb_3_legacy import Stats, popup_packs  # noqa: PLC0415 - the stat catalogue is heavy
    from fpdb_3_legacy.stats_table import TABLE_STAT_FUNCTIONS  # noqa: PLC0415

    # Player stats, and the table stats a cell may show too (the table's smallest stack).
    known = frozenset(Stats.get_valid_stats()) | frozenset(TABLE_STAT_FUNCTIONS)
    named = {cell.getAttribute("_stat_name") for cell in root.getElementsByTagName("stat")}
    named |= {
        row.getAttribute("pu_stat_name")
        for row in root.getElementsByTagName("pu_stat")
        # A navigation row's "stat" is the text it shows, not a statistic.
        if not row.getAttribute("pu_stat_submenu")
    }
    # A trailing _<digit> asks for that many decimal places (vpip_0), as Stats.do_stat reads it (Codex, #640).
    unknown = sorted(name for name in named if name not in known and re.sub("_[0-9]$", "", name) not in known)
    if unknown:
        problems.append(f"unknown stat(s): {', '.join(unknown)}")

    library = popup_packs.load_default_registry()
    available = {node.getAttribute("pu_name") for node in root.getElementsByTagName("pu")}
    for pack in library.names():
        available |= set(library.packs[pack].nodes)
    available |= _stock_popups()
    opened = {cell.getAttribute("popup") for cell in root.getElementsByTagName("stat") if cell.getAttribute("popup")}
    opened |= {row.getAttribute("pu_stat_submenu") for row in root.getElementsByTagName("pu_stat")} - {""}
    missing = sorted(opened - available)
    if missing:
        problems.append(f"popup(s) neither in the package nor in the shipped library: {', '.join(missing)}")
    return problems
