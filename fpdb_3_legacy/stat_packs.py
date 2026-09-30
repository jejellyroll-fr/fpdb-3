"""User-installed declarative stat packs (#403).

The declarative definitions of #306 are data: a stat names a metric, filters,
fragments and display metadata the engine already knows, and nothing else. A
**stat pack** makes that data shareable -- a user installs ``my-pack.fpdbstats``
and its stats appear in the HUD picker and in Research, without editing fpdb,
writing Python or writing SQL.

A pack is a ``manifest.json`` plus the files it lists, either as a folder or as
a ``.fpdbstats`` zip archive::

    {
      "schema": "fpdb_stat_pack",
      "version": 1,
      "id": "example.preflop",
      "name": "Example Preflop Pack",
      "author": "Example",
      "description": "Additional preflop analytics",
      "definition_schema_version": 1,
      "min_fpdb_version": "3.9",
      "fragments": {"example.preflop.btn_open": {"position": ["BTN"]}},
      "definitions": ["stats/btn.json"],
      "presets": ["presets/btn.json"]
    }

What keeps a pack safe is what it *cannot* say:

* every definition goes through :func:`analytics_definitions.parse_definition`,
  the validator the shipped library uses, so a pack can only name registered
  metrics, filters, dimensions, fragments and formats -- no SQL, no Python;
* the manifest and every file it lists are read as JSON, never imported or
  executed -- JSON only, because a pack is made to be shared and must install
  on every fpdb, while YAML needs PyYAML, which fpdb does not ship;
* the listed paths must be plain relative paths inside the pack with a data
  suffix, so a pack cannot point at ``/etc/passwd`` or ``../../somewhere``;
* nothing is fetched from the network, at install or at evaluation.

Identity is namespaced: the pack id is dotted (``author.topic``) and every
definition, fragment and preset it adds must start with ``<pack id>.``. A pack
can therefore never replace a built-in stat, and two packs cannot claim the same
name -- both are refused at install with the offending names listed.

Installed packs live in the user's data directory
(``<fpdb config dir>/stat-definitions.d/<pack id>/``), never in the application
package. Enabled/disabled state is a small ``state.json`` beside them. The
registries read the packs when they are built, so a change is picked up by what
is opened next; the HUD process keeps the registry it started with, which is why
the manager asks for a restart rather than refreshing half the app.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
import unicodedata
import zipfile
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final

from . import analytics_definitions as definitions
from .analytics_definitions import DEFINITION_SCHEMA_VERSION, StatDefinition
from .loggingFpdb import get_logger

log = get_logger("stat_packs")

PACK_SCHEMA: Final = "fpdb_stat_pack"
PACK_SCHEMA_VERSION: Final = 1
PACK_SUFFIX: Final = ".fpdbstats"
MANIFEST_NAME: Final = "manifest.json"
STATE_NAME: Final = "state.json"
USER_DIR_NAME: Final = "stat-definitions.d"

# Status words the manager shows; "built-in" is the shipped library itself.
BUILTIN: Final = "built-in"
ENABLED: Final = "installed"
DISABLED: Final = "disabled"
INVALID: Final = "invalid"

_MANIFEST_FIELDS: Final = frozenset(
    {
        "schema",
        "version",
        "id",
        "name",
        "author",
        "description",
        "pack_version",
        "definition_schema_version",
        "min_fpdb_version",
        "fragments",
        "definitions",
        "presets",
    },
)
_DATA_SUFFIXES: Final = (".json",)
# ``author.topic`` or deeper: lower-case segments, at least two of them, so a
# pack id reads as a namespace and cannot be mistaken for a built-in stat name.
# Used with fullmatch: "$" alone also matches before a final newline.
_PACK_ID: Final = re.compile(r"[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+")
_RESERVED_NAMESPACES: Final = frozenset({"fpdb", "builtin", "core"})
# What a stat, fragment or preset a pack adds may be called: an identifier.
_NAME: Final = re.compile(r"[A-Za-z0-9_.-]+")
# A minimum fpdb version: up to three numeric parts, the ones compared. A fourth
# part, a suffix or a word would be dropped by the comparison and let a pack
# past the gate it declares. Used with fullmatch.
_MIN_VERSION: Final = re.compile(r"[0-9]{1,9}(?:\.[0-9]{1,9}){0,2}")
# A date bound as H.startTime stores it and compares it as text: a date, or a
# date and a time separated by a space ("T" sorts after " " and would shift it).
_DATE_BOUND: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?: [0-9]{2}:[0-9]{2}(?::[0-9]{2})?)?")
_DATE_FILTERS: Final = frozenset({"date_from", "date_to"})
_WINDOWS_FORBIDDEN: Final = re.compile(r'[<>:"|?*\x00-\x1f]')
_WINDOWS_RESERVED: Final = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))},
)
# Generous for data, small enough that an archive cannot fill the disk.
MAX_ARCHIVE_FILES: Final = 200
# Members an archive may hold around its pack. Finder adds an AppleDouble
# sidecar under __MACOSX/ for each file it zips, so a pack at the file limit
# comes in an archive of twice as many members; the byte budget still covers
# every one of them.
MAX_ARCHIVE_MEMBERS: Final = 2 * MAX_ARCHIVE_FILES + 2
# Fragments, stats or presets one pack may declare, of each. fpdb ships five
# stats and twenty fragments; the file limit cannot bound these, since a 5 MB
# manifest holds a few hundred thousand empty fragments, each validated,
# kept and merged into every registry built afterwards.
MAX_PACK_ENTRIES: Final = 500
# The root Finder writes its metadata under: never part of a pack.
_FINDER_METADATA: Final = "__MACOSX/"
MAX_ARCHIVE_BYTES: Final = 5 * 1024 * 1024
# Problems reported for one pack. Past this, reading stops: a few bytes per bad
# entry would otherwise become a message each -- a crafted 5 MB file holds a
# million -- and the import would build hundreds of megabytes of them.
MAX_REPORTED_ERRORS: Final = 50
# Characters kept of one problem. A message quotes the value it refuses, and a
# pack can make one value megabytes long and have fifty definitions name it:
# fifty whole copies would be hundreds of megabytes in the report.
MAX_ERROR_CHARS: Final = 500
# More decimal places than any stat can mean; a pack cannot ask for more.
MAX_PRECISION: Final = 10
# The common limit on one path component (ext4, APFS, NTFS): a longer name
# cannot be created on every system a pack may be installed on.
MAX_NAME_BYTES: Final = 255
# A listed path as a whole: deep enough for any pack's layout, and short enough
# that a longest-allowed name in a folder still fits well within macOS's
# 1,024-byte path limit once under the install folder.
MAX_PATH_DEPTH: Final = 8
MAX_PATH_LENGTH: Final = 512  # bytes of UTF-8, what the file system counts
# The largest number a filter may hold. SQLite binds integers as 64 bits, and a
# sizing range in per cent is multiplied by 100 before it is bound; 2**53 keeps
# both exact and inside that, far past any real hand id, stake or stack.
MAX_FILTER_NUMBER: Final = 2**53
# What fpdb wraps a pack id in inside the pack directory: the staging folder is
# ".<id>." plus mkdtemp's eight random characters, and the install a
# replacement moves aside is ".<id>.previous". Both add ten characters.
MAX_ID_LENGTH: Final = MAX_NAME_BYTES - len("..previous")
# Digits allowed in one component of a version. A real version has a handful;
# Python refuses to read an integer literal of more than 4300 digits, and a
# *quoted* component of that length would reach int() as a bare ValueError no
# pack handler catches, so a longer one is refused.
MAX_VERSION_DIGITS: Final = 9


def _clip(message: str) -> str:
    """One problem, cut to about MAX_ERROR_CHARS characters.

    Cut in the middle: a message names what it refuses first and why last, and
    what runs long is the value quoted between them.
    """
    if len(message) <= MAX_ERROR_CHARS:
        return message
    half = MAX_ERROR_CHARS // 2
    return f"{message[:half]} … {message[-half:]}"


class _ErrorLog(list[str]):
    """The problems found in one pack, each cut as it is recorded.

    Cut when recorded rather than when reported, so a long message is never
    held whole: fifty copies of a quoted 4 MB value never exist together.
    """

    def append(self, message: str) -> None:
        super().append(_clip(message))

    def extend(self, messages: Iterable[str]) -> None:
        for message in messages:
            self.append(message)


class PackError(ValueError):
    """A pack that cannot be installed or loaded, with every reason found."""

    def __init__(self, messages: Iterable[str], source: str = "") -> None:
        self.messages = [_clip(message) for message in messages] or ["invalid pack"]
        self.source = source
        prefix = f"{source}: " if source else ""
        super().__init__(prefix + "; ".join(self.messages))


@dataclass(frozen=True)
class StatPack:
    """A validated pack: its manifest, the definitions and presets it adds."""

    id: str
    name: str
    author: str
    description: str
    pack_version: str
    min_fpdb_version: str
    fragments: Mapping[str, Mapping[str, Any]]
    definitions: tuple[StatDefinition, ...]
    presets: tuple[Any, ...]
    files: Mapping[str, bytes] = field(repr=False, default_factory=dict)
    manifest: Mapping[str, Any] = field(repr=False, default_factory=dict)


@dataclass(frozen=True)
class PackStatus:
    """One row of the pack manager."""

    id: str
    name: str
    status: str
    definitions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    author: str = ""
    description: str = ""
    pack_version: str = ""
    path: str = ""


# ---------------------------------------------------------------------------
# Locations and state.
# ---------------------------------------------------------------------------


def user_packs_dir() -> Path:
    """Where installed packs live: the user's fpdb data directory."""
    from .Configuration import CONFIG_PATH  # noqa: PLC0415 - only needed when no directory is given

    return Path(CONFIG_PATH) / USER_DIR_NAME


