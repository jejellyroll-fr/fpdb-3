"""Stable fingerprints for file-by-file tournament-summary regression tests.

Summaries cannot be parsed the way hands are: a TourneySummary subclass does
its work in ``__init__``, which also opens a database. The established way
round it -- already used by the per-site summary tests -- is to patch that
``__init__`` out, seed the attributes it would have set, and call
``parseSummary`` directly. This module holds that scaffolding once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# What TourneySummary.__init__ sets before a converter starts parsing. Values a
# converter leaves untouched stay at these defaults, so they double as the
# "not stated by this summary" marker in a snapshot.
INIT_DEFAULTS: dict[str, Any] = {
    "tourneyName": None, "tourneyTypeId": None, "tourneyId": None,
    "startTime": None, "endTime": None, "tourNo": None, "currency": None,
    "buyinCurrency": None, "buyin": 0, "fee": 0, "hero": None, "maxseats": 0,
    "entries": 0, "speed": "Normal", "prizepool": 0, "buyInChips": 0, "mixed": None,
    "isRebuy": False, "isAddOn": False, "isKO": False, "isProgressive": False,
    "isMatrix": False, "isShootout": False, "isFast": False, "rebuyChips": None,
    "addOnChips": None, "rebuyCost": 0, "addOnCost": 0, "totalRebuyCount": None,
    "totalAddOnCount": None, "koBounty": 0, "isSng": False, "isStep": False,
    "stepNo": 0, "isChance": False, "chanceCount": 0, "isMultiEntry": False,
    "isReEntry": False, "isNewToGame": False, "isHomeGame": False, "isSplit": False,
    "isTime": False, "timeAmt": 0, "isSatellite": False, "isDoubleOrNothing": False,
    "isCashOut": False, "isOnDemand": False, "isFlighted": False, "isGuarantee": False,
    "guaranteeAmt": 0, "added": None, "addedCurrency": None, "isLottery": False,
    "comment": None,
}

# The tournament facts whose drift changes what an imported summary means.
FINGERPRINT_FIELDS = (
    "tourNo", "tourneyName", "currency", "buyinCurrency", "buyin", "fee",
    "prizepool", "entries", "maxseats", "buyInChips", "speed", "mixed",
    "koBounty", "rebuyCost", "addOnCost", "guaranteeAmt", "added", "addedCurrency",
    "isRebuy", "isAddOn", "isKO", "isProgressive", "isMatrix", "isShootout",
    "isFast", "isSng", "isStep", "isSatellite", "isDoubleOrNothing", "isGuarantee",
    "isMultiEntry", "isReEntry", "isFlighted", "isOnDemand", "isLottery",
    "startTime", "endTime",
)


def clean_money(value: str) -> str:
    """Strip grouping and currency marks, as TourneySummary.clearMoneyString does."""
    return value.replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()


def read_text(path: Path) -> str:
    """Read a summary the way TourneySummary.readFile does.

    A UTF-16 byte-order mark is unambiguous and must be honoured first: half of
    the Full Tilt corpus is UTF-16-LE, and falling through to cp1252 decodes it
    into mojibake that no header regex can match.
    """
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="ignore")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


HHTYPE_BY_SUFFIX = {".xls": "xls", ".xlsx": "xls", ".htm": "html", ".html": "html"}


def hhtype_for(path: Path) -> str:
    """Which parseSummary branch a file takes, as the importer decides it."""
    return HHTYPE_BY_SUFFIX.get(path.suffix.lower(), "summary")


def make_summary(summary_class: Any, text: str, sitename: str, site_id: int, hhtype: str = "summary") -> Any:
    """Build a parseable summary without touching a database."""
    config, db = MagicMock(), MagicMock()
    with patch("fpdb_3_legacy.TourneySummary.TourneySummary.__init__", return_value=None):
        summary = summary_class(config=config, db=db, summaryText=text, builtFrom="file")
    summary.config = config
    summary.db = db
    summary.summaryText = text
    summary.hhtype = hhtype
    summary.sitename = sitename
    summary.siteName = sitename
    summary.siteId = site_id
    summary.in_path = "none"
    # WinningSummary reads a page header alongside each tournament chunk.
    summary.header = ""
    for attr, value in INIT_DEFAULTS.items():
        setattr(summary, attr, value)
    # A fresh dict per summary: converters write into it, and a shared default
    # would leak one file's game type into the next.
    summary.gametype = {}
    summary.addPlayer = MagicMock()
    summary.clearMoneyString = MagicMock(side_effect=clean_money)
    return summary


def _stable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _stable(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def summary_fingerprint(summary: Any) -> dict:
    """The tournament facts plus every player the converter registered."""
    fields = {name: _stable(getattr(summary, name, None)) for name in FINGERPRINT_FIELDS}
    players = [
        {
            "rank": _stable(call.args[0] if call.args else call.kwargs.get("rank")),
            "name": _stable(call.args[1] if len(call.args) > 1 else call.kwargs.get("name")),
            "winnings": _stable(call.args[2] if len(call.args) > 2 else call.kwargs.get("winnings")),
            "currency": _stable(call.args[3] if len(call.args) > 3 else call.kwargs.get("winningsCurrency")),
            "rebuys": _stable(call.args[4] if len(call.args) > 4 else call.kwargs.get("rebuyCount")),
            "addons": _stable(call.args[5] if len(call.args) > 5 else call.kwargs.get("addOnCount")),
            "ko": _stable(call.args[6] if len(call.args) > 6 else call.kwargs.get("koCount")),
        }
        for call in summary.addPlayer.call_args_list
    ]
    return {"tournament": fields, "players": players}
