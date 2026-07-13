"""Compile fpdb's gettext catalogs from ``fpdb-<lang>.po`` to ``.mo`` on demand.

fpdb ships translations as flat ``locale/fpdb-<lang>.po`` files, but gettext
loads them from ``locale/<lang>/LC_MESSAGES/fpdb.mo``. The ``.mo`` are build
artifacts (git-ignored), so this module compiles them — with no external
dependency (no msgfmt binary, no babel/polib) — either from the CLI wrapper in
``tools/compile_translations.py`` or lazily at startup via :func:`ensure_compiled`.
"""

from __future__ import annotations

import array
import re
import struct
from pathlib import Path

DOMAIN = "fpdb"

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}
_LINE = re.compile(r'^\s*(msgid|msgstr|msgid_plural)\s+"(.*)"\s*$')
_CONT = re.compile(r'^\s*"(.*)"\s*$')


def _unescape(text: str) -> str:
    """Turn a .po quoted-string body into its real value."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            out.append(_ESCAPES.get(text[i + 1], text[i + 1]))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_po(path: Path) -> dict[str, str]:
    """Parse a .po file into a ``{msgid: msgstr}`` map (singular entries only)."""
    messages: dict[str, str] = {}
    key = val = None
    target = None  # which buffer continuation lines append to
    skip_plural = False

    def flush() -> None:
        # Skip entries with an empty translation (like GNU msgfmt) so gettext
        # falls back to the source string instead of returning "" — an empty
        # menu/label. The header entry (msgid "") has a non-empty msgstr carrying
        # the charset, so it is kept (required for UTF-8 decoding). Plurals ignored.
        if key is not None and val and not skip_plural:
            messages[key] = val

    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line.startswith("#") or not line.strip():
                continue
            match = _LINE.match(line)
            if match:
                kind, body = match.group(1), _unescape(match.group(2))
                if kind == "msgid":
                    flush()
                    key, val, target, skip_plural = body, None, "id", False
                elif kind == "msgid_plural":
                    skip_plural = True  # plural entries are ignored for now
                    target = None
                else:  # msgstr
                    val, target = body, "str"
                continue
            cont = _CONT.match(line)
            if cont and target == "id" and key is not None:
                key += _unescape(cont.group(1))
            elif cont and target == "str" and val is not None:
                val += _unescape(cont.group(1))
    flush()
    return messages


def generate_mo(messages: dict[str, str]) -> bytes:
    """Serialise ``messages`` into the little-endian gettext .mo binary format."""
    keys = sorted(messages.keys())
    offsets = []
    ids = strs = b""
    for key in keys:
        msgid = key.encode("utf-8")
        msgstr = messages[key].encode("utf-8")
        offsets.append((len(ids), len(msgid), len(strs), len(msgstr)))
        ids += msgid + b"\x00"
        strs += msgstr + b"\x00"

    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets: list[int] = []
    voffsets: list[int] = []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]

    output = struct.pack(
        "Iiiiiii",
        0x950412DE,  # magic
        0,  # version
        len(keys),  # number of entries
        7 * 4,  # start of key index
        7 * 4 + len(keys) * 8,  # start of value index
        0,
        0,  # size/offset of hash table (unused)
    )
    output += array.array("i", koffsets + voffsets).tobytes()
    output += ids
    output += strs
    return output


def available_locales(locale_dir: Path) -> list[str]:
    """Language codes with a ``fpdb-<lang>.po`` file in ``locale_dir``."""
    return sorted(p.stem[len(DOMAIN) + 1 :] for p in locale_dir.glob(f"{DOMAIN}-*.po"))


def compile_locale(locale_dir: Path, lang: str) -> Path:
    """Compile ``fpdb-<lang>.po`` -> ``<lang>/LC_MESSAGES/fpdb.mo``; return the .mo path."""
    po_path = locale_dir / f"{DOMAIN}-{lang}.po"
    mo_dir = locale_dir / lang / "LC_MESSAGES"
    mo_dir.mkdir(parents=True, exist_ok=True)
    mo_path = mo_dir / f"{DOMAIN}.mo"
    mo_path.write_bytes(generate_mo(parse_po(po_path)))
    return mo_path


def ensure_compiled(locale_dir: Path, langs: list[str] | None = None) -> list[str]:
    """Compile catalogs whose .mo is missing or older than its .po.

    Idempotent and cheap on repeat runs (an up-to-date .mo is skipped), so it is
    safe to call at startup. Returns the list of languages actually (re)compiled.
    Compilation failures are swallowed per-language: a broken catalog must never
    stop the app from launching.
    """
    locale_dir = Path(locale_dir)
    if not locale_dir.is_dir():
        return []
    # Rebuild when the .po changed OR when this compiler changed (so a fix to the
    # compilation itself invalidates .mo files produced by an older version).
    compiler_mtime = Path(__file__).stat().st_mtime
    targets = langs if langs is not None else available_locales(locale_dir)
    recompiled: list[str] = []
    for lang in targets:
        po_path = locale_dir / f"{DOMAIN}-{lang}.po"
        if not po_path.exists():
            continue
        mo_path = locale_dir / lang / "LC_MESSAGES" / f"{DOMAIN}.mo"
        source_mtime = max(po_path.stat().st_mtime, compiler_mtime)
        if mo_path.exists() and mo_path.stat().st_mtime >= source_mtime:
            continue  # already up to date
        try:
            compile_locale(locale_dir, lang)
            recompiled.append(lang)
        except Exception:  # noqa: BLE001, S112 - a bad catalog must not block startup
            continue
    return recompiled