def _root(packs_dir: str | Path | None) -> Path:
    return Path(packs_dir) if packs_dir is not None else user_packs_dir()


def _read_state(root: Path) -> dict[str, Any]:
    path = root / STATE_NAME
    if not path.is_file():
        return {"disabled": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        log.warning("Unreadable %s; treating every pack as enabled", path)
        return {"disabled": []}
    if not isinstance(state, dict) or not isinstance(state.get("disabled", []), list):
        log.warning("Malformed %s; treating every pack as enabled", path)
        return {"disabled": []}
    # Only pack ids are kept: anything else (an object, a number) would break
    # every reader of the state, and cannot name a pack anyway.
    disabled = [entry for entry in state.get("disabled", []) if isinstance(entry, str) and _PACK_ID.fullmatch(entry)]
    if len(disabled) != len(state.get("disabled", [])):
        log.warning("Ignored malformed entries in %s", path)
    return {**state, "disabled": disabled}


def _write_state(root: Path, state: Mapping[str, Any]) -> None:
    """Replace ``state.json`` atomically.

    An unreadable state reads as "everything enabled", so a write cut short
    must never leave a truncated file: the new state goes to a temporary file
    that replaces the old one in a single step.
    """
    root.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{STATE_NAME}.", dir=root)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(_canonical_json(state))
        os.replace(temporary, root / STATE_NAME)
    except OSError:
        Path(temporary).unlink(missing_ok=True)
        raise


def _canonical_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Reading a pack.
# ---------------------------------------------------------------------------


def _safe_member(name: str, source: str) -> str:
    """A listed path as a normalized relative path inside the pack, or refuse it."""
    if not isinstance(name, str) or not name.strip():
        raise PackError([f"file path {name!r} must be a non-empty string"], source)
    if "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise PackError([f"file path {name!r} must be relative, with forward slashes"], source)
    path = PurePosixPath(name)
    if any(part in ("", ".", "..") for part in path.parts):
        raise PackError([f"file path {name!r} must stay inside the pack"], source)
    if path.suffix.lower() not in _DATA_SUFFIXES:
        raise PackError(
            [f"file {name!r} is not a data file; allowed suffixes: {list(_DATA_SUFFIXES)}"],
            source,
        )
    if len(path.parts) > MAX_PATH_DEPTH or len(name.encode("utf-8", "surrogatepass")) > MAX_PATH_LENGTH:
        # Each part may be short and portable while the whole is not: creating
        # 1,800 nested folders recurses past Python's limit, and a very long
        # path under the install folder exceeds what the system accepts.
        raise PackError(
            [f"file path {name!r} is too deep or too long (at most {MAX_PATH_DEPTH} levels, {MAX_PATH_LENGTH} bytes)"],
            source,
        )
    problem = _portable_name_problem(path)
    if problem:
        raise PackError([f"file path {name!r} {problem}"], source)
    canonical = path.as_posix()
    if canonical != name:
        # "./a.json" and "a//b.json" read the same file under another name; the
        # manifest must spell it the one way the pack stores it.
        raise PackError([f"file path {name!r} must be written {canonical!r}"], source)
    return canonical


def _portable_name_problem(path: PurePosixPath) -> str:
    """Why a path would not name one distinct file on every system, or ``""``.

    Windows drops a trailing dot or space from a name ("stats." is "stats"),
    reserves device names (CON, NUL, COM1...) and forbids a few characters;
    a pack installs everywhere, so its paths must mean the same file everywhere.
    A name that no file system can hold at all -- one past the common component
    limit, or one JSON can carry but UTF-8 cannot encode -- is refused here,
    where the pack is read, rather than by the write that follows it.
    """
    for part in path.parts:
        if part != part.rstrip(". "):
            return "has a name ending in a dot or a space"
        if _WINDOWS_FORBIDDEN.search(part):
            return 'uses a character Windows does not allow (<>:"|?* or a control character)'
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
            return f"uses the reserved Windows name {part.split('.', 1)[0]!r}"
        try:
            encoded = part.encode("utf-8")
        except UnicodeEncodeError:
            return "is not valid UTF-8 text"
        if len(encoded) > MAX_NAME_BYTES:
            return f"has a name longer than {MAX_NAME_BYTES} bytes"
    return ""


def _read_files(source: Path) -> dict[str, bytes]:
    """Every file of a pack folder or ``.fpdbstats`` archive, by relative path."""
    if source.is_dir():
        return _read_folder(source)
    if source.is_file() and source.name == MANIFEST_NAME:
        return _read_files(source.parent)
    if source.is_file() and zipfile.is_zipfile(source):
        return _read_archive(source)
    raise PackError(["expected a pack folder, its manifest.json, or a .fpdbstats archive"], str(source))


def _read_folder(source: Path) -> dict[str, bytes]:
    """The manifest of a pack folder and the files it lists, nothing else.

    A folder is often where a pack was downloaded or unpacked, beside anything
    else; reading only what the manifest names -- under the same count and
    size limits as an archive -- keeps an unrelated large file from being
    loaded. Anything the manifest gets wrong is left for :func:`read_pack` to
    report with the rest.
    """
    manifest_path = source / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return {}
    files = {MANIFEST_NAME: _read_bounded(manifest_path, MAX_ARCHIVE_BYTES, str(source))}
    try:
        manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return files
    if not isinstance(manifest, Mapping):
        return files
    listed = [
        entry
        for key in ("definitions", "presets")
        if isinstance(manifest.get(key), list)
        for entry in manifest[key]
        if isinstance(entry, str)
    ]
    # The manifest is one of the pack's files: an archive counts it, and the
    # export of a folder writes it, so a folder counts it too -- otherwise
    # fpdb could export a pack it then refuses to import.
    problem = _listing_size_problem(manifest)
    if problem:
        raise PackError([problem], str(source))
    total = len(files[MANIFEST_NAME])
    for entry in listed:
        try:
            name = _safe_member(entry, str(source))
        except PackError:
            continue
        # No component of the path may be a link: a linked file, or a linked
        # folder above it, would read something outside the pack.
        path = source
        for part in PurePosixPath(name).parts:
            path = path / part
            if path.is_symlink():
                raise PackError([f"{name}: symbolic links are not allowed in a pack"], str(source))
        if not path.is_file():
            continue
        data = _read_bounded(path, MAX_ARCHIVE_BYTES - total, str(source))
        total += len(data)
        files[name] = data
    return files


def _read_bounded(path: Path, budget: int, source: str) -> bytes:
    """A file's bytes, refused past ``budget`` without reading it whole."""
    if path.stat().st_size > budget:
        raise PackError([f"the pack is larger than {MAX_ARCHIVE_BYTES} bytes"], source)
    return path.read_bytes()


def _read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo, budget: int, source: str) -> bytes:
    """One archive entry, decompressed in chunks and never past ``budget`` bytes.

    The sizes in a zip header are the archive's own claim; reading in bounded
    chunks means a crafted entry (a zip bomb) is stopped at the budget instead
    of being inflated in memory first.
    """
    # No compression-ratio test: repetitive JSON compresses far past any fixed
    # ratio, and fpdb's own exports would be refused on re-import. The bounded
    # read below is what stops a bomb, whatever its ratio.
    chunks: list[bytes] = []
    size = 0
    with archive.open(info) as entry:
        while chunk := entry.read(64 * 1024):
            size += len(chunk)
            if size > budget:
                raise PackError([f"archive is larger than {MAX_ARCHIVE_BYTES} bytes uncompressed"], source)
            chunks.append(chunk)
    return b"".join(chunks)


