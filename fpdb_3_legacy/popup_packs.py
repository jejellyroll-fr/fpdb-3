"""Declarative popup packs: hierarchical HUD popups as data (#299).

The HUD's popups are already data -- ``<pu pu_name="...">`` elements in
``HUD_config.xml``, each a class name and a list of stat names, with
``pu_stat_submenu`` nesting one popup inside another. What the analytics epic
asks for is a *pack* of them: a whole preflop/SRP/3-bet-pot/river hierarchy,
versioned, validated, shipped, and editable without touching Python.

This module defines that layer. A :class:`PopupPack` is one JSON document
(``popup_packs.d/*.json``) holding named :class:`PopupNode` popups, each a list
of :class:`PopupEntry` rows. Loading validates before anything is installed:

* every stat name must exist -- in the native catalogue (``Stats.STATLIST``) or
  in the declarative descriptor registry (``stat_registry``);
* every ``submenu`` must resolve to another node of the pack, to a popup the
  configuration already has, or to a node of another pack being installed;
* a node's submenu graph must be acyclic (the HUD opens submenus recursively);
* fields, classes and params are looked up in registries, so a typo is a
  ``ValueError`` naming the field and listing what is allowed, and no ``.json``
  can smuggle in Python, SQL or a widget tree.

Compiled, a node becomes exactly the :class:`fpdb_3_legacy.Configuration.Popup`
the HUD already reads -- built from a generated ``<pu>`` node, so there is one
popup type in the system and the HUD code is untouched. Installing is additive:
existing popups are never modified unless the caller asks, and every pack
re-installs idempotently over its own nodes.

**Sample sizes.** The modern popup already renders a stat's sample in its own
column (field 4 of the six-tuple from ``Stats.do_stat``). A node may therefore
declare ``"require_sample": true``, and the loader refuses a pack whose entries
cannot show one: a frequency without its denominator is the thing #307's
cohorts exist to prevent, and a popup is where a user reads it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Final, NoReturn

# The pack file schema this module understands. A file written for a newer
# schema is refused rather than half-read.
POPUP_PACK_SCHEMA_VERSION: Final = 1

# The popup class a node uses unless it says otherwise. ModernSubmenu is the
# framework the HUD preferences install and the one that renders samples.
DEFAULT_PU_CLASS: Final = "ModernSubmenu"

# The popup classes a pack may name: every class ``Popup.resolve_popup_class``
# can find, kept as data so an unknown class is refused at load time rather than
# falling back to the "default" popup at right-click time, and so loading a pack
# does not have to import Qt. A test asserts this matches the modules two-way,
# so the list cannot drift from what the HUD actually resolves.
POPUP_CLASSES: Final[tuple[str, ...]] = (
    "default",
    "Multicol",
    "Submenu",
    "ModernSubmenu",
    "ModernSubmenuLight",
    "ModernSubmenuClassic",
    "CategorizedPopup",
    "RangeChartPopup",
    "BlockPopup",
)

# ``<pu>`` attributes Configuration.Popup reads into ``pu_class_params``. A
# pack's ``params`` is checked against these, so a param cannot be invented.
PARAM_ATTRIBUTES: Final[dict[str, str]] = {
    "source": "pu_source",
    "group": "pu_group",
    "theme": "pu_theme",
    "icon_provider": "pu_icon_provider",
    "title": "pu_title",
    "width": "pu_width",
    "max_height": "pu_max_height",
}

# A node's optional fields; anything else in the document is refused.
_NODE_FIELDS: Final = frozenset(
    {"name", "class", "title", "params", "require_sample", "entries", "description"},
)
_ENTRY_FIELDS: Final = frozenset({"stat", "label", "submenu", "category", "color"})
_PACK_FIELDS: Final = frozenset(
    {"name", "label", "description", "tags", "root", "nodes", "source"},
)


def _fail(message: str, source: str = "") -> NoReturn:
    raise ValueError(f"{message} [{source}]" if source else message)


# ---------------------------------------------------------------------------
# The stat vocabulary.
# ---------------------------------------------------------------------------


def native_stats() -> frozenset[str]:
    """The native stat names the HUD knows (``Stats.STATLIST``), imported lazily."""
    from fpdb_3_legacy import Stats  # noqa: PLC0415 - keeps this module import-light

    return frozenset(Stats.STATLIST)


def descriptor_stats() -> frozenset[str]:
    """The declarative descriptor names, from the shared registry."""
    from fpdb_3_legacy.stat_registry import get_registry  # noqa: PLC0415

    return frozenset(get_registry().names())


def known_stats() -> frozenset[str]:
    """Every stat name a pack may use: native catalogue plus descriptors."""
    return native_stats() | descriptor_stats()


def sample_for(stat: str) -> str:
    """What a stat shows in a popup's sample column, or ``""`` when it shows none.

    A descriptor declares its own with a ``sample`` expression, and the
    expression is what is reported -- the number only exists per player, at the
    table. A native stat follows the catalogue convention of carrying
    ``"(done/chances)"`` in the fifth element of its tuple, so the probe goes
    through ``do_stat`` -- the same call the popup makes -- and reports the
    shape of the sample column rather than a parallel guess at it.
    """
    from fpdb_3_legacy import Stats  # noqa: PLC0415 - keeps this module import-light

    if stat not in Stats.STATLIST:
        from fpdb_3_legacy.stat_registry import get_registry  # noqa: PLC0415

        descriptor = get_registry().get(stat)
        if descriptor is None or descriptor.sample_expression is None:
            return ""
        return f"({descriptor.sample})"
    try:
        result = Stats.do_stat({}, -1, stat)
    except Exception:  # noqa: BLE001 - a probe must never break a pack load
        return ""
    if not isinstance(result, tuple) or len(result) < 5:
        return ""
    sample = result[4]
    return str(sample) if sample else ""


def has_sample(stat: str) -> bool:
    """Whether a stat can show a sample at all -- what a pack's promise checks."""
    return bool(sample_for(stat))


