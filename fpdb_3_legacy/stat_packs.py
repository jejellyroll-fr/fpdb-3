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
import os
import re
import shutil
import tempfile
import unicodedata
import zipfile
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
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
_WINDOWS_FORBIDDEN: Final = re.compile(r'[<>:"|?*\x00-\x1f]')
_WINDOWS_RESERVED: Final = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))},
)
# Generous for data, small enough that an archive cannot fill the disk.
MAX_ARCHIVE_FILES: Final = 200
MAX_ARCHIVE_BYTES: Final = 5 * 1024 * 1024
# More decimal places than any stat can mean; a pack cannot ask for more.
MAX_PRECISION: Final = 10
# JSON compresses well, but not a thousandfold: beyond this it is a zip bomb.
MAX_COMPRESSION_RATIO: Final = 200


class PackError(ValueError):
    """A pack that cannot be installed or loaded, with every reason found."""

    def __init__(self, messages: Iterable[str], source: str = "") -> None:
        self.messages = list(messages) or ["invalid pack"]
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
    """
    for part in path.parts:
        if part != part.rstrip(". "):
            return "has a name ending in a dot or a space"
        if _WINDOWS_FORBIDDEN.search(part):
            return 'uses a character Windows does not allow (<>:"|?* or a control character)'
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
            return f"uses the reserved Windows name {part.split('.', 1)[0]!r}"
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
    if len(listed) > MAX_ARCHIVE_FILES:
        raise PackError([f"the manifest lists {len(listed)} files; at most {MAX_ARCHIVE_FILES}"], str(source))
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
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise PackError([f"archive entry {info.filename!r} is compressed suspiciously well"], source)
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
    # An archive made by zipping the pack folder has one top-level directory.
    if MANIFEST_NAME not in files:
        tops = {name.split("/", 1)[0] for name in files}
        if len(tops) == 1:
            prefix = f"{tops.pop()}/"
            files = {name[len(prefix) :]: data for name, data in files.items() if name.startswith(prefix)}
    return files


def _read_archive_entries(source: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total = 0
    with zipfile.ZipFile(source) as archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        if len(entries) > MAX_ARCHIVE_FILES:
            raise PackError([f"archive holds {len(entries)} files; at most {MAX_ARCHIVE_FILES}"], str(source))
        for info in entries:
            name = info.filename
            # The same containment rule as the manifest's listed paths, applied
            # to every entry: an archive cannot smuggle a path out of the pack.
            if name.startswith("/") or "\\" in name or ".." in PurePosixPath(name).parts:
                raise PackError([f"archive entry {name!r} escapes the pack"], str(source))
            data = _read_entry(archive, info, MAX_ARCHIVE_BYTES - total, str(source))
            total += len(data)
            files[PurePosixPath(name).as_posix()] = data
    return files


def _parse_data(name: str, data: bytes, source: str) -> Any:
    """A data file's content, with every way it can be unreadable as a PackError."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackError([f"{name} is not UTF-8 text: {exc}"], source) from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        # JSONDecodeError, and the plain ValueError of an integer longer than
        # Python's int-string limit: either way the file cannot be read.
        raise PackError([f"{name} is not valid JSON: {exc}"], source) from exc
    except RecursionError as exc:
        # Valid JSON nested deeper than the parser can follow: still refused.
        raise PackError([f"{name} is nested too deeply to read"], source) from exc