def _read_archive(source: Path) -> dict[str, bytes]:
    # Opening a zip parses its whole central directory into memory, before any
    # entry count can be checked; an archive file larger than a pack may hold
    # uncompressed is refused before it is opened.
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise PackError([f"the archive is larger than {MAX_ARCHIVE_BYTES} bytes"], str(source))
    try:
        files = _read_archive_entries(source)
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError) as exc:
        # A damaged entry (bad CRC, truncated data), encryption or an
        # unsupported compression method: the archive is refused, not raised.
        raise PackError([f"the archive cannot be read: {exc}"], str(source)) from exc
    files = {name: data for name, data in files.items() if not name.startswith(_FINDER_METADATA)}
    # An archive made by zipping the pack folder has the pack in one top-level
    # directory -- possibly beside others it does not list, such as the
    # __MACOSX/ metadata Finder adds -- so the pack is the one directory that
    # holds a manifest.
    if MANIFEST_NAME not in files:
        roots = sorted(
            name[: -len(MANIFEST_NAME) - 1]
            for name in files
            if name.count("/") == 1 and name.endswith(f"/{MANIFEST_NAME}")
        )
        if len(roots) > 1:
            raise PackError(
                [f"the archive holds several packs ({', '.join(roots)}); share one per archive"], str(source)
            )
        if roots:
            prefix = f"{roots[0]}/"
            files = {name[len(prefix) :]: data for name, data in files.items() if name.startswith(prefix)}
    # The pack's own limit, counted once its root is known: what surrounds it
    # (Finder's sidecars, a README beside the folder) is not part of it.
    if len(files) > MAX_ARCHIVE_FILES:
        raise PackError([f"the pack holds {len(files)} files; at most {MAX_ARCHIVE_FILES}"], str(source))
    return files


def _read_archive_entries(source: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total = 0
    with zipfile.ZipFile(source) as archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        if len(entries) > MAX_ARCHIVE_MEMBERS:
            raise PackError([f"archive holds {len(entries)} files; at most {MAX_ARCHIVE_MEMBERS}"], str(source))
        for info in entries:
            name = info.filename
            # The same containment rule as the manifest's listed paths, applied
            # to every entry: an archive cannot smuggle a path out of the pack.
            if name.startswith("/") or "\\" in name or ".." in PurePosixPath(name).parts:
                raise PackError([f"archive entry {name!r} escapes the pack"], str(source))
            # "stats//a.json" or "./manifest.json" name the same file as the
            # canonical spelling: stored under one key, the later one would
            # silently replace the member the manifest actually lists.
            canonical = PurePosixPath(name).as_posix()
            if canonical != name or canonical in files:
                raise PackError([f"archive entry {name!r} repeats or re-spells another entry"], str(source))
            data = _read_entry(archive, info, MAX_ARCHIVE_BYTES - total, str(source))
            total += len(data)
            files[canonical] = data
    return files


def _parse_data(name: str, data: bytes, source: str) -> Any:
    """A data file's content, with every way it can be unreadable as a PackError."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackError([f"{name} is not UTF-8 text: {exc}"], source) from exc
    try:
        document = json.loads(text, object_pairs_hook=_unique_keys)
        # UTF-8 bytes can still spell a lone surrogate as an escape ("\ud800"):
        # json.loads keeps it, and the database driver cannot encode it when a
        # filter binds it, so the stat would fail every time it runs. A string
        # anywhere in the file has to be text that can be written back out.
        json.dumps(document, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PackError([f"{name} holds text that is not valid Unicode (a lone surrogate escape)"], source) from exc
    except ValueError as exc:
        # JSONDecodeError, a repeated key, and the plain ValueError of an
        # integer longer than Python's int-string limit: either way the file
        # cannot be read as written.
        raise PackError([f"{name} is not valid JSON: {exc}"], source) from exc
    except RecursionError as exc:
        # Valid JSON nested deeper than the parser can follow: still refused.
        raise PackError([f"{name} is nested too deeply to read"], source) from exc
    return document


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A JSON object, refused if it names a key twice.

    json.loads keeps the last of two equal keys, so the first is never seen by
    any check: ``"in_position": "false", "in_position": true`` would install
    as the second alone, a stat meaning something other than its file says.
    """
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"key {key!r} appears twice in one object")
        document[key] = value
    return document


def _version_tuple(version: str) -> tuple[int, ...]:
    """The first three components of a version, as numbers.

    A component longer than ``MAX_VERSION_DIGITS`` digits raises ValueError:
    past Python's integer-string limit ``int()`` cannot read it at all, and
    reading only its leading digits would compare "00000000099" as 0 and let
    a pack that needs fpdb 99 install here.
    """
    numbers = re.findall(r"\d+", version)
    if any(len(number) > MAX_VERSION_DIGITS for number in numbers):
        raise ValueError(f"has a component longer than {MAX_VERSION_DIGITS} digits")
    return tuple(int(number) for number in numbers[:3])


def _fpdb_version() -> str:
    from . import __version__  # noqa: PLC0415 - avoids importing the package root at module load

    return str(__version__)