# ---------------------------------------------------------------------------
# Entries, nodes, packs.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PopupEntry:
    """One row of a popup: a stat, optionally labelled and optionally a submenu."""

    stat: str
    label: str = ""
    submenu: str = ""
    category: str = ""
    color: str = ""

    @property
    def display_text(self) -> str:
        """What the row reads in the popup.

        For a navigation row the classic XML puts the text in ``pu_stat_name``
        (which is ``stat`` here), and ModernStatRow falls back to it because
        there is no stat data to name the row; ``label`` still wins when set,
        which is how a pack localizes a row.
        """
        return self.label or self.stat

    def as_dict(self) -> dict[str, str]:
        out = {"stat": self.stat}
        for key in ("label", "submenu", "category", "color"):
            value = getattr(self, key)
            if value:
                out[key] = value
        return out


@dataclass(frozen=True)
class PopupNode:
    """One popup in a pack: a class, a list of rows and optional params."""

    name: str
    entries: tuple[PopupEntry, ...] = ()
    pu_class: str = DEFAULT_PU_CLASS
    title: str = ""
    description: str = ""
    require_sample: bool = False
    params: Mapping[str, str] = field(default_factory=dict)

    def stats(self) -> tuple[str, ...]:
        return tuple(entry.stat for entry in self.entries if not entry.submenu)

    def submenus(self) -> tuple[str, ...]:
        return tuple(entry.submenu for entry in self.entries if entry.submenu)

    def to_config_popup(self) -> Any:
        """Compile to the ``Configuration.Popup`` the HUD reads.

        Built from a generated ``<pu>`` node and parsed by the configuration's
        own class, so a pack-defined popup is byte-identical in shape to one
        from ``HUD_config.xml``: there is no second popup type to keep in step.
        """
        from defusedxml.minidom import parseString  # noqa: PLC0415 - keeps pack loading import-light

        from fpdb_3_legacy.Configuration import Popup as ConfigPopup  # noqa: PLC0415 - avoids a cycle

        return ConfigPopup(parseString(self.to_xml()).documentElement)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "class": self.pu_class}
        if self.title:
            out["title"] = self.title
        if self.description:
            out["description"] = self.description
        if self.require_sample:
            out["require_sample"] = True
        if self.params:
            out["params"] = dict(self.params)
        out["entries"] = [entry.as_dict() for entry in self.entries]
        return out

    def to_xml(self) -> str:
        """The ``<pu>`` element a user could paste into ``HUD_config.xml``."""
        attributes = [f' pu_name="{escape(self.name, quote=True)}"', f' pu_class="{escape(self.pu_class, quote=True)}"']
        if self.title:
            attributes.append(f' pu_title="{escape(self.title, quote=True)}"')
        attributes.extend(
            f' {PARAM_ATTRIBUTES[key]}="{escape(str(value), quote=True)}"' for key, value in self.params.items()
        )
        if not self.entries:
            return f"<pu{''.join(attributes)} />"

        lines = [f"<pu{''.join(attributes)}>"]
        for entry in self.entries:
            entry_attributes = [f' pu_stat_name="{escape(entry.stat, quote=True)}"']
            if entry.label:
                entry_attributes.append(f' pu_stat_label="{escape(entry.label, quote=True)}"')
            if entry.submenu:
                entry_attributes.append(f' pu_stat_submenu="{escape(entry.submenu, quote=True)}"')
            if entry.category:
                entry_attributes.append(f' pu_stat_category="{escape(entry.category, quote=True)}"')
            if entry.color:
                entry_attributes.append(f' pu_stat_color="{escape(entry.color, quote=True)}"')
            lines.append(f"    <pu_stat{''.join(entry_attributes)} />")
        lines.append("</pu>")
        return "\n".join(lines)