def _version_tuple(version: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", version)
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
    return _portable_name_problem(PurePosixPath(pack_id))


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
    if minimum and _version_tuple(minimum) > _version_tuple(running):
        errors.append(f"needs fpdb {minimum} or newer (this is {running})")

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

    prefix = f"{pack_id}."
    fragments = _read_fragments(manifest.get("fragments", {}), prefix, errors)
    library = {**definitions.FILTER_FRAGMENTS, **fragments}
    stats = _read_definitions(manifest.get("definitions", []), files, prefix, library, pack_id, label, errors)
    presets = _read_presets(manifest.get("presets", []), files, prefix, label, errors)
    if not stats and not presets and not errors:
        errors.append("a pack must add at least one definition or preset")
    if errors:
        raise PackError(errors, label)
    listed = {MANIFEST_NAME, *manifest.get("definitions", []), *manifest.get("presets", [])}
    folded: dict[str, str] = {}
    for name in sorted(listed):
        # Windows and macOS file systems ignore case, and macOS also Unicode
        # normalization ("é" as one code point or two): names that differ only
        # that way would be written to one file, and the install would lose one.
        key = unicodedata.normalize("NFC", name).casefold()
        if key in folded:
            errors.append(f"files {folded[key]!r} and {name!r} name the same file on some systems")
        folded[key] = name
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
    fragments: dict[str, dict[str, Any]] = {}
    for name, filters in raw.items():
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
        try:
            entries = _entries_in(document, name)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for entry in entries:
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
        problem = _filter_value_problem({**query.filters, **query.numerator})
        if problem:
            raise ValueError(problem)
    except (ArithmeticError, AttributeError, TypeError, ValueError) as exc:
        # A malformed value ({"bet_sizing_pct": [{}, 50]}) fails as a TypeError
        # deep in the compiler; it is still just a bad value in the pack.
        raise ValueError(f"{name}: stat {definition.name!r}: {exc}") from exc
    return definition


def _entries_in(document: Any, name: str) -> list[Mapping[str, Any]]:
    """The raw definitions of one file, after the shipped library's file checks."""
    return definitions.definition_entries(document, name)


def _read_presets(listed: Any, files: Mapping[str, bytes], prefix: str, label: str, errors: list[str]) -> list[Any]:
    from . import research_presets  # noqa: PLC0415 - Research is optional for a stats-only pack

    presets: list[Any] = []
    seen: set[str] = set()
    for name, raw in _listed_documents(listed, files, "presets", label, errors):
        try:
            pack = research_presets.validate_preset_pack(raw, name)
        except (ArithmeticError, AttributeError, TypeError, ValueError) as exc:
            # The shipped validator trusts shipped data's shapes; a pack's data
            # is not shipped, so a wrong shape is its error, not a crash.
            errors.append(f"{name}: {exc}")
            continue
        for preset in pack.presets:
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
    if kind in ("set", "scalar"):
        # A mapping (other than is_null) compiles as one bound parameter the
        # database cannot compare: only values, or a list of them.
        values = value if isinstance(value, (list, tuple)) else [value]
        if any(isinstance(item, (Mapping, list, tuple)) or item is None for item in values):
            return f"filter {name!r} takes a value or a list of values, not {value!r}"
        return ""
    if kind in ("range_low", "range_high"):
        if preset:
            return f"filter {name!r} is chosen in Research, not stored in a preset; list it under variables"
        # One bound, bound as it comes: a list would reach the database driver.
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return f"filter {name!r} takes a single date or number, not {value!r}"
        return ""
    return _range_problem(name, value) if kind == "range" else ""


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
    import math  # noqa: PLC0415

    for bound in bounds:
        if bound is None:
            continue
        if isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound):
            return f"range filter {name!r} needs numbers for its bounds, not {bound!r}"
    return ""


def _preset_compile_error(preset: Any) -> str:
    """Why the engine cannot run a preset's query, or ``""``.

    The preset validator checks names; compiling checks the values too (a
    range with three bounds, an unknown position), which is what would
    otherwise break the Research Browser only when the preset is chosen.
    """
    from .analytics_query import Query, compile_query  # noqa: PLC0415

    try:
        problem = _filter_value_problem({**preset.filters, **preset.numerator}, preset=True)
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


def list_packs(packs_dir: str | Path | None = None, *, include_builtin: bool = True) -> list[PackStatus]:
    """The manager's rows: the built-in library, then each installed pack."""
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
    for status in list_packs(root, include_builtin=False):
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