def _version_error(value: Any, field_name: str, what: str, supported: int) -> str:
    """Why a schema version cannot be read here, or ``""``."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return f"{field_name} must be a positive integer"
    if value > supported:
        return f"{what} version {value} is newer than supported ({supported}); upgrade fpdb"
    return ""


def _pack_id_problem(pack_id: Any) -> str:
    """Why a manifest id cannot name a pack, or ``""``."""
    if not isinstance(pack_id, str) or not _PACK_ID.fullmatch(pack_id):
        return "must be a dotted lower-case namespace such as 'author.topic'"
    if pack_id.split(".", 1)[0] in _RESERVED_NAMESPACES:
        return f"uses a reserved namespace ({sorted(_RESERVED_NAMESPACES)})"
    # The id is the install folder's name: "con.stats" cannot be one on Windows.
    problem = _portable_name_problem(PurePosixPath(pack_id))
    if problem:
        return problem
    if len(pack_id) > MAX_ID_LENGTH:
        # fpdb writes a staging folder and a backup beside the install, each the
        # id plus ten characters: past the component limit the id validates here
        # and the install then fails with ENAMETOOLONG, reported as a read error.
        return f"is longer than {MAX_ID_LENGTH} characters; it names the install folder"
    return ""


def _minimum_version_problem(minimum: str, running: str) -> str:
    """Why this fpdb cannot load a pack asking for ``minimum``, or ``""``."""
    if not minimum:
        return ""
    if not _MIN_VERSION.fullmatch(minimum):
        return f"min_fpdb_version {minimum!r} must be written like '3.9' or '3.9.1', each part at most {MAX_VERSION_DIGITS} digits"
    try:
        if _version_tuple(minimum) > _version_tuple(running):
            return f"needs fpdb {minimum} or newer (this is {running})"
    except ValueError as exc:
        return f"min_fpdb_version {exc}"
    return ""


def _manifest_errors(manifest: Mapping[str, Any], running: str) -> tuple[list[str], str, str]:
    """The manifest's own problems, its pack id and its minimum fpdb version."""
    errors: list[str] = []
    unknown = sorted(set(manifest) - _MANIFEST_FIELDS)
    if unknown:
        errors.append(f"unsupported manifest field(s) {unknown}; allowed: {sorted(_MANIFEST_FIELDS)}")
    if manifest.get("schema") != PACK_SCHEMA:
        errors.append(f"schema must be {PACK_SCHEMA!r}, got {manifest.get('schema')!r}")
    for field_name, what, supported, default in (
        ("version", "pack schema", PACK_SCHEMA_VERSION, None),
        ("definition_schema_version", "definition schema", DEFINITION_SCHEMA_VERSION, DEFINITION_SCHEMA_VERSION),
    ):
        problem = _version_error(manifest.get(field_name, default), field_name, what, supported)
        if problem:
            errors.append(problem)
    minimum = str(manifest.get("min_fpdb_version") or "")
    problem = _minimum_version_problem(minimum, running)
    if problem:
        errors.append(problem)

    pack_id = manifest.get("id")
    problem = _pack_id_problem(pack_id)
    if problem:
        errors.append(f"id {pack_id!r} {problem}")
        if not isinstance(pack_id, str) or not _PACK_ID.fullmatch(pack_id):
            pack_id = ""
    for text_field in ("name", "author", "description", "pack_version", "min_fpdb_version"):
        if text_field in manifest and not isinstance(manifest[text_field], str):
            errors.append(f"{text_field} must be a string")
    return errors, pack_id or "", minimum


def read_pack(source: str | Path, *, fpdb_version: str | None = None) -> StatPack:
    """Read and validate a pack on its own (collisions are checked at install).

    Every problem found is reported together, so an author fixes a pack in one
    pass instead of one error at a time.
    """
    source = Path(source)
    label = source.name
    files = _read_files(source)
    if MANIFEST_NAME not in files:
        raise PackError([f"no {MANIFEST_NAME} at the top of the pack"], label)
    manifest = _parse_data(MANIFEST_NAME, files[MANIFEST_NAME], label)
    if not isinstance(manifest, Mapping):
        raise PackError([f"{MANIFEST_NAME} must be an object"], label)

    errors, pack_id, minimum = _manifest_errors(manifest, fpdb_version or _fpdb_version())
    if errors:
        # The version and identity checks come first: a pack for a newer schema
        # is refused before any of its files is interpreted.
        raise PackError(errors, label)
    # Before any list is walked: an archive counts its members, not the
    # entries of a list in its manifest.
    problem = _listing_size_problem(manifest)
    if problem:
        raise PackError([problem], label)
    errors = _ErrorLog()

    prefix = f"{pack_id}."
    fragments = _read_fragments(manifest.get("fragments", {}), prefix, errors)
    library = {**definitions.FILTER_FRAGMENTS, **fragments}
    stats = _read_definitions(manifest.get("definitions", []), files, prefix, library, pack_id, label, errors)
    presets = _read_presets(manifest.get("presets", []), files, prefix, label, errors)
    if not stats and not presets and not errors:
        errors.append("a pack must add at least one definition or preset")
    if _full(errors):
        errors = [*errors[:MAX_REPORTED_ERRORS], f"stopped after {MAX_REPORTED_ERRORS} problems; fix these first"]
    if errors:
        raise PackError(errors, label)
    listed = {MANIFEST_NAME, *manifest.get("definitions", []), *manifest.get("presets", [])}
    errors = _folded_collisions(listed)
    if errors:
        raise PackError(errors, label)
    return StatPack(
        id=pack_id,
        name=str(manifest.get("name") or pack_id),
        author=str(manifest.get("author") or ""),
        description=str(manifest.get("description") or ""),
        pack_version=str(manifest.get("pack_version") or ""),
        min_fpdb_version=minimum,
        fragments=fragments,
        definitions=tuple(stats),
        presets=tuple(presets),
        # Only what the manifest lists is kept: stray files in a folder or an
        # archive are neither installed nor re-shared.
        files={name: data for name, data in files.items() if name in listed},
        manifest=dict(manifest),
    )


def _name_problem(name: str, prefix: str) -> str:
    """Why a name a pack adds is not acceptable, or ``""``.

    Beyond the namespace, the name is an identifier: it is written into
    HUD_config.xml when a stat is placed on a HUD, so a control character
    there would leave a configuration fpdb cannot read back.
    """
    if not name.startswith(prefix):
        return f"must be namespaced under {prefix!r}"
    if not _NAME.fullmatch(name):
        return "may only use letters, digits, '_', '.' and '-'"
    return ""


def _read_fragments(raw: Any, prefix: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, Mapping):
        errors.append("fragments must be an object of name -> filters")
        return {}
    if len(raw) > MAX_PACK_ENTRIES:
        # Refused before any is looked at: walking them is the cost.
        errors.append(f"the manifest declares {len(raw)} fragments; a pack holds at most {MAX_PACK_ENTRIES}")
        return {}
    fragments: dict[str, dict[str, Any]] = {}
    for name, filters in raw.items():
        if _full(errors):
            break
        problem = _name_problem(str(name), prefix)
        if problem:
            errors.append(f"fragment {name!r} {problem}")
            continue
        if not isinstance(filters, Mapping):
            errors.append(f"fragment {name!r} must be an object of filter -> value")
            continue
        own = {key: value for key, value in filters.items() if key != "fragments"}
        try:
            resolved = definitions.validate_filters(own, f"fragment {name}")
        except (ArithmeticError, AttributeError, TypeError, ValueError) as exc:
            errors.append(f"fragment {name!r}: {exc}")
            continue
        nested = filters.get("fragments", [])
        if not isinstance(nested, list) or not all(isinstance(item, str) for item in nested):
            errors.append(f"fragment {name!r}: fragments must be a list of fragment names")
            continue
        if nested:
            resolved["fragments"] = list(nested)
        fragments[str(name)] = resolved
    return fragments


def _folded_collisions(listed: Iterable[str]) -> list[str]:
    """Listed files that would land on one file on some systems."""
    problems: list[str] = []
    folded: dict[str, str] = {}
    for name in sorted(listed):
        # Windows and macOS file systems ignore case, and macOS also Unicode
        # normalization ("é" as one code point or two): names that differ only
        # that way would be written to one file, and the install would lose one.
        key = unicodedata.normalize("NFC", name).casefold()
        if key in folded:
            problems.append(f"files {folded[key]!r} and {name!r} name the same file on some systems")
        folded[key] = name
    return problems


def _listing_size_problem(manifest: Mapping[str, Any]) -> str:
    """Why the manifest lists more entries than a pack can hold, or ``""``.

    Every entry counts, not only the paths: a list of a million numbers is
    as long to walk, and each would be reported as a problem of its own. The
    manifest is one of the pack's files too -- an archive counts it, and the
    export of a folder writes it.
    """
    count = sum(len(manifest[key]) for key in ("definitions", "presets") if isinstance(manifest.get(key), list))
    if count + 1 > MAX_ARCHIVE_FILES:
        return f"the manifest lists {count} files; a pack holds at most {MAX_ARCHIVE_FILES}, the manifest included"
    return ""


