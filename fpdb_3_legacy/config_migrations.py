"""Versioned, conservative HUD configuration upgrades and reference diagnostics."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import defusedxml.minidom


def reference_errors(doc) -> list[str]:
    """Report every unresolved HUD binding, including its owning game/site."""
    definitions = {
        kind: {n.getAttribute("name") for n in doc.getElementsByTagName(tag)}
        for kind, tag in (("aux", "aw"), ("stat_set", "ss"), ("layout_set", "ls"))
    }
    errors = []
    for node in doc.getElementsByTagName("*"):
        bindings = [(attr, attr) for attr in ("aux", "stat_set", "layout_set")]
        if node.tagName == "layout_set":
            bindings.append(("ls", "layout_set"))
        if node.tagName == "hud_profile_rule":
            bindings.append(("profile", "stat_set"))
        for attr, kind in bindings:
            if not node.hasAttribute(attr):
                continue
            names = node.getAttribute(attr).split(",") if attr == "aux" else [node.getAttribute(attr)]
            for name in names:
                name = name.strip()
                if name and name not in definitions[kind]:
                    owner = node
                    keys = ("game_name", "site_name", "name")
                    while not any(owner.hasAttribute(a) for a in keys):
                        if owner.parentNode.nodeType != owner.ELEMENT_NODE:
                            break
                        owner = owner.parentNode
                    label = next((owner.getAttribute(a) for a in keys if owner.hasAttribute(a)), node.tagName)
                    errors.append(f"{label}: {kind} references undefined {name!r}")
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
        sources = template.getElementsByTagName(section)
        if not sources:
            continue
        targets = doc.getElementsByTagName(section)
        if not targets:
            doc.documentElement.appendChild(doc.importNode(sources[0], True))
            continue
        target = targets[0]
        existing = {n.getAttribute(key) for n in target.getElementsByTagName(tag)}
        for node in sources[0].getElementsByTagName(tag):
            if node.getAttribute(key) not in existing:
                target.appendChild(doc.importNode(node, True))
    _repair_renamed_references(doc)


def _repair_renamed_references(doc) -> None:
    aux_names = {n.getAttribute("name") for n in doc.getElementsByTagName("aw")}
    if "Classic_HUD" not in aux_names and "ClassicHud" in aux_names:
        for node in doc.getElementsByTagName("game"):
            names = [name.strip() for name in node.getAttribute("aux").split(",")]
            if "Classic_HUD" in names:
                node.setAttribute("aux", ", ".join("ClassicHud" if name == "Classic_HUD" else name for name in names))
    layout_names = {n.getAttribute("name") for n in doc.getElementsByTagName("ls")}
    if "bodova_default" not in layout_names and "bovada_default" in layout_names:
        for node in doc.getElementsByTagName("layout_set"):
            if node.getAttribute("ls") == "bodova_default":
                node.setAttribute("ls", "bovada_default")


MIGRATIONS = ((83, 84, _merge_83_to_84),)


def upgrade_document(doc, template, target_version: int):
    """Prepare on a copy; never stamp an unknown schema as current."""
    candidate = doc.cloneNode(True)
    general = candidate.getElementsByTagName("general")
    if not general:
        raise ValueError("Configuration has no version; manual review is required.")
    version = int(general[0].getAttribute("version"))
    template_general = template.getElementsByTagName("general")
    if not template_general or int(template_general[0].getAttribute("version")) != target_version:
        raise ValueError("The shipped configuration template has an incompatible version.")
    for old, new, migrate in MIGRATIONS:
        if version == old and new <= target_version:
            migrate(candidate, template)
            general[0].setAttribute("version", str(new))
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
            stream.write(doc.toxml())
            stream.flush()
            os.fsync(stream.fileno())
        defusedxml.minidom.parse(temporary)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return backup
