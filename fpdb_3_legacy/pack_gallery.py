"""The pack gallery's index: shared HUD packages and stat packs, checked before they install (#449).

fpdb's shareable content is already data: ``.fpdbhud`` HUD packages and
``.fpdbstats`` stat packs. The gallery is how players find each other's: a
public repository holds the packages and an ``index.json`` that lists them::

    {
      "schema": "fpdb-3/pack-index",
      "version": 1,
      "packs": [
        {
          "id": "fpdb-3.nlhe_6max_basic",
          "kind": "hud",
          "name": "FPDB Basic",
          "version": "1.0.0",
          "min_fpdb_version": "3.9",
          "author": "fpdb-3",
          "license": "AGPL-3.0-or-later",
          "description": "The starter HUD for No Limit Hold'em 6-max.",
          "file": "hud/nlhe_6max_basic.fpdbhud",
          "sha256": "…",
          "size": 5212,
          "screenshot": "screens/nlhe_6max_basic.png"
        }
      ]
    }

This module reads that index and the packages it points at, and decides what
may install. Nothing here installs or draws anything; the app's *Get packs*
dialog and the packs repository's CI both stand on it, so a package the CI
accepts is one the app accepts:

* an index entry that is malformed, or names a kind this fpdb does not know,
  is set aside with its reason; the rest of the index stays usable;
* a package is the bytes the index promised (size and SHA-256) and passes the
  same validators a manual import uses: :func:`stat_packs.read_pack` for a
  stat pack, :func:`hud_package.package_problems` for a HUD package, so one
  naming a stat or popup that does not exist is refused with the names;
* a package is data only: nothing is imported or run, and a stat pack can only
  name what the stat engine registers;
* a fetched package is kept in a cache, and the index too, so the gallery
  lists and installs what it already has when the network is down.

``python -m fpdb_3_legacy.pack_gallery validate <repository>`` is the check
the packs repository's CI runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

import defusedxml.minidom

from fpdb_3_legacy import stat_packs
from fpdb_3_legacy.hud_package import package_problems

INDEX_SCHEMA: Final = "fpdb-3/pack-index"
INDEX_VERSION: Final = 1
INDEX_NAME: Final = "index.json"
#: Each kind of package the gallery carries, and the file suffix it must have.
KINDS: Final = {"hud": ".fpdbhud", "stats": stat_packs.PACK_SUFFIX}
#: A package is read whole before it is judged; a stat pack archive has its own, equal, limit.
MAX_PACKAGE_BYTES: Final = stat_packs.MAX_ARCHIVE_BYTES
MAX_INDEX_BYTES: Final = 2 * 1024 * 1024
_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_FIELDS: Final = frozenset(
    {
        "id",
        "kind",
        "name",
        "version",
        "min_fpdb_version",
        "author",
        "license",
        "description",
        "file",
        "sha256",
        "size",
        "screenshot",
        "stats",
    }
)
_REQUIRED: Final = ("id", "kind", "name", "version", "author", "license", "file", "sha256", "size")

#: Reads *location* (an https URL or a local path), at most *limit* bytes; raises OSError.
Reader = Callable[[str, int], bytes]


class GalleryError(ValueError):
    """An index or a package that cannot be used, with every reason found."""

    def __init__(self, messages: Iterable[str], source: str = "") -> None:
        self.messages = list(messages) or ["invalid"]
        self.source = source
        super().__init__((f"{source}: " if source else "") + "; ".join(self.messages))


@dataclass(frozen=True)
class GalleryEntry:
    """One package the index lists, as checked."""

    id: str
    kind: str
    name: str
    version: str
    author: str
    license: str
    file: str
    sha256: str
    size: int
    min_fpdb_version: str = ""
    description: str = ""
    screenshot: str = ""
    stats: tuple[str, ...] = ()

    @property
    def filename(self) -> str:
        return PurePosixPath(self.file).name


@dataclass(frozen=True)
class PackIndex:
    """The gallery's index: the usable entries, and the ones set aside with why."""

    entries: tuple[GalleryEntry, ...]
    rejected: tuple[tuple[str, str], ...] = ()  # (entry id or position, reason)
    stale: bool = False  # read from the cache because the gallery could not be reached

    def get(self, pack_id: str) -> GalleryEntry | None:
        return next((entry for entry in self.entries if entry.id == pack_id), None)