def _full(errors: list[str]) -> bool:
    """Whether enough problems are recorded to stop reading (MAX_REPORTED_ERRORS)."""
    return len(errors) >= MAX_REPORTED_ERRORS


def _listed_documents(
    listed: Any,
    files: Mapping[str, bytes],
    what: str,
    label: str,
    errors: list[str],
) -> list[tuple[str, Any]]:
    """The parsed files a manifest list names, recording what cannot be read."""
    if not isinstance(listed, list):
        errors.append(f"{what} must be a list of file paths")
        return []
    documents: list[tuple[str, Any]] = []
    for entry in listed:
        try:
            name = _safe_member(entry, label)
            if name not in files:
                raise PackError([f"listed file {name!r} is missing from the pack"])
            documents.append((name, _parse_data(name, files[name], label)))
        except PackError as exc:
            errors.extend(exc.messages)
    return documents


def _read_definitions(
    listed: Any,
    files: Mapping[str, bytes],
    prefix: str,
    library: Mapping[str, Mapping[str, Any]],
    pack_id: str,
    label: str,
    errors: list[str],
) -> list[StatDefinition]:
    stats: list[StatDefinition] = []
    seen: set[str] = set()
    for name, document in _listed_documents(listed, files, "definitions", label, errors):
        if _full(errors):
            break
        try:
            entries = _entries_in(document, name)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if len(stats) + len(entries) > MAX_PACK_ENTRIES:
            errors.append(f"{name}: the pack defines more than {MAX_PACK_ENTRIES} stats")
            break
        for entry in entries:
            if _full(errors):
                break
            # One definition at a time, so every bad one in the file is reported.
            try:
                definition = _checked_definition(entry, name, prefix, library, pack_id, seen)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            seen.add(definition.name)
            stats.append(definition)
    return stats


def _checked_definition(
    entry: Mapping[str, Any],
    name: str,
    prefix: str,
    library: Mapping[str, Mapping[str, Any]],
    pack_id: str,
    seen: set[str],
) -> StatDefinition:
    """One definition through the shipped validator, the namespace and the compiler."""
    try:
        definition = definitions.parse_definition(entry, f"pack:{pack_id}/{name}")
    except (ArithmeticError, AttributeError, TypeError) as exc:
        # The shared parser trusts shipped shapes; from a pack, a wrong shape
        # is the pack's error to report, not an exception to leak.
        raise ValueError(f"{name}: {exc}") from exc
    problem = _name_problem(definition.name, prefix)
    if problem:
        raise ValueError(f"{name}: stat {definition.name!r} {problem}")
    precision = definition.display.precision
    if precision is not None and precision > MAX_PRECISION:
        # Rendered as f"{value:.{precision}f}": a huge precision would build
        # an enormous string every time the stat is drawn.
        raise ValueError(f"{name}: stat {definition.name!r} precision must be at most {MAX_PRECISION}")
    if definition.name in seen:
        raise ValueError(f"{name}: stat {definition.name!r} is defined twice in the pack")
    try:
        # Compiled exactly as the engine will run it: this is where a bad
        # filter *value* ("position": ["dealer-ish"]) is caught.
        definitions.compile_definition(definition, fragments=library)
        query = definitions.resolve_query(definition, fragments=library)
        # Checked apart: a merged dict would hide the denominator's value
        # wherever the numerator names the same filter.
        problem = _filter_value_problem(query.filters) or _filter_value_problem(query.numerator)
        if problem:
            raise ValueError(problem)
    except (ArithmeticError, AttributeError, TypeError, ValueError) as exc:
        # A malformed value ({"bet_sizing_pct": [{}, 50]}) fails as a TypeError
        # deep in the compiler; it is still just a bad value in the pack.
        raise ValueError(f"{name}: stat {definition.name!r}: {exc}") from exc
    except RecursionError as exc:
        # Fragments are expanded recursively: a chain of a thousand fragments,
        # each naming the next, exhausts the stack. Refused, not raised.
        raise ValueError(f"{name}: stat {definition.name!r}: its fragments are nested too deeply") from exc
    return definition


def _entries_in(document: Any, name: str) -> list[Mapping[str, Any]]:
    """The raw definitions of one file, after the shipped library's file checks."""
    return definitions.definition_entries(document, name)


def _read_presets(listed: Any, files: Mapping[str, bytes], prefix: str, label: str, errors: list[str]) -> list[Any]:
    from . import research_presets  # noqa: PLC0415 - Research is optional for a stats-only pack

    presets: list[Any] = []
    seen: set[str] = set()
    for name, raw in _listed_documents(listed, files, "presets", label, errors):
        if _full(errors):
            break
        try:
            listed_presets = raw.get("presets") if isinstance(raw, Mapping) else None
            if isinstance(listed_presets, list) and len(presets) + len(listed_presets) > MAX_PACK_ENTRIES:
                # Before the shipped validator, which compiles every one.
                errors.append(f"{name}: the pack defines more than {MAX_PACK_ENTRIES} presets")
                break
            pack = research_presets.validate_preset_pack(raw, name)
        except (ArithmeticError, AttributeError, TypeError, ValueError) as exc:
            # The shipped validator trusts shipped data's shapes; a pack's data
            # is not shipped, so a wrong shape is its error, not a crash.
            errors.append(f"{name}: {exc}")
            continue
        for preset in pack.presets:
            if _full(errors):
                break
            problem = _name_problem(preset.id, prefix)
            if problem:
                errors.append(f"{name}: preset {preset.id!r} {problem}")
                continue
            # The preset validator checks one file; the picker resolves a preset
            # by id, so an id repeated in another file of the pack is ambiguous.
            if preset.id in seen:
                errors.append(f"{name}: preset {preset.id!r} is defined twice in the pack")
                continue
            problem = _preset_compile_error(preset)
            if problem:
                errors.append(f"{name}: preset {preset.id!r}: {problem}")
                continue
            seen.add(preset.id)
            presets.append(preset)
    return presets


def _filter_value_problem(filters: Mapping[str, Any], *, preset: bool = False) -> str:
    """Why a filter value would not mean what it says, or ``""``.

    The compiler is lenient where a pack must not be: it binds range bounds as
    they come (the Research filter row later reads them with float()), reads
    a range mapping with misspelled keys as "unbounded", and turns any
    non-empty string into True, so ``"in_position": "false"`` or
    ``{"is_null": "false"}`` would measure the opposite of what they say. For
    a preset, a one-sided date or hand range cannot be shown by Research's
    two-ended range control either.
    """
    from .analytics_query import FILTERS  # noqa: PLC0415

    for name, value in filters.items():
        spec = FILTERS.get(name)
        if spec is None:
            continue
        problem = _one_filter_problem(name, value, spec.kind, preset=preset)
        if not problem and preset:
            problem = _research_round_trip_problem(name, value, spec.kind)
        if not problem:
            problem = _bound_parameter_problem(name, value)
        if problem:
            return problem
    return ""


def _bound_parameter_problem(name: str, value: Any) -> str:
    """Why a filter's *compiled* parameters cannot be bound, or ``""``.

    The compiler converts some values before binding them -- a position
    written "100000000000000000000" becomes that integer, a sizing per cent is
    multiplied into basis points -- so the value as written can pass every
    check and the number the database receives still overflow it when the
    stat first runs.
    """
    from .analytics_query import _compile_filter  # noqa: PLC0415

    _fragments, params = _compile_filter(name, value, "%s", "sqlite")
    for param in params:
        problem = _non_finite_problem(name, param)
        if problem:
            return problem
    return ""


