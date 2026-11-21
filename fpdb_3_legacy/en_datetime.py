"""Parse English hand-history dates whatever the process locale is.

``datetime.strptime`` reads ``%a``, ``%A``, ``%b``, ``%B`` and ``%p`` through
the process's ``LC_TIME``. fpdb never sets it, but ``QApplication`` calls
``setlocale(LC_ALL, "")`` on Unix, so in the GUI a French user's process
expects ``octobre`` and an empty AM/PM marker, and every English date fails.
Toggling ``locale.setlocale`` around the call is not an option: it is
process-wide and the import runs in a worker thread.

``parse_en_datetime`` takes the same format string as ``strptime`` but reads
month names, day names and AM/PM from fixed English tables, so its result does
not depend on the locale.
"""

from __future__ import annotations

import datetime
import functools
import re

_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# Every spelling a hand history uses -> month number. "Sept" shows up in some
# exports next to the three-letter "Sep".
_MONTH_NUMBERS = {name: i for i, name in enumerate(_MONTHS, start=1)}
_MONTH_NUMBERS.update({name[:3]: i for i, name in enumerate(_MONTHS, start=1)})
_MONTH_NUMBERS["sept"] = 9
_DAY_NAMES = set(_DAYS) | {name[:3] for name in _DAYS}


def _alternation(names: set[str] | dict[str, int]) -> str:
    # Longest first, so "June" is not cut to "Jun" and leave "e" unmatched.
    return "|".join(sorted(names, key=len, reverse=True))


_NUMERIC = {
    "Y": r"\d{4}",
    "y": r"\d{2}",
    "m": r"\d{1,2}",
    "d": r"\d{1,2}",
    "H": r"\d{1,2}",
    "I": r"\d{1,2}",
    "M": r"\d{1,2}",
    "S": r"\d{1,2}",
}
_NAMED = {
    "b": _alternation(_MONTH_NUMBERS),
    "B": _alternation(_MONTH_NUMBERS),
    "a": _alternation(_DAY_NAMES),
    "A": _alternation(_DAY_NAMES),
    "p": "am|pm",
}
# Directive -> regex group name (a and A share one, as do b and B).
_GROUP = {"b": "month_name", "B": "month_name", "a": "day_name", "A": "day_name"}


def _directive_regex(directive: str, fmt: str) -> tuple[str, str]:
    """Return (group name, regex body) for one strptime directive."""
    if directive in _NUMERIC:
        return directive, _NUMERIC[directive]
    if directive in _NAMED:
        return _GROUP.get(directive, directive), _NAMED[directive]
    msg = f"unsupported directive %{directive} in format {fmt!r}"
    raise ValueError(msg)


@functools.lru_cache(maxsize=64)
def _compile(fmt: str) -> re.Pattern[str]:
    parts: list[str] = []
    seen: set[str] = set()
    for literal, directive in _tokens(fmt):
        if directive is None:
            # As strptime does: whitespace in the format matches one or more
            # whitespace characters in the text.
            parts.append(r"\s+" if literal.isspace() else re.escape(literal))
            continue
        group, body = _directive_regex(directive, fmt)
        if group in seen:
            msg = f"directive %{directive} repeated in format {fmt!r}"
            raise ValueError(msg)
        seen.add(group)
        parts.append(f"(?P<{group}>{body})")
    return re.compile("".join(parts), re.IGNORECASE)


def _tokens(fmt: str) -> list[tuple[str, str | None]]:
    """Split a format into (literal, None) and ("", directive) tokens."""
    tokens: list[tuple[str, str | None]] = []
    for piece in re.finditer(r"%(.)|%$|\s+|[^%\s]", fmt):
        if piece.group(0) == "%":
            msg = f"stray % in format {fmt!r}"
            raise ValueError(msg)
        directive = piece.group(1)
        if directive == "%":
            tokens.append(("%", None))
        elif directive is not None:
            tokens.append(("", directive))
        else:
            tokens.append((piece.group(0), None))
    return tokens


def _year(fields: dict[str, str | None]) -> int:
    if (full := fields.get("Y")) is not None:
        return int(full)
    if (short_text := fields.get("y")) is not None:
        # strptime's pivot: 69-99 -> 1900s, 00-68 -> 2000s.
        short = int(short_text)
        return short + (1900 if short >= 69 else 2000)  # noqa: PLR2004
    return 1900


def _month(fields: dict[str, str | None]) -> int:
    if (number := fields.get("m")) is not None:
        return int(number)
    if (name := fields.get("month_name")) is not None:
        return _MONTH_NUMBERS[name.lower()]
    return 1


def _hour(fields: dict[str, str | None]) -> int:
    if (hour24 := fields.get("H")) is not None:
        return int(hour24)
    if (hour12 := fields.get("I")) is None:
        return 0
    hour = int(hour12)
    if not 1 <= hour <= 12:  # noqa: PLR2004
        msg = f"12-hour clock value {hour} out of range"
        raise ValueError(msg)
    # %p without %I is ignored, as in strptime; 12 AM is midnight, 12 PM noon.
    return hour % 12 + (12 if (fields.get("p") or "").lower() == "pm" else 0)


def parse_en_datetime(text: str, fmt: str) -> datetime.datetime:
    """Parse ``text`` with a ``strptime`` format, reading names in English.

    Supports ``%Y %y %m %d %H %I %M %S %b %B %a %A %p %%``. Month names are
    accepted in full or abbreviated form for both ``%b`` and ``%B``, day names
    likewise for ``%a`` and ``%A``, all case-insensitively. The day name is
    read but not checked against the date, as ``strptime`` does. The result is
    naive, like ``strptime``'s.

    Raises ``ValueError`` when the text does not match the format.
    """
    match = _compile(fmt).fullmatch(text)
    if match is None:
        msg = f"time data {text!r} does not match format {fmt!r}"
        raise ValueError(msg)
    fields = match.groupdict()
    try:
        return datetime.datetime(  # noqa: DTZ001 - naive, like strptime
            _year(fields),
            _month(fields),
            int(fields.get("d") or 1),
            _hour(fields),
            int(fields.get("M") or 0),
            int(fields.get("S") or 0),
        )
    except ValueError as exc:
        msg = f"time data {text!r} does not match format {fmt!r}: {exc}"
        raise ValueError(msg) from exc