# ---------------------------------------------------------------------------
# The index.
# ---------------------------------------------------------------------------


def parse_index(text: str | bytes) -> PackIndex:
    """Read an index; a bad entry is set aside, a bad document raises :class:`GalleryError`."""
    try:
        document = json.loads(text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise GalleryError([f"not JSON: {exc}"], INDEX_NAME) from None
    problems = _document_problems(document)
    if problems:
        raise GalleryError(problems, INDEX_NAME)

    entries: list[GalleryEntry] = []
    rejected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for position, raw in enumerate(document["packs"], 1):
        label = str(raw["id"]) if isinstance(raw, dict) and isinstance(raw.get("id"), str) else f"#{position}"
        try:
            entry = _entry(raw)
        except GalleryError as exc:
            rejected.append((label, "; ".join(exc.messages)))
            continue
        if entry.id in seen:
            rejected.append((label, "listed twice"))
            continue
        seen.add(entry.id)
        entries.append(entry)
    return PackIndex(tuple(entries), tuple(rejected))


def _document_problems(document: Any) -> list[str]:
    """Why *document* is not an index this fpdb reads, or ``[]``."""
    if not isinstance(document, dict):
        return ["the index must be a JSON object"]
    problems = []
    if document.get("schema") != INDEX_SCHEMA:
        problems.append(f"schema must be {INDEX_SCHEMA!r}, got {document.get('schema')!r}")
    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        problems.append("version must be a positive integer")
    elif version > INDEX_VERSION:
        problems.append(f"index version {version} is newer than supported ({INDEX_VERSION}); upgrade fpdb")
    if not isinstance(document.get("packs"), list):
        problems.append("packs must be a list")
    return problems


def _entry(raw: Any) -> GalleryEntry:  # noqa: C901, PLR0912 - one check per field, each with its own reason
    if not isinstance(raw, dict):
        raise GalleryError(["an entry must be a JSON object"])
    problems = [f"{name} is missing" for name in _REQUIRED if name not in raw]
    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        problems.append(f"unsupported field(s) {unknown}")
    for name in ("id", "kind", "name", "version", "author", "license", "file", "sha256"):
        if name in raw and (not isinstance(raw[name], str) or not raw[name].strip()):
            problems.append(f"{name} must be a non-empty string")
    for name in ("min_fpdb_version", "description", "screenshot"):
        if name in raw and not isinstance(raw[name], str):
            problems.append(f"{name} must be a string")
    if problems:
        raise GalleryError(problems)

    problem = stat_packs._pack_id_problem(raw["id"])
    if problem:
        problems.append(f"id {problem}")
    kind = raw["kind"]
    if kind not in KINDS:
        problems.append(f"kind {kind!r} is not one this fpdb installs ({', '.join(sorted(KINDS))})")
    if not stat_packs._MIN_VERSION.fullmatch(raw["version"]):
        problems.append(f"version {raw['version']!r} must be written like '1.2' or '1.2.3'")
    minimum = raw.get("min_fpdb_version", "")
    if minimum and not stat_packs._MIN_VERSION.fullmatch(minimum):
        problems.append(f"min_fpdb_version {minimum!r} must be written like '3.9' or '3.9.1'")
    problem = _path_problem(raw["file"], KINDS.get(kind))
    if problem:
        problems.append(f"file {problem}")
    if raw.get("screenshot"):
        problem = _path_problem(raw["screenshot"], None)
        if problem:
            problems.append(f"screenshot {problem}")
    if not _SHA256.fullmatch(raw["sha256"]):
        problems.append("sha256 must be 64 lower-case hexadecimal digits")
    size = raw["size"]
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_PACKAGE_BYTES:
        problems.append(f"size must be a whole number of bytes from 1 to {MAX_PACKAGE_BYTES}")
    stats = raw.get("stats", [])
    if not isinstance(stats, list) or not all(isinstance(name, str) for name in stats):
        problems.append("stats must be a list of stat names")
    if problems:
        raise GalleryError(problems)
    return GalleryEntry(
        id=raw["id"],
        kind=kind,
        name=raw["name"],
        version=raw["version"],
        author=raw["author"],
        license=raw["license"],
        file=raw["file"],
        sha256=raw["sha256"],
        size=size,
        min_fpdb_version=minimum,
        description=raw.get("description", ""),
        screenshot=raw.get("screenshot", ""),
        stats=tuple(stats),
    )


def _path_problem(path: str, suffix: str | None) -> str:
    """Why *path* cannot name a file in the gallery, or ``""``: relative, inside it, portable."""
    pure = PurePosixPath(path)
    if "\\" in path or pure.is_absolute() or ".." in pure.parts or not pure.parts:
        return f"{path!r} must be a relative path inside the gallery"
    problem = stat_packs._portable_name_problem(pure)
    if problem:
        return f"{path!r} {problem}"
    if suffix and pure.suffix != suffix:
        return f"{path!r} must end in {suffix}"
    return ""


def incompatibility(entry: GalleryEntry, fpdb_version: str | None = None) -> str:
    """Why this fpdb cannot use *entry*, or ``""``."""
    return stat_packs._minimum_version_problem(entry.min_fpdb_version, fpdb_version or stat_packs._fpdb_version())


def updates(index: PackIndex, installed: Mapping[str, str]) -> list[tuple[GalleryEntry, str]]:
    """The installed packs the index has a newer version of: ``(entry, installed version)``.

    *installed* maps a pack id to the version installed. A version that cannot
    be read counts as older, so a pack installed by hand can still be updated.
    """
    found = []
    for pack_id, version in installed.items():
        entry = index.get(pack_id)
        if entry is None:
            continue
        try:
            older = stat_packs._version_tuple(version) < stat_packs._version_tuple(entry.version)
        except ValueError:
            older = True
        if older:
            found.append((entry, version))
    return found


# ---------------------------------------------------------------------------
# Packages.
# ---------------------------------------------------------------------------


def package_problems_for(entry: GalleryEntry, data: bytes, *, fpdb_version: str | None = None) -> list[str]:
    """Why *data* is not the package *entry* promises, or ``[]``.

    The bytes are checked against the index first, then against the index's
    ``min_fpdb_version``, then read by the validator a manual import uses for
    that kind of package.
    """
    if len(data) != entry.size:
        return [f"is {len(data)} bytes, the index says {entry.size}"]
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        return ["does not match the checksum in the index"]
    # The index's minimum holds for every kind, and may be stricter than a stat pack's own (Codex, #640).
    too_new = incompatibility(entry, fpdb_version)
    if too_new:
        return [too_new]
    if entry.kind == "hud":
        try:
            root = defusedxml.minidom.parseString(data).documentElement
        except Exception as exc:  # noqa: BLE001 - expat, defusedxml and decoding errors alike
            return [f"is not a readable HUD package: {exc}"]
        return package_problems(root)
    with tempfile.TemporaryDirectory(prefix="fpdb-pack-") as folder:
        archive = Path(folder) / entry.filename
        archive.write_bytes(data)
        try:
            pack = stat_packs.read_pack(archive, fpdb_version=fpdb_version)
        except stat_packs.PackError as exc:
            return list(exc.messages)
    problems = []
    if pack.id != entry.id:
        problems.append(f"the pack inside is {pack.id!r}, the index says {entry.id!r}")
    if pack.pack_version != entry.version:
        problems.append(f"the pack inside is version {pack.pack_version!r}, the index says {entry.version!r}")
    return problems


def location(source: str, path: str) -> str:
    """Where *path* (relative to the gallery) is, for a gallery at *source* (an https URL or a folder)."""
    if _is_url(source):
        return urllib.parse.urljoin(source.rstrip("/") + "/", urllib.parse.quote(path))
    return str(Path(source) / Path(*PurePosixPath(path).parts))


def _is_url(source: str) -> bool:
    return urllib.parse.urlsplit(source).scheme in ("https", "http")


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to another https URL (Codex, #640).

    The index carries the packages' checksums, so it is only as trustworthy as
    the connection it came over: a redirect to plain http is refused, not
    followed.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201, PLR0913 - urllib's signature
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise OSError(f"{req.full_url}: redirected to {newurl}; the gallery is only read over https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_HttpsOnlyRedirects)


def read_location(where: str, limit: int) -> bytes:
    """Read *where*, an https URL or a local file, refusing anything past *limit* bytes."""
    if _is_url(where):
        if urllib.parse.urlsplit(where).scheme != "https":
            raise OSError(f"{where}: the gallery is only read over https")
        request = urllib.request.Request(where, headers={"User-Agent": "fpdb-3 pack gallery"})  # noqa: S310 - https only, checked above
        with _OPENER.open(request, timeout=20) as response:  # https only, redirects included
            data = response.read(limit + 1)
    else:
        with Path(where).open("rb") as handle:
            data = handle.read(limit + 1)
    if len(data) > limit:
        raise OSError(f"{where}: larger than {limit} bytes")
    return data


def load_index(source: str, cache_dir: Path, *, read: Reader = read_location) -> PackIndex:
    """The gallery's index from *source*, kept in *cache_dir*; the cached copy when *source* cannot be read.

    :raises GalleryError: when neither the gallery nor the cache has a usable index.
    """
    cached = Path(cache_dir) / INDEX_NAME
    try:
        data = read(location(source, INDEX_NAME), MAX_INDEX_BYTES)
        index = parse_index(data)
    except (OSError, GalleryError) as exc:
        if not cached.is_file():
            raise GalleryError([f"the gallery could not be read ({exc}) and nothing is cached"], source) from None
        stale = parse_index(cached.read_bytes())
        return PackIndex(stale.entries, stale.rejected, stale=True)
    _write_atomically(cached, data)
    return index


def fetch_package(
    entry: GalleryEntry,
    source: str,
    cache_dir: Path,
    *,
    read: Reader = read_location,
    fpdb_version: str | None = None,
) -> Path:
    """The verified package for *entry*: from the cache when it is there and intact, else from *source*.

    :raises GalleryError: when the package cannot be read or is not what the index promises.
    """
    target = Path(cache_dir) / "packages" / entry.id / entry.version / entry.filename
    if target.is_file() and not package_problems_for(entry, target.read_bytes(), fpdb_version=fpdb_version):
        return target
    try:
        data = read(location(source, entry.file), MAX_PACKAGE_BYTES)
    except OSError as exc:
        raise GalleryError([f"could not be downloaded: {exc}"], entry.id) from None
    problems = package_problems_for(entry, data, fpdb_version=fpdb_version)
    if problems:
        raise GalleryError(problems, entry.id)
    _write_atomically(target, data)
    return target


def _write_atomically(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as handle:
        handle.write(data)
    Path(handle.name).replace(target)


# ---------------------------------------------------------------------------
# Installing.
# ---------------------------------------------------------------------------

#: Where fpdb remembers what it installed from the gallery, beside the user's config.
RECORD_NAME: Final = "pack-gallery.json"
#: The gallery fpdb reads unless ``<general pack_gallery="...">`` names another.
DEFAULT_GALLERY: Final = "https://raw.githubusercontent.com/jejellyroll-fr/fpdb-3-packs/main"


def record_path() -> Path:
    from fpdb_3_legacy.Configuration import CONFIG_PATH  # noqa: PLC0415 - only needed when no path is given

    return Path(CONFIG_PATH) / RECORD_NAME


def read_record(path: Path) -> dict[str, dict[str, Any]]:
    """What was installed from the gallery: ``{id: {"kind", "version", "profiles", "popups", "panel_rules"}}``."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    installed = document.get("installed") if isinstance(document, dict) else None
    return {key: value for key, value in (installed or {}).items() if isinstance(value, dict)}


def _write_record(path: Path, installed: Mapping[str, Mapping[str, Any]]) -> None:
    text = json.dumps({"installed": dict(sorted(installed.items()))}, indent=2, ensure_ascii=False) + "\n"
    _write_atomically(Path(path), text.encode("utf-8"))


def installed_versions(record: Path, packs_dir: Path | None = None) -> dict[str, str]:
    """The installed version of every pack the gallery may know: stat packs as installed, HUDs as recorded."""
    versions = {pack_id: str(entry.get("version", "")) for pack_id, entry in read_record(record).items()}
    for status in stat_packs.list_packs(packs_dir):
        if status.status in (stat_packs.ENABLED, stat_packs.DISABLED):
            versions[status.id] = status.pack_version
    return versions


def _hud_root(package: Path) -> Any:
    root = defusedxml.minidom.parse(str(package)).documentElement
    problems = package_problems(root)
    if problems:
        raise GalleryError(problems, package.name)
    return root


def _named_children(root: Any, tag: str, attribute: str) -> list[str]:
    return [node.getAttribute(attribute) for node in root.childNodes if getattr(node, "tagName", "") == tag]


def _remove_named(config_doc: Any, tag: str, attribute: str, names: Iterable[str]) -> None:
    wanted = set(names)
    for node in list(config_doc.getElementsByTagName(tag)):
        if node.getAttribute(attribute) in wanted:
            node.parentNode.removeChild(node)


def _panel_rules(config_doc: Any) -> list[Any]:
    from fpdb_3_legacy.hud_package import _is_panel_rule_placeholder  # noqa: PLC0415

    return [node for node in config_doc.getElementsByTagName("hud_panel_rules") if not _is_panel_rule_placeholder(node)]


def _panel_scope(section: Any) -> str:
    return section.getAttribute("profile").strip().casefold()


def _remove_panel_rules(config_doc: Any, scopes: Iterable[str]) -> None:
    wanted = set(scopes)
    for section in _panel_rules(config_doc):
        if _panel_scope(section) in wanted:
            section.parentNode.removeChild(section)


def _saved(config_doc: Any, save: Callable[[], None] | None, change: Callable[[], bool]) -> bool:
    """Run *change* on *config_doc*, then *save* it if it changed; on any failure, *config_doc* is as it was.

    The record is written only after this returns, so a configuration that
    could not be saved is never recorded as installed or uninstalled (Codex, #641).
    """
    snapshot = config_doc.documentElement.cloneNode(True)
    try:
        changed = change()
        if changed and save is not None:
            save()
    except BaseException:
        config_doc.replaceChild(snapshot, config_doc.documentElement)
        raise
    return changed


def install_entry(
    entry: GalleryEntry,
    package: Path,
    *,
    config_doc: Any,
    record: Path,
    packs_dir: Path | None = None,
    replace: bool = False,
    save: Callable[[], None] | None = None,
) -> bool:
    """Install the verified *package* of *entry*; whether the HUD configuration changed.

    A stat pack goes into the user pack directory. A HUD package is merged into
    *config_doc* the way the reference HUDs are: its profiles, popups and panel
    rules are added, nothing of the user's is touched, and no game is bound to
    it. An update (*replace*) first removes what the pack installed. It is
    refused when the new version drops a profile a game still uses, and a
    popup it drops stays while something of the user's still opens it.

    When the HUD configuration changed, *save* is called before the record is
    written; if it fails, *config_doc* is restored and the record is left as
    it was.
    """
    record = Path(record)
    installed = read_record(record)
    changed = False
    if entry.kind == "stats":
        stat_packs.install_pack(package, packs_dir, replace=replace)
        installed[entry.id] = {"kind": entry.kind, "version": entry.version}
    else:
        from fpdb_3_legacy.hud_package import install_missing_hud_package, package_popups  # noqa: PLC0415

        root = _hud_root(package)
        previous = installed.get(entry.id, {}) if replace else {}
        # Only what the gallery added is the pack's: a profile or popup of the
        # user's that shares a name is theirs, and is never replaced or removed.
        ours_profiles = set(previous.get("profiles") or [])
        ours_popups = set(previous.get("popups") or [])
        profiles = _named_children(root, "ss", "name")
        taken = [name for name in profiles if name not in ours_profiles and _exists(config_doc, "ss", "name", name)]
        if taken:
            raise GalleryError(
                [f"you already have a HUD profile named {', '.join(taken)}; rename yours to install this pack"],
                entry.id,
            )
        # Codex (#641): a profile the new version drops must not leave a game pointing nowhere.
        bound = _bound_games(config_doc, ours_profiles - set(profiles))
        if bound:
            raise GalleryError(
                [
                    f"this version drops a HUD profile used for {', '.join(bound)}; "
                    "choose another profile for these games first"
                ],
                entry.id,
            )
        new_popups = {popup.getAttribute("pu_name") for popup in package_popups(root)}
        ours_rules = set(previous.get("panel_rules") or [])
        added: dict[str, list[str]] = {}

        def change() -> bool:
            _remove_named(config_doc, "ss", "name", ours_profiles)
            # A popup the new version still has is replaced; one it drops goes only
            # when nothing of the user's still opens it (Codex, #641).
            # Only the user's own profiles and popups count as opening it: the
            # pack's previous popups are all about to be removed or replaced.
            kept = (ours_popups - new_popups) - _unused_popups(config_doc, ours_popups)
            _remove_named(config_doc, "pu", "pu_name", ours_popups - kept)
            # The panel-rule sections the pack added are its own too, and are
            # replaced rather than left selecting the old version's panels (Codex, #641).
            _remove_panel_rules(config_doc, ours_rules)
            rules_before = {_panel_scope(section) for section in _panel_rules(config_doc)}
            added["popups"] = [name for name in sorted(new_popups) if not _exists(config_doc, "pu", "pu_name", name)]
            # No <game> binding: a pack's profile is put to use by the user, in Preferences (Codex, #641).
            changed = install_missing_hud_package(config_doc, root, bind_games=False)
            added["popups"] += sorted(kept)
            added["panel_rules"] = sorted(
                {_panel_scope(section) for section in _panel_rules(config_doc)} - rules_before
            )
            return changed or bool(ours_profiles or ours_popups or ours_rules)

        changed = _saved(config_doc, save, change)
        installed[entry.id] = {
            "kind": entry.kind,
            "version": entry.version,
            "profiles": profiles,
            "popups": added["popups"],
            "panel_rules": added["panel_rules"],
        }
    _write_record(record, installed)
    return changed


def _unused_popups(config_doc: Any, candidates: set[str]) -> set[str]:
    """The *candidates* nothing else opens: no remaining stat, and no popup outside them, even through a chain."""
    submenus = {
        popup.getAttribute("pu_name"): {
            row.getAttribute("pu_stat_submenu") for row in popup.getElementsByTagName("pu_stat")
        }
        for popup in config_doc.getElementsByTagName("pu")
    }
    kept = {node.getAttribute("popup") for node in config_doc.getElementsByTagName("stat")} & candidates
    for name, opens in submenus.items():
        if name not in candidates:
            kept |= opens & candidates
    while True:
        reached = {opened for name in kept for opened in submenus.get(name, ())} & candidates
        if reached <= kept:
            return candidates - kept
        kept |= reached


def _bound_games(config_doc: Any, profiles: set[str]) -> list[str]:
    """The games, as ``game (type)``, whose HUD is one of *profiles*."""
    return sorted(
        {
            f"{node.parentNode.getAttribute('game_name')} ({node.getAttribute('game_type')})"
            for node in config_doc.getElementsByTagName("game_stat_set")
            if node.getAttribute("stat_set") in profiles
        }
    )


def _exists(config_doc: Any, tag: str, attribute: str, name: str) -> bool:
    return any(node.getAttribute(attribute) == name for node in config_doc.getElementsByTagName(tag))


def uninstall_entry(
    pack_id: str,
    *,
    config_doc: Any,
    record: Path,
    packs_dir: Path | None = None,
    save: Callable[[], None] | None = None,
) -> bool:
    """Remove a pack installed from the gallery; whether the HUD configuration changed.

    A HUD whose profile a game still uses is refused with the games named:
    removing it would leave those tables without a HUD. As for an install,
    *save* is called before the record is written, and a failure leaves both
    as they were.
    """
    record = Path(record)
    installed = read_record(record)
    entry = installed.get(pack_id)
    if entry is None:
        raise GalleryError(["was not installed from the gallery"], pack_id)
    changed = False
    if entry.get("kind") == "stats":
        stat_packs.uninstall_pack(pack_id, packs_dir)
    else:
        profiles = set(entry.get("profiles") or [])
        bound = _bound_games(config_doc, profiles)
        if bound:
            raise GalleryError(
                [f"its HUD profile is in use for {', '.join(bound)}; choose another profile for these games first"],
                pack_id,
            )
        rules = set(entry.get("panel_rules") or [])

        def change() -> bool:
            _remove_named(config_doc, "ss", "name", profiles)
            _remove_named(config_doc, "pu", "pu_name", _unused_popups(config_doc, set(entry.get("popups") or [])))
            _remove_panel_rules(config_doc, rules)
            return bool(profiles or entry.get("popups") or rules)

        changed = _saved(config_doc, save, change)
    del installed[pack_id]
    _write_record(record, installed)
    return changed


# ---------------------------------------------------------------------------
# The packs repository's check, and entries for it.
# ---------------------------------------------------------------------------


def index_entry(
    path: Path, *, pack_id: str, kind: str, name: str, version: str, author: str, license: str, **extra: Any
) -> dict[str, Any]:
    """The index entry for the package at *path*, with its size and checksum filled in."""
    data = Path(path).read_bytes()
    entry = {
        "id": pack_id,
        "kind": kind,
        "name": name,
        "version": version,
        "author": author,
        "license": license,
        **extra,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }
    entry.setdefault("file", f"{kind}/{Path(path).name}")
    return entry


def validate_repository(root: Path, *, fpdb_version: str | None = None) -> list[str]:
    """Every problem with the gallery at *root*: its index, each entry, and each package's content."""
    root = Path(root)
    try:
        index = parse_index((root / INDEX_NAME).read_bytes())
    except OSError as exc:
        return [f"{INDEX_NAME}: {exc}"]
    except GalleryError as exc:
        return [str(exc)]
    problems = [f"{label}: {reason}" for label, reason in index.rejected]
    for entry in index.entries:
        package = root / Path(*PurePosixPath(entry.file).parts)
        if not package.is_file():
            problems.append(f"{entry.id}: {entry.file} is not in the repository")
            continue
        problems.extend(
            f"{entry.id}: {problem}"
            for problem in package_problems_for(entry, package.read_bytes(), fpdb_version=fpdb_version)
        )
        if entry.screenshot and not (root / Path(*PurePosixPath(entry.screenshot).parts)).is_file():
            problems.append(f"{entry.id}: screenshot {entry.screenshot} is not in the repository")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fpdb_3_legacy.pack_gallery", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="check a packs repository: its index and every package")
    check.add_argument("root", type=Path)
    check.add_argument("--fpdb-version", help="the fpdb version to check minimum versions against")
    arguments = parser.parse_args(argv)
    problems = validate_repository(arguments.root, fpdb_version=arguments.fpdb_version)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"{arguments.root / INDEX_NAME}: every package checks out")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