# Filter kinds whose value is a plain value or a list of them.
_VALUE_KINDS: Final = frozenset({"set", "scalar", "label", "flagset", "flagset_all", "flagset_none"})
# Filter kinds the Research browser edits as comma-separated text.
_TEXT_KINDS: Final = frozenset({"set", "scalar", "label", "flagset", "flagset_all", "flagset_none", "identity_set"})


def _row_text_problem(name: str, value: Any) -> str:
    """Why the Research filter row would not read this value back as written.

    The row is the one control a preset's text value goes through. It writes
    the value as one field -- a list joined with ", " -- and reads the whole
    field back: an empty field is *no filter at all*, ``true`` and ``false`` a
    condition, a field with a comma a list of words, and digits alone a
    number. So the field is checked whole, as the row reads it: ``"001"``
    alone comes back as the number 1, but ``["007", "Hero"]`` comes back as it
    went in, while ``[1, 2]`` comes back as the words ``["1", "2"]``.
    """
    from .research_browser import text_value  # noqa: PLC0415 - Research is optional for a stats-only pack

    items = list(value) if isinstance(value, (list, tuple)) else [value]
    # Exactly what _FilterRow.set_value writes into the field.
    back = text_value(", ".join(str(item) for item in items))
    if (back if isinstance(back, list) else [back]) == items:
        return ""  # a one-item list and its item are the same filter to the engine
    if back is None:
        return f"filter {name!r} in a preset needs a word: the filter row reads an empty one as no filter"
    return f"filter {name!r} in a preset takes values the filter row reads back as written, not {value!r} (read back as {back!r})"


def _research_round_trip_problem(name: str, value: Any, kind: str) -> str:
    """Why a preset value would not survive Research's filter controls, or ``""``.

    A preset is loaded into those controls and read back before it runs. A
    range control takes ``[low, high]`` (a {min, max} mapping leaves it at its
    defaults, and a pair with neither bound is read back as no filter at all);
    a text control joins values with commas and splits them again, so only
    words and whole numbers come back as they went in -- a pair such as
    ["PokerStars", "Hero"] must be written "PokerStars:Hero".
    """
    if kind in ("range", "range_pct"):
        if not (isinstance(value, (list, tuple)) and len(value) == 2):
            return f"filter {name!r} must be written [low, high] in a preset, not {value!r}"
        return _range_control_problem(name, value)
    if kind not in _TEXT_KINDS:
        return ""
    if kind == "flagset_none" and value is True:
        # The engine's own form for "no flag at all": the row writes "True"
        # and reads it back as True, so it survives the round trip.
        return ""
    items = value if isinstance(value, (list, tuple)) else [value]
    if not items:
        # The engine reads [] as "none of these" and matches no row, but the
        # row writes it as an empty field and reads that back as no filter:
        # the preset would run over everything instead of nothing.
        return f"filter {name!r} in a preset needs at least one value; the filter row reads [] as no filter"
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            return f"filter {name!r} in a preset takes words or whole numbers, not {item!r}"
    return _row_text_problem(name, value)


def _range_control_problem(name: str, bounds: Iterable[Any]) -> str:
    """Why a preset range would be rounded or clamped by its control, or ``""``.

    The spin boxes span RANGE_CONTROL_MIN..MAX to RANGE_CONTROL_DECIMALS places,
    the minimum reading back as "no bound": [10.001, 20] would come back as
    [10.0, 20] and 20,000,000 as 10,000,000, running another query than the
    pack declares.
    """
    from .research_browser import RANGE_CONTROL_DECIMALS, RANGE_CONTROL_MAX, RANGE_CONTROL_MIN  # noqa: PLC0415

    for bound in bounds:
        if bound is None or isinstance(bound, bool) or not isinstance(bound, (int, float)):
            continue  # an open end, or a value the other checks refuse
        if not RANGE_CONTROL_MIN < bound <= RANGE_CONTROL_MAX:
            return f"filter {name!r} bound {bound!r} is outside what Research can show ({RANGE_CONTROL_MIN}, {RANGE_CONTROL_MAX}]"
        if round(bound, RANGE_CONTROL_DECIMALS) != bound:
            return f"filter {name!r} bound {bound!r} has more than {RANGE_CONTROL_DECIMALS} decimals, which Research rounds"
    return ""


