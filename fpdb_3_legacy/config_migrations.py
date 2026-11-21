"""Versioned, conservative HUD configuration upgrades and reference diagnostics."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fpdb_3_legacy import config_xml as cx

# The attributes that name what an element is: a binding is reported under the
# nearest element (itself or an ancestor) carrying one of them.
_OWNER_KEYS = ("game_name", "site_name", "name")


def _owner_label(doc, node, default: str) -> str:
    """The name of the game, site or definition that holds ``node``."""
    owner = node
    while not any(cx.has_attr(owner, key) for key in _OWNER_KEYS):
        parent = cx.parent_of(doc, owner)
        if parent is None:
            break
        owner = parent
    return next((cx.attr(owner, key) for key in _OWNER_KEYS if cx.has_attr(owner, key)), default)


def reference_errors(doc) -> list[str]:
    """Report every unresolved HUD binding, including its owning game/site."""
    definitions = {
        kind: {cx.attr(n, "name") for n in cx.find_all(doc, tag)}
        for kind, tag in (("aux", "aw"), ("stat_set", "ss"), ("layout_set", "ls"))
    }
    errors = []
    for node in cx.find_all(doc, "*"):
        tag = cx.tag_of(node)
        bindings = [(attr, attr) for attr in ("aux", "stat_set", "layout_set")]
        if tag == "layout_set":
            bindings.append(("ls", "layout_set"))
        if tag == "hud_profile_rule":
            bindings.append(("profile", "stat_set"))
        for attr, kind in bindings:
            if not cx.has_attr(node, attr):
                continue
            names = cx.attr(node, attr).split(",") if attr == "aux" else [cx.attr(node, attr)]
            for name in names:
                name = name.strip()
                if name and name not in definitions[kind]:
                    errors.append(f"{_owner_label(doc, node, tag)}: {kind} references undefined {name!r}")
    return errors


def _merge_83_to_84(doc, template) -> None:
    # Existing definitions and bindings may be customized: fill gaps only.
    for section, tag, key in (
        ("aux_windows", "aw", "name"),
        ("stat_sets", "ss", "name"),
        ("layout_sets", "ls", "name"),
        ("popup_windows", "pu", "pu_name"),
        ("supported_games", "game", "game_name"),
        ("supported_sites", "site", "site_name"),
        ("hhcs", "hhc", "site"),
    ):
        sources = cx.find_all(template, section)
        if not sources:
            continue
        targets = cx.find_all(doc, section)
        if not targets:
            cx.append(doc, doc, cx.import_node(doc, sources[0]))
            continue
        target = targets[0]
        existing = {cx.attr(n, key) for n in cx.find_all(target, tag)}
        for node in cx.find_all(sources[0], tag):
            if cx.attr(node, key) not in existing:
                cx.append(doc, target, cx.import_node(doc, node))
    _repair_renamed_references(doc)


def _preserve_84_to_85(doc, template) -> None:
    """Advance to v85 without replacing a user's customized HUD positions.

    Version 85 ships corrected layout reference sizes and adds a runtime guard for
    impossible reference/position pairs. Existing layouts are user-editable, so
    copying the template's coordinates during migration would destroy personal
    HUD placement. The safe migration is therefore deliberately conservative:
    preserve the document and only apply the already-safe alias repair before the
    common reference validation stamps the new version.
    """
    del template
    _repair_renamed_references(doc)


def _preserve_85_to_86(doc, template) -> None:
    """Advance to v86 without changing user-defined HUD panel settings.

    Dynamic panel rules are opt-in and disabled in the shipped template, so an
    existing configuration must keep its document intact while acquiring the
    new schema version.
    """
    del doc, template


def _preserve_86_to_87(doc, template) -> None:
    """Advance to v87 without touching user settings (#680).

    v87 only adds optional database attributes (local_first/local_path) that
    default to off when absent, so an existing configuration keeps its document
    intact and simply gains the new schema version.
    """
    del doc, template


# Rooms each version adds: an upgrade gives them to a configuration lacking them.
SITES_ADDED_IN_88 = ("Bet365.fr Poker",)  # #717
SITES_ADDED_IN_90 = ("Unibet",)  # #729: the 2026 Relax Gaming client
SITES_ADDED_IN_91 = ("Betclic",)  # #730: the 2025+ in-house client, apart from the iPoker skin
SITES_ADDED_IN_94 = ("CoinPoker",)  # #732: text hand-history import, nothing live
SITES_ADDED_IN_95 = ("BetRivers",)  # #731: text hand-history import, nothing live


def _child_section(doc, section: str):
    found = cx.find_all(doc, section)
    return found[0] if found else None


def _add_sites(doc, template, names) -> None:
    """Give ``doc`` the template's <site> and <hhc> of each room in ``names`` it lacks.

    A room the configuration already declares keeps its entry as it is. The
    layout sets the new entry uses come along when the configuration lacks
    them, so the upgrade's reference check still passes.
    """
    for section, tag, key in (("supported_sites", "site", "site_name"), ("hhcs", "hhc", "site")):
        target = _child_section(doc, section)
        source = _child_section(template, section)
        if target is None or source is None:
            continue
        existing = {cx.attr(node, key) for node in cx.find_all(target, tag)}
        for node in cx.find_all(source, tag):
            if cx.attr(node, key) in names and cx.attr(node, key) not in existing:
                cx.append(doc, target, cx.import_node(doc, node))
                existing.add(cx.attr(node, key))
                _add_missing_layout_sets(doc, template, node)


def _add_missing_layout_sets(doc, template, site) -> None:
    target = _child_section(doc, "layout_sets")
    source = _child_section(template, "layout_sets")
    if target is None or source is None:
        return
    defined = {cx.attr(node, "name") for node in cx.find_all(target, "ls")}
    wanted = {cx.attr(node, "ls") for node in cx.find_all(site, "layout_set")} - defined
    for node in cx.find_all(source, "ls"):
        if cx.attr(node, "name") in wanted:
            cx.append(doc, target, cx.import_node(doc, node))


def _add_sites_87_to_88(doc, template) -> None:
    """Advance to v88, adding the bet365.fr room (#717) to a configuration lacking it.

    Everything else is kept as the user left it, their own entry for that room
    included.
    """
    _add_sites(doc, template, SITES_ADDED_IN_88)


def _add_summary_importers_88_to_89(doc, template) -> None:
    """Advance to v89, giving each room the summary importer the template declares (#725).

    A configuration written from the development HUD_config.xml declared the
    Unibet converter without "UnibetSummary", so its tournament summaries were
    never recognised. A room whose <hhc> names no summary importer gains the
    template's, when both name the same converter; one the user set is kept.
    """
    target = _child_section(doc, "hhcs")
    source = _child_section(template, "hhcs")
    if target is None or source is None:
        return
    declared = {
        (cx.attr(node, "site"), cx.attr(node, "converter")): cx.attr(node, "summaryImporter")
        for node in cx.find_all(source, "hhc")
        if cx.attr(node, "summaryImporter")
    }
    for node in cx.find_all(target, "hhc"):
        importer = declared.get((cx.attr(node, "site"), cx.attr(node, "converter")))
        if importer and not cx.attr(node, "summaryImporter"):
            cx.set_attr(node, "summaryImporter", importer)


def _add_sites_89_to_90(doc, template) -> None:
    """Advance to v90, adding the current Unibet room (#729) to a configuration lacking it.

    Configurations had its converter but no <site>, so it could be neither
    enabled nor given a hand-history folder. Its "Unibet_default" layout set
    comes along. A configuration that already declares the room keeps it.
    """
    _add_sites(doc, template, SITES_ADDED_IN_90)


def _add_sites_90_to_91(doc, template) -> None:
    """Advance to v91, adding the 2025+ Betclic room (#730) to a configuration lacking it.

    The room is new, so every configuration lacks it: the <site>, its <hhc>
    converter entry and the layout set it references all come from the
    template. A configuration that already declares the room keeps it.
    """
    _add_sites(doc, template, SITES_ADDED_IN_91)


def _preserve_91_to_92(doc, template) -> None:
    """Advance to v92 while retaining user settings.

    The shipped Ring Player Stats column defaults are appended by
    ``GUICashStats.add_missing_defaults`` when the configuration loads; no
    document rewrite is needed for this version.
    """
    del doc, template


def _zero_padding_92_to_93(doc, template) -> None:
    """Keep every HUD looking as it did when ``xpad`` / ``ypad`` start to count.

    Up to v92 the HUD parsed both attributes and drew nothing with them, so the
    values a configuration holds (``xpad="1"`` in every shipped profile) never
    reached the screen. From v93 they add to the grid's gaps (#770): an upgrade
    sets them to 0, the spacing those HUDs have always had.
    """
    del template
    for node in cx.find_all(doc, "ss"):
        for attr in ("xpad", "ypad"):
            if cx.has_attr(node, attr):
                cx.set_attr(node, attr, "0")


def _add_sites_93_to_94(doc, template) -> None:
    """Advance to v94, adding CoinPoker back as an import-only room (#732).

    Its entries were dropped when the room was switched off; its exported hand
    histories can now be bulk-imported. The room arrives disabled, with no HUD
    (``aux_enabled="False"``, which the code enforces anyway). A configuration
    that still declares the room keeps its entry.
    """
    _add_sites(doc, template, SITES_ADDED_IN_94)


def _add_sites_94_to_95(doc, template) -> None:
    """Advance to v95, adding BetRivers as an import-only room (#731).

    The room is new: its <site> (off, no HUD) and its <hhc> come from the
    template. A configuration that already declares it keeps it.
    """
    _add_sites(doc, template, SITES_ADDED_IN_95)


def _add_summary_importers_95_to_96(doc, template) -> None:
    """Advance to v96, giving GGPoker its tournament-summary importer (#868).

    GG summaries were never recognised: the room declared no summary importer.
    The v89 rule is applied again, so a room whose <hhc> names none gains the
    template's; one the user set is kept.
    """
    _add_summary_importers_88_to_89(doc, template)


def _repair_renamed_references(doc) -> None:
    aux_names = {cx.attr(n, "name") for n in cx.find_all(doc, "aw")}
    if "Classic_HUD" not in aux_names and "ClassicHud" in aux_names:
        for node in cx.find_all(doc, "game"):
            names = [name.strip() for name in cx.attr(node, "aux").split(",")]
            if "Classic_HUD" in names:
                cx.set_attr(node, "aux", ", ".join("ClassicHud" if name == "Classic_HUD" else name for name in names))
    layout_names = {cx.attr(n, "name") for n in cx.find_all(doc, "ls")}
    if "bodova_default" not in layout_names and "bovada_default" in layout_names:
        for node in cx.find_all(doc, "layout_set"):
            if cx.attr(node, "ls") == "bodova_default":
                cx.set_attr(node, "ls", "bovada_default")


MIGRATIONS = (
    (83, 84, _merge_83_to_84),
    (84, 85, _preserve_84_to_85),
    (85, 86, _preserve_85_to_86),
    (86, 87, _preserve_86_to_87),
    (87, 88, _add_sites_87_to_88),
    (88, 89, _add_summary_importers_88_to_89),
    (89, 90, _add_sites_89_to_90),
    (90, 91, _add_sites_90_to_91),
    (91, 92, _preserve_91_to_92),
    (92, 93, _zero_padding_92_to_93),
    (93, 94, _add_sites_93_to_94),
    (94, 95, _add_sites_94_to_95),
    (95, 96, _add_summary_importers_95_to_96),
)


def upgrade_document(doc, template, target_version: int):
    """Prepare on a copy; never stamp an unknown schema as current."""
    candidate = cx.clone_document(doc)
    general = cx.find_all(candidate, "general")
    if not general:
        raise ValueError("Configuration has no version; manual review is required.")
    version = int(cx.attr(general[0], "version"))
    template_general = cx.find_all(template, "general")
    if not template_general or int(cx.attr(template_general[0], "version")) != target_version:
        raise ValueError("The shipped configuration template has an incompatible version.")
    for old, new, migrate in MIGRATIONS:
        if version == old and new <= target_version:
            migrate(candidate, template)
            cx.set_attr(general[0], "version", str(new))
            version = new
    if version != target_version:
        raise ValueError(f"No configuration upgrade path from version {version} to {target_version}.")
    errors = reference_errors(candidate)
    if errors:
        raise ValueError("Configuration still contains unresolved references:\n" + "\n".join(errors))
    return candidate


def write_upgrade(path: str, doc) -> str:
    """Keep a unique byte-for-byte backup and atomically replace the config."""
    target = Path(path)
    backup_fd, backup = tempfile.mkstemp(prefix=target.name + ".pre-upgrade-", suffix=".xml", dir=target.parent)
    os.close(backup_fd)
    try:
        shutil.copy2(target, backup)
    except OSError:
        Path(backup).unlink(missing_ok=True)
        raise
    temp_fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as stream:
            stream.write(cx.to_xml(doc))
            stream.flush()
            os.fsync(stream.fileno())
        cx.parse_file(temporary, backend=cx.backend_of(doc))
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return backup