@dataclass(frozen=True)
class PopupPack:
    """A named set of popups, with one root the HUD's stat blocks can point at."""

    name: str
    nodes: Mapping[str, PopupNode]
    root: str
    label: Mapping[str, str] | str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    source: str = ""

    def label_text(self, locale: str = "en") -> str:
        """The pack's label in one locale, falling back to its English form."""
        if isinstance(self.label, Mapping):
            return str(self.label.get(locale) or self.label.get("en") or self.name)
        return self.label or self.name

    def node(self, name: str) -> PopupNode:
        if name not in self.nodes:
            _fail(f"Pack {self.name!r}: unknown popup {name!r}; known: {sorted(self.nodes)}")
        return self.nodes[name]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.nodes))

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "root": self.root}
        for key in ("label", "description"):
            value = getattr(self, key)
            if not value:
                continue
            out[key] = dict(value) if isinstance(value, Mapping) else value
        if self.tags:
            out["tags"] = list(self.tags)
        if self.source:
            out["source"] = self.source
        out["nodes"] = [self.nodes[name].as_dict() for name in self.names()]
        return out


# ---------------------------------------------------------------------------
# Validation: parse a document into a pack, refusing anything unknown.
# ---------------------------------------------------------------------------


def _unknown(data: Mapping[str, Any], allowed: frozenset[str], where: str, source: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        _fail(f"{where}: unknown field(s) {extra}; allowed: {sorted(allowed)}", source)


def _as_params(raw: Any, where: str, source: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        _fail(f"{where}: params must be an object", source)
    unknown = sorted(set(raw) - set(PARAM_ATTRIBUTES))
    if unknown:
        _fail(f"{where}: unknown param(s) {unknown}; allowed: {sorted(PARAM_ATTRIBUTES)}", source)
    return {str(key): str(value) for key, value in raw.items()}


def _as_entries(raw: Any, where: str, source: str) -> tuple[PopupEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        _fail(f"{where}: entries must be a list", source)
    entries: list[PopupEntry] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            entries.append(PopupEntry(stat=item))
            continue
        if not isinstance(item, Mapping):
            _fail(f"{where}: entry {index} must be a stat name or an object", source)
        _unknown(item, _ENTRY_FIELDS, f"{where}: entry {index}", source)
        stat = item.get("stat")
        if not isinstance(stat, str) or not stat:
            _fail(f"{where}: entry {index} needs a stat name", source)
        entries.append(
            PopupEntry(
                stat=stat,
                label=str(item.get("label", "")),
                submenu=str(item.get("submenu", "")),
                category=str(item.get("category", "")),
                color=str(item.get("color", "")),
            ),
        )
    return tuple(entries)


def _parse_node(data: Mapping[str, Any], source: str) -> PopupNode:
    if isinstance(data, str):
        data = {"name": data}
    if not isinstance(data, Mapping):
        _fail(f"A popup must be an object or a name, got {type(data).__name__}", source)
    _unknown(data, _NODE_FIELDS, "popup", source)
    name = data.get("name")
    if not isinstance(name, str) or not name:
        _fail("A popup needs a name", source)
    pu_class = str(data.get("class", DEFAULT_PU_CLASS))
    if pu_class not in POPUP_CLASSES:
        _fail(f"Popup {name!r}: unknown class {pu_class!r}; known: {list(POPUP_CLASSES)}", source)
    require_sample = bool(data.get("require_sample", False))
    entries = _as_entries(data.get("entries"), f"Popup {name!r}", source)
    if not entries:
        _fail(f"Popup {name!r}: needs at least one entry", source)
    if require_sample:
        _require_samples(name, entries, source)
    return PopupNode(
        name=name,
        entries=entries,
        pu_class=pu_class,
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        require_sample=require_sample,
        params=_as_params(data.get("params"), f"Popup {name!r}", source),
    )


def _require_samples(name: str, entries: Sequence[PopupEntry], source: str) -> None:
    """Refuse a node that promises a sample and cannot deliver one."""
    missing = [entry.stat for entry in entries if not entry.submenu and not has_sample(entry.stat)]
    if missing:
        _fail(
            f"Popup {name!r} requires a sample, but {missing} have no sample to show "
            f"(a descriptor needs a 'sample' expression)",
            source,
        )


def _nodes_from(raw: Any, source: str) -> dict[str, PopupNode]:
    """The ``nodes`` section, as a name -> node mapping, refusing duplicates."""
    nodes: dict[str, PopupNode] = {}
    if isinstance(raw, Mapping):
        items: Iterable[Any] = [{"name": name, **(body if isinstance(body, Mapping) else {})} for name, body in raw.items()]
    elif isinstance(raw, list):
        items = raw
    else:
        _fail("'nodes' must be a list of popups or an object keyed by name", source)
    for item in items:
        node = _parse_node(item, source)
        if node.name in nodes:
            _fail(f"Duplicate popup {node.name!r} in one pack", source)
        nodes[node.name] = node
    if not nodes:
        _fail("A pack needs at least one popup", source)
    return nodes


def _check_submenus(nodes: Mapping[str, PopupNode], root: str, known: frozenset[str], source: str) -> None:
    """Every submenu resolves, and the graph the root reaches is acyclic."""
    for node in nodes.values():
        for submenu in node.submenus():
            if submenu not in nodes and submenu not in known:
                _fail(
                    f"Popup {node.name!r}: submenu {submenu!r} is neither a popup of this pack "
                    f"({sorted(nodes)}) nor one the configuration defines",
                    source,
                )
    # Depth-first over the pack's own nodes: the HUD opens submenus by the same
    # edges, so a cycle is an unbounded chain of windows, not a late error.
    visiting: set[str] = set()
    done: set[str] = set()

    def walk(name: str, path: tuple[str, ...]) -> None:
        if name in done or name not in nodes:
            return
        if name in visiting:
            _fail(f"Submenu cycle: {' -> '.join([*path, name])}", source)
        visiting.add(name)
        for submenu in nodes[name].submenus():
            walk(submenu, (*path, name))
        visiting.discard(name)
        done.add(name)

    for name in nodes:
        walk(name, ())


def parse_pack(data: Mapping[str, Any], source: str = "", known_popups: Iterable[str] = ()) -> PopupPack:
    """One pack document to a :class:`PopupPack`, validated."""
    if not isinstance(data, Mapping):
        _fail(f"A pack must be an object, got {type(data).__name__}", source)
    _unknown(data, _PACK_FIELDS, "pack", source)
    name = data.get("name")
    if not isinstance(name, str) or not name:
        _fail("A pack needs a name", source)
    nodes = _nodes_from(data.get("nodes"), source)
    root = str(data.get("root", ""))
    if not root:
        _fail(f"Pack {name!r}: needs a root popup", source)
    if root not in nodes:
        _fail(f"Pack {name!r}: root {root!r} is not one of its popups {sorted(nodes)}", source)
    _check_submenus(nodes, root, frozenset(known_popups), source)
    tags = data.get("tags", ())
    if not isinstance(tags, (list, tuple)) or not all(isinstance(tag, str) for tag in tags):
        _fail(f"Pack {name!r}: tags must be a list of strings", source)
    label = data.get("label", "")
    if not isinstance(label, (str, Mapping)):
        _fail(f"Pack {name!r}: label must be text or a locale mapping", source)
    return PopupPack(
        name=name,
        nodes=nodes,
        root=root,
        label=label,
        description=str(data.get("description", "")),
        tags=tuple(tags),
        source=str(data.get("source", source)),
    )


def validate_pack(pack: PopupPack) -> tuple[str, ...]:
    """The non-fatal findings about a pack: entries that will show no sample.

    Unknown *stats* are fatal and already refused by :func:`load_packs`, because
    a popup naming a stat nobody implements renders as ``xxx`` at the table.
    A missing *sample* is not: the value is still worth showing, and the issue
    asks only that the sample be there where it exists. Reporting it is how a
    pack author notices a rate quietly presented without its denominator.
    """
    warnings: list[str] = []
    for name in sorted(pack.nodes):
        node = pack.nodes[name]
        missing = [entry.stat for entry in node.entries if not entry.submenu and not has_sample(entry.stat)]
        if missing:
            warnings.append(f"{name}: no sample for {', '.join(missing)}")
    return tuple(warnings)


def _check_stats_known(pack: PopupPack) -> None:
    known = known_stats()
    for node in pack.nodes.values():
        for entry in node.entries:
            if not entry.submenu and entry.stat not in known:
                _fail(
                    f"Popup {node.name!r}: unknown stat {entry.stat!r}; "
                    f"it is neither in the native catalogue nor a descriptor",
                    pack.source,
                )


# ---------------------------------------------------------------------------
# Loading and saving.
# ---------------------------------------------------------------------------


def _documents(document: Any, path: Path) -> list[Mapping[str, Any]]:
    if isinstance(document, Mapping) and "packs" in document:
        raw = document["packs"]
        if not isinstance(raw, list):
            _fail(f"{path}: 'packs' must be a list", str(path))
        return list(raw)
    if isinstance(document, list):
        return list(document)
    if isinstance(document, Mapping):
        return [document]
    _fail(f"{path}: expected a pack object or a list of packs", str(path))


def _check_version(document: Any, path: Path) -> None:
    if not isinstance(document, Mapping):
        return
    version = document.get("schema_version", POPUP_PACK_SCHEMA_VERSION)
    if not isinstance(version, int) or isinstance(version, bool):
        _fail(f"{path}: schema_version must be an integer", str(path))
    if version > POPUP_PACK_SCHEMA_VERSION:
        _fail(
            f"{path}: popup pack schema {version} is newer than {POPUP_PACK_SCHEMA_VERSION}; "
            "upgrade fpdb-3 rather than reading it half-way",
            str(path),
        )


def load_packs(path: str | Path, known_popups: Iterable[str] = ()) -> list[PopupPack]:
    """Every pack in one ``.json`` file, validated."""
    source = Path(path)
    document = json.loads(source.read_text(encoding="utf-8"))
    _check_version(document, source)
    packs = [parse_pack(entry, str(source), known_popups) for entry in _documents(document, source)]
    for pack in packs:
        _check_stats_known(pack)
    return packs


def _raw_node_names(entry: Mapping[str, Any]) -> set[str]:
    """The popup names a raw pack document declares, without validating it."""
    raw = entry.get("nodes") if isinstance(entry, Mapping) else None
    names: set[str] = set()
    if isinstance(raw, Mapping):
        names.update(str(name) for name in raw)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, Mapping) and isinstance(item.get("name"), str):
                names.add(item["name"])
    return names


def _directory_node_names(root: Path) -> frozenset[str]:
    """Every popup name the files of one directory declare, across files.

    A pack may link to another pack's popup (the shipped ``analytics`` root
    does), so the links can only be checked once the whole directory is known.
    """
    names: set[str] = set()
    for path in sorted(root.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in _documents(document, path):
            names.update(_raw_node_names(entry))
    return frozenset(names)


def load_directory(directory: str | Path, known_popups: Iterable[str] = ()) -> list[PopupPack]:
    """Every pack in every ``.json`` file of a directory, name-sorted.

    ``known_popups`` gains every popup the directory itself declares, so a pack
    may nest inside a sibling file's popup.
    """
    root = Path(directory)
    if not root.is_dir():
        return []
    known = frozenset(known_popups) | _directory_node_names(root)
    packs: list[PopupPack] = []
    for path in sorted(root.glob("*.json")):
        packs.extend(load_packs(path, known))
    return packs


@dataclass
class PackRegistry:
    """Packs by name, from the packaged directory plus any extra ones."""

    packs: dict[str, PopupPack] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)

    def add(self, pack: PopupPack, source: str = "") -> None:
        self.packs[pack.name] = pack
        if source:
            self.sources[pack.name] = source

    def names(self) -> list[str]:
        return sorted(self.packs)

    def get(self, name: str) -> PopupPack:
        if name not in self.packs:
            _fail(f"Unknown popup pack {name!r}; known: {self.names()}")
        return self.packs[name]

    def all_nodes(self) -> list[PopupNode]:
        return [node for name in self.names() for node in self.packs[name].nodes.values()]

    def validate(self) -> tuple[str, ...]:
        """Warnings for every pack in the registry."""
        return tuple(warning for name in self.names() for warning in validate_pack(self.packs[name]))

    def save(self, pack: PopupPack, path: str | Path) -> Path:
        """Write one pack as a validated document (save-then-load round trips)."""
        known = frozenset(node.name for node in self.all_nodes())
        validated = parse_pack(pack.as_dict(), str(path), known)
        _check_stats_known(validated)
        target = Path(path)
        document = {"schema_version": POPUP_PACK_SCHEMA_VERSION, "packs": [validated.as_dict()]}
        target.write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")
        return target


def default_packs_dir() -> Path:
    """The packaged popup pack library."""
    return Path(__file__).resolve().parent / "popup_packs.d"


def load_default_registry(extra_dirs: Iterable[str | Path] = ()) -> PackRegistry:
    """The bundled packs plus every ``.json`` in ``extra_dirs``."""
    registry = PackRegistry()
    for pack in load_directory(default_packs_dir()):
        registry.add(pack, "builtin")
    known = frozenset(node.name for node in registry.all_nodes())
    for directory in extra_dirs:
        for pack in load_directory(directory, known):
            registry.add(pack, str(directory))
    return registry


_registry: PackRegistry | None = None


def get_registry() -> PackRegistry:
    """The process-wide registry, built once from the packaged packs."""
    global _registry
    if _registry is None:
        _registry = load_default_registry()
    return _registry


# ---------------------------------------------------------------------------
# Installing into a configuration.
# ---------------------------------------------------------------------------


@dataclass
class InstallReport:
    """What an install did: the popups added, the ones it refused, the warnings."""

    installed: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    roots: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"installed {len(self.installed)} popup(s), replaced {len(self.replaced)}, skipped {len(self.skipped)}"]
        for pack, root in sorted(self.roots.items()):
            lines.append(f"  {pack} -> {root}")
        lines.extend(f"  warning: {warning}" for warning in self.warnings)
        return "\n".join(lines)


def _owned_by_pack(config: Any, name: str) -> str:
    """The pack that installed a popup, from the registry it was recorded in."""
    return getattr(config, "pack_popups", {}).get(name, "")


def install_packs(
    config: Any,
    packs: Sequence[PopupPack],
    *,
    overwrite: bool = False,
    known_popups: Iterable[str] = (),
) -> InstallReport:
    """Add the packs' popups to ``config.popup_windows``, additively.

    A name already taken by a popup the user (or ``HUD_config.xml``) defines is
    left alone unless ``overwrite`` -- a pack must never silently replace a
    popup someone configured. A name the *same* pack installed earlier is
    replaced, so installing twice is idempotent rather than an error.
    """
    report = InstallReport()
    existing = set(getattr(config, "popup_windows", {})) | set(known_popups)
    incoming = frozenset(node.name for pack in packs for node in pack.nodes.values())
    config.pack_popups = dict(getattr(config, "pack_popups", {}))
    for pack in packs:
        # A submenu may point at another pack being installed in the same call,
        # so the link check sees the union, not just this pack's own nodes.
        _check_submenus(pack.nodes, pack.root, frozenset(str(name) for name in existing | incoming), pack.source)
        _check_stats_known(pack)
        for name in sorted(pack.nodes):
            owner = _owned_by_pack(config, name)
            if name in existing and not (overwrite or owner == pack.name):
                report.skipped.append(name)
                continue
            config.popup_windows[name] = pack.nodes[name].to_config_popup()
            config.pack_popups[name] = pack.name
            if owner == pack.name or name in existing:
                report.replaced.append(name)
            else:
                report.installed.append(name)
        report.roots[pack.name] = pack.root
        report.warnings.extend(f"{pack.name}: {warning}" for warning in validate_pack(pack))
    return report


def link_pack(config: Any, popup_name: str, pack: PopupPack, label: str = "Analytics", submenu_key: str = "") -> None:
    """Add a submenu row pointing at a pack's root inside an existing popup.

    This is how a pack reaches a *profile*: the profile's stat block popup gains
    one row that opens the pack, instead of the user re-authoring the hierarchy.
    Idempotent -- an existing row with the same submenu is not duplicated -- and
    it refuses to touch a popup that does not exist rather than creating one.
    """
    popups = getattr(config, "popup_windows", {})
    if popup_name not in popups:
        _fail(f"Cannot link into {popup_name!r}: no such popup")
    if pack.root not in getattr(config, "popup_windows", {}):
        _fail(f"Pack {pack.name!r} is not installed; install it before linking it in")
    popup = popups[popup_name]
    stats = getattr(popup, "pu_stats", [])
    submenus = getattr(popup, "pu_stats_submenu", [])
    if pack.root in [entry[1] for entry in submenus]:
        return
    stats.append(submenu_key or label)
    getattr(popup, "pu_stats_category", []).append("")
    getattr(popup, "pu_stats_label", []).append(label)
    getattr(popup, "pu_stats_color", []).append("")
    submenus.append((submenu_key or label, pack.root))


def format_node(node: PopupNode, with_samples: bool = True) -> str:
    """A readable rendering of one popup: its rows, submenus and samples."""
    known = known_stats()
    lines = [f"{node.name} ({node.pu_class})"]
    for entry in node.entries:
        if entry.submenu:
            lines.append(f"   > {entry.display_text} -> {entry.submenu}")
            continue
        shown = f" [{sample_for(entry.stat) or '-'}]" if with_samples else ""
        unknown = "" if entry.stat in known else "  [unknown stat]"
        lines.append(f"   {entry.display_text}: {entry.stat}{shown}{unknown}")
    return "\n".join(lines)


def format_pack(pack: PopupPack, with_samples: bool = True) -> str:
    """A readable rendering of a pack: its tree, with stats and samples."""
    lines = [
        f"{pack.name}: {pack.description or '(no description)'}",
        f"  root: {pack.root}",
    ]
    for name in pack.names():
        node = pack.nodes[name]
        marker = "*" if name == pack.root else " "
        rendered = format_node(node, with_samples=with_samples).splitlines()
        lines.append(f" {marker} {rendered[0]}")
        lines.extend(rendered[1:])
    return "\n".join(lines)


__all__ = [
    "DEFAULT_PU_CLASS",
    "PARAM_ATTRIBUTES",
    "POPUP_CLASSES",
    "POPUP_PACK_SCHEMA_VERSION",
    "InstallReport",
    "PackRegistry",
    "PopupEntry",
    "PopupNode",
    "PopupPack",
    "default_packs_dir",
    "descriptor_stats",
    "format_node",
    "format_pack",
    "get_registry",
    "has_sample",
    "install_packs",
    "known_stats",
    "link_pack",
    "load_default_registry",
    "load_directory",
    "load_packs",
    "native_stats",
    "parse_pack",
    "sample_for",
    "validate_pack",
]