def _non_finite_problem(name: str, value: Any) -> str:
    """Why a numeric filter value is not a number a query can compare, or ``""``.

    JSON has no NaN or Infinity, but Python's parser reads both constants as
    floats, so a hand-written file can carry one. Bound as a parameter it
    matches nothing at all on SQLite -- the stat then reports an empty
    population -- and a stricter backend refuses the query outright.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return f"filter {name!r} needs a finite number, not {value!r}"
    # 10**100 is a valid JSON number, and binding it fails in the database
    # ("Python int too large to convert to SQLite INTEGER") only when it runs.
    if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) > MAX_FILTER_NUMBER:
        return f"filter {name!r} holds a number too large for the database, {value!r}"
    return ""


def _value_filter_problem(name: str, value: Any, *, kind: str) -> str:
    """Why a set-valued filter's value is not one the query can compare, or ``""``.

    A mapping (other than is_null) compiles as one bound parameter the database
    cannot compare -- or, for a label, is stringified into its LIKE pattern and
    matches nothing -- so only values, or a list of them, are taken, and each of
    those has to be a number the query can actually use. A boolean is not one:
    the driver binds True as the integer 1, so ``{"hand_id": true}`` would
    quietly select hand 1 instead of refusing a filter the author mis-typed.
    ``flagset_none`` is the exception, because ``True`` is its own form there --
    the compiler reads it as "no flag at all".
    """
    values = value if isinstance(value, (list, tuple)) else [value]
    if any(isinstance(item, (Mapping, list, tuple)) or item is None for item in values):
        return f"filter {name!r} takes a value or a list of values, not {value!r}"
    for item in values:
        if isinstance(item, bool) and not (kind == "flagset_none" and value is True):
            return f"filter {name!r} takes a word or a number, not the boolean {item!r}"
        problem = _non_finite_problem(name, item)
        if problem:
            return problem
    return ""


def _one_filter_problem(name: str, value: Any, kind: str, *, preset: bool) -> str:
    if isinstance(value, Mapping) and set(value) == {"is_null"}:
        # The compiler takes this structured form for any filter, first. A
        # Research filter row cannot hold it, so a preset would turn it into
        # the text "{'is_null': False}" and compare against that.
        if preset:
            return f"filter {name!r} cannot use is_null in a preset; Research cannot show it"
        if not isinstance(value["is_null"], bool):
            return f"filter {name!r} needs is_null to be true or false, not {value['is_null']!r}"
        return ""
    if kind in ("bool", "hero", "null_check") and not isinstance(value, bool):
        return f"filter {name!r} needs true or false, not {value!r}"
    if kind in _VALUE_KINDS:
        return _value_filter_problem(name, value, kind=kind)
    if kind in ("range_low", "range_high"):
        if preset:
            return f"filter {name!r} is chosen in Research, not stored in a preset; list it under variables"
        # One bound, bound as it comes: a list would reach the database driver.
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return f"filter {name!r} takes a single date or number, not {value!r}"
        return _non_finite_problem(name, value) or _one_sided_problem(name, value)
    if kind == "identity_set":
        return _identity_problem(name, value)
    return _range_problem(name, value) if kind in ("range", "range_pct") else ""


def _one_sided_problem(name: str, value: Any) -> str:
    """Why a one-sided bound is not the kind its column holds, or ``""``.

    The bound is compared as it comes: "oops" against a hand id, or
    "not-a-date" against a start time, matches nothing on SQLite -- an empty
    population rather than an error -- and a stricter backend refuses the
    comparison when the stat first runs.
    """
    if name in _DATE_FILTERS:
        if isinstance(value, str) and _DATE_BOUND.fullmatch(value):
            try:
                datetime.fromisoformat(value)
            except ValueError:
                pass  # the right shape, not a real date (2026-13-45)
            else:
                return ""
        return f"filter {name!r} takes a date written 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM[:SS]', not {value!r}"
    if not isinstance(value, int):
        return f"filter {name!r} takes a whole hand id, not {value!r}"
    return ""


def _identity_problem(name: str, value: Any) -> str:
    """Why an identity filter would not name real players, or ``""``.

    The compiler takes {site: alias}, "Site:alias" or [site, alias] and turns
    every part into text, so a list or an object where a name belongs would
    be compared as "['Hero', 'Villain']" and match nobody.
    """
    if isinstance(value, Mapping):
        pairs: list[Any] = list(value.items())
    else:
        entries = value if isinstance(value, (list, tuple)) else [value]
        pairs = []
        for entry in entries:
            if isinstance(entry, str):
                continue  # "Site:alias": the compiler checks its shape
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                return f"filter {name!r} takes 'Site:alias' or [site, alias] identities, not {entry!r}"
            pairs.append(tuple(entry))
    for site, alias in pairs:
        if not all(isinstance(part, str) and part.strip() for part in (site, alias)):
            return f"filter {name!r} needs a site and an alias as plain text, not {site!r}: {alias!r}"
    return ""


def _range_problem(name: str, value: Any) -> str:
    if isinstance(value, Mapping):
        unknown = sorted(set(value) - {"min", "max"})
        if unknown or value.get("min") is None and value.get("max") is None:
            return f"range filter {name!r} takes min and/or max, not {dict(value)!r}"
        bounds: Any = (value.get("min"), value.get("max"))
    else:
        bounds = value
    if not isinstance(bounds, (list, tuple)):
        return ""  # the compiler reports the shape
    return _bounds_problem(name, bounds)


def _bounds_problem(name: str, bounds: Iterable[Any]) -> str:
    bounds = list(bounds)
    for bound in bounds:
        if bound is None:
            continue
        if isinstance(bound, bool) or not isinstance(bound, (int, float)):
            return f"range filter {name!r} needs numbers for its bounds, not {bound!r}"
        if isinstance(bound, float) and not math.isfinite(bound):
            return f"range filter {name!r} needs numbers for its bounds, not {bound!r}"
        problem = _non_finite_problem(name, bound)
        if problem:
            return problem
    if len(bounds) != 2:
        return ""  # the compiler reports the shape
    low, high = bounds
    # [null, null] compiles to no predicate at all -- the stat measures every
    # hand -- and [20, 10] to two that exclude each other, so it never has data.
    if low is None and high is None:
        return f"range filter {name!r} needs at least one bound, not {bounds!r}"
    if low is not None and high is not None and low > high:
        return f"range filter {name!r} has its low bound above its high one, {bounds!r}"
    return ""


def _preset_compile_error(preset: Any) -> str:
    """Why the engine cannot run a preset's query, or ``""``.

    The preset validator checks names; compiling checks the values too (a
    range with three bounds, an unknown position), which is what would
    otherwise break the Research Browser only when the preset is chosen.
    """
    from .analytics_query import Query, compile_query  # noqa: PLC0415

    try:
        # Only the filters go through Research's controls; the numerator is
        # held as it is and run as it is, so it takes any shape the engine does.
        problem = _filter_value_problem(preset.filters, preset=True) or _filter_value_problem(preset.numerator)
        if problem:
            return problem
        compile_query(
            Query(
                metric=preset.metric,
                filters=dict(preset.filters),
                numerator=dict(preset.numerator),
                group_by=tuple(preset.group_by),
            ),
        )
    except (ArithmeticError, TypeError, ValueError) as exc:
        # A 400-digit bound overflows float(): still just a bad value.
        return str(exc)
    return ""


# ---------------------------------------------------------------------------
# Installing, listing and managing.
# ---------------------------------------------------------------------------


def _builtin_names() -> set[str]:
    registry = definitions.DefinitionRegistry()
    registry.load_directory(definitions.default_definitions_dir())
    return set(registry.names()) | set(registry.fragments)


def _collisions(pack: StatPack, root: Path) -> list[str]:
    """Names this pack would take from a built-in or another installed pack."""
    problems: list[str] = []
    builtin = _builtin_names()
    ours = {definition.name for definition in pack.definitions} | set(pack.fragments)
    for name in sorted(ours & builtin):
        problems.append(f"{name!r} is a built-in name; a pack cannot replace it")
    for other in _installed(root):
        if other.id == pack.id:
            continue
        theirs = {definition.name for definition in other.definitions} | set(other.fragments)
        theirs |= {preset.id for preset in other.presets}
        mine = ours | {preset.id for preset in pack.presets}
        for name in sorted(mine & theirs):
            problems.append(f"{name!r} is already defined by installed pack {other.id!r}")
    return problems


def install_pack(
    source: str | Path,
    packs_dir: str | Path | None = None,
    *,
    replace: bool = False,
    fpdb_version: str | None = None,
) -> StatPack:
    """Validate ``source`` and copy it into the user pack directory.

    Nothing is written unless the whole pack is valid and collides with
    nothing. Reinstalling the same pack id needs ``replace=True``.
    """
    root = _root(packs_dir)
    pack = read_pack(source, fpdb_version=fpdb_version)
    target = root / pack.id
    # A pack whose earlier replacement was interrupted is put back first, so
    # the "already installed" check sees it and replace=False still protects it.
    if root.is_dir():
        _recover_interrupted_replacements(root)
    if target.exists() and not replace:
        raise PackError([f"pack {pack.id!r} is already installed; uninstall it or replace it"], pack.id)
    fresh = not target.exists()
    problems = _collisions(pack, root)
    if problems:
        raise PackError(problems, pack.id)
    _write_pack(pack, root, target)
    if fresh:
        _forget_disabled(root, pack.id)
    return pack


def _write_pack(pack: StatPack, root: Path, target: Path) -> None:
    """Write ``pack`` beside ``target``, then swap it in.

    A failure half-way leaves the previous install (or nothing), never a pack
    with half its files; the previous install is moved aside, not deleted,
    until the new one is in place, and restored if the swap fails.
    """
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{pack.id}.", dir=root))
    backup: Path | None = None
    try:
        for name, data in pack.files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if target.exists():
            backup = root / f".{pack.id}.previous"
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
        staging.rename(target)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and backup.exists() and not target.exists():
            backup.rename(target)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


def _forget_disabled(root: Path, pack_id: str) -> None:
    """Drop a stale disabled flag left by an uninstall that could not save it.

    A replacement keeps the user's choice; a fresh install of the same id must
    not inherit the flag of a pack that was removed.
    """
    state = _read_state(root)
    if pack_id not in state.get("disabled", []):
        return
    state["disabled"] = [name for name in state["disabled"] if name != pack_id]
    try:
        _write_state(root, state)
    except OSError as exc:
        log.warning("Installed %s but could not clear its stale disabled flag: %s", pack_id, exc)


def uninstall_pack(pack_id: str, packs_dir: str | Path | None = None) -> None:
    """Remove an installed pack -- valid or not -- and forget its enabled state.

    ``pack_id`` is the pack's folder name, which is what the manager lists for
    an invalid pack too: a hand-edited folder whose manifest names another pack
    must still be removable, and only that folder may be removed.
    """
    root = _root(packs_dir)
    target = _installed_folder(root, pack_id)
    shutil.rmtree(target)
    # The pack is gone; forgetting its disabled flag is housekeeping. Done the
    # other way round, a removal that then failed would re-enable the pack, and
    # a state file that cannot be written must not report a done uninstall as
    # failed. A leftover entry names no installed pack and is harmless.
    state = _read_state(root)
    state["disabled"] = [name for name in state.get("disabled", []) if name != pack_id]
    try:
        _write_state(root, state)
    except OSError as exc:
        log.warning("Uninstalled %s but could not update %s: %s", pack_id, STATE_NAME, exc)


def set_enabled(pack_id: str, enabled: bool, packs_dir: str | Path | None = None) -> None:
    """Switch an installed pack on or off without uninstalling it."""
    root = _root(packs_dir)
    _pack_dir(root, pack_id)
    state = _read_state(root)
    disabled = [name for name in state.get("disabled", []) if name != pack_id]
    if not enabled:
        disabled.append(pack_id)
    state["disabled"] = sorted(disabled)
    _write_state(root, state)


def _installed_folder(root: Path, folder: str) -> Path:
    """A direct, non-hidden folder of the pack directory, whatever it holds."""
    if not isinstance(folder, str) or not folder or folder.startswith(".") or folder != Path(folder).name:
        raise PackError([f"{folder!r} is not an installed pack folder"])
    target = root / folder
    if not target.is_dir() or target.is_symlink():
        raise PackError([f"pack {folder!r} is not installed"])
    return target


def _pack_dir(root: Path, pack_id: str) -> Path:
    if not isinstance(pack_id, str) or not _PACK_ID.fullmatch(pack_id):
        raise PackError([f"{pack_id!r} is not a pack id"])
    target = root / pack_id
    if not (target / MANIFEST_NAME).is_file():
        raise PackError([f"pack {pack_id!r} is not installed"])
    return target


def _installed(root: Path) -> list[StatPack]:
    """Every installed pack that still reads as valid, regardless of state."""
    packs = []
    for status in list_packs(root, include_builtin=False):
        if status.status == INVALID:
            continue
        try:
            packs.append(read_pack(root / status.id))
        except PackError:
            continue
    return packs


def _recover_interrupted_replacements(root: Path) -> None:
    """Put back a pack whose replacement stopped half-way.

    A replacement moves the old install to ``.<id>.previous`` before moving the
    new one in. If fpdb stopped between the two steps the pack folder is gone
    and only the backup is left: restore it. A backup beside a live pack is the
    leftover of a finished replacement and is removed.
    """
    for backup in root.glob(".*.previous"):
        if not backup.is_dir() or backup.is_symlink():
            continue
        target = root / backup.name[1 : -len(".previous")]
        try:
            if target.exists():
                shutil.rmtree(backup)
            else:
                backup.rename(target)
                log.warning("Restored stat pack %s after an interrupted replacement", target.name)
        except OSError as exc:
            log.warning("Could not recover %s: %s", backup, exc)


def list_packs(
    packs_dir: str | Path | None = None,
    *,
    include_builtin: bool = True,
    recover: bool = True,
) -> list[PackStatus]:
    """The manager's rows: the built-in library, then each installed pack.

    ``recover`` puts back a pack whose replacement was interrupted; only the
    manager and installation ask for it. The registries read packs in every
    process -- the HUD's included -- and a read that renamed folders could
    undo a replacement another process is in the middle of.
    """
    root = _root(packs_dir)
    rows: list[PackStatus] = []
    if include_builtin:
        registry = definitions.DefinitionRegistry()
        registry.load_directory(definitions.default_definitions_dir())
        rows.append(
            PackStatus(
                id="builtin",
                name="Built-in definitions",
                status=BUILTIN,
                definitions=tuple(registry.names()),
                path=str(definitions.default_definitions_dir()),
            ),
        )
    if not root.is_dir():
        return rows
    if recover:
        _recover_interrupted_replacements(root)
    disabled = set(_read_state(root).get("disabled", []))
    for directory in sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")):
        try:
            pack = read_pack(directory)
        except (PackError, OSError, ValueError, TypeError) as exc:
            messages = exc.messages if isinstance(exc, PackError) else [str(exc)]
            rows.append(PackStatus(id=directory.name, name=directory.name, status=INVALID, errors=tuple(messages), path=str(directory)))
            continue
        errors: tuple[str, ...] = ()
        status = DISABLED if pack.id in disabled else ENABLED
        if pack.id != directory.name:
            status, errors = INVALID, (f"folder {directory.name!r} holds pack {pack.id!r}",)
        rows.append(
            PackStatus(
                # The folder, not the manifest's claim: it is what a row acts on.
                id=directory.name,
                name=pack.name,
                status=status,
                definitions=tuple(definition.name for definition in pack.definitions),
                errors=errors,
                author=pack.author,
                description=pack.description,
                pack_version=pack.pack_version,
                path=str(directory),
            ),
        )
    return rows


def enabled_packs(packs_dir: str | Path | None = None) -> list[StatPack]:
    """The installed packs the registries should read: valid and enabled.

    A pack that has become invalid (hand-edited, or made for a newer fpdb) is
    skipped with a warning instead of taking the whole registry down.
    """
    root = _root(packs_dir)
    if not root.is_dir():
        return []
    builtin = _builtin_names()
    packs: list[StatPack] = []
    taken: set[str] = set(builtin)
    for status in list_packs(root, include_builtin=False, recover=False):
        if status.status != ENABLED:
            if status.status == INVALID:
                log.warning("Stat pack %s not loaded: %s", status.id, "; ".join(status.errors))
            continue
        try:
            pack = read_pack(root / status.id)
        except PackError as exc:  # pragma: no cover - listed as valid a moment ago
            log.warning("Stat pack %s not loaded: %s", status.id, exc)
            continue
        names = {definition.name for definition in pack.definitions} | set(pack.fragments)
        names |= {preset.id for preset in pack.presets}
        clash = names & taken
        if clash:
            # Installs refuse this; a folder copied in by hand could still try it.
            log.warning("Stat pack %s not loaded: it redefines %s", pack.id, sorted(clash))
            continue
        taken |= names
        packs.append(pack)
    return packs


def export_pack(pack_id: str, destination: str | Path, packs_dir: str | Path | None = None) -> Path:
    """Write an installed pack as a ``.fpdbstats`` archive another fpdb can install.

    The archive is deterministic -- sorted entries, fixed timestamps and
    permissions -- so exporting the same pack twice gives the same bytes.
    """
    root = _root(packs_dir)
    pack = read_pack(_pack_dir(root, pack_id))
    target = Path(destination)
    if target.is_dir():
        target = target / f"{pack.id}{PACK_SUFFIX}"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(pack.files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, pack.files[name])
    return target


# ---------------------------------------------------------------------------
# What the registries read.
# ---------------------------------------------------------------------------


def installed_definitions(packs_dir: str | Path | None = None) -> tuple[list[StatDefinition], dict[str, Any]]:
    """The definitions and fragments of every enabled pack."""
    stats: list[StatDefinition] = []
    fragments: dict[str, Any] = {}
    for pack in enabled_packs(packs_dir):
        stats.extend(pack.definitions)
        fragments.update(pack.fragments)
    return stats, fragments


def installed_presets(packs_dir: str | Path | None = None) -> tuple[Any, ...]:
    """The Research presets of every enabled pack."""
    return tuple(preset for pack in enabled_packs(packs_dir) for preset in pack.presets)


def pack_of(definition: StatDefinition) -> str:
    """The pack a definition came from, or ``""`` for a built-in."""
    source = definition.source or ""
    if not source.startswith("pack:"):
        return ""
    return source[len("pack:") :].split("/", 1)[0]


__all__ = [
    "BUILTIN",
    "DISABLED",
    "ENABLED",
    "INVALID",
    "MANIFEST_NAME",
    "PACK_SCHEMA",
    "PACK_SCHEMA_VERSION",
    "PACK_SUFFIX",
    "PackError",
    "PackStatus",
    "StatPack",
    "enabled_packs",
    "export_pack",
    "install_pack",
    "installed_definitions",
    "installed_presets",
    "list_packs",
    "pack_of",
    "read_pack",
    "set_enabled",
    "uninstall_pack",
    "user_packs_dir",
]
