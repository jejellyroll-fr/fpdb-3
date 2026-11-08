"""Canonical models for HTTP-captured poker hands.

The capture layer keeps raw site payloads, but its normalized target should use
the same game taxonomy and street names as Hand.py.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class StreetProfile:
    """Street collections matching the attributes initialized by Hand classes."""

    all_streets: tuple[str, ...]
    action_streets: tuple[str, ...]
    hole_streets: tuple[str, ...]
    community_streets: tuple[str, ...] = ()
    discard_streets: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "allStreets": list(self.all_streets),
            "actionStreets": list(self.action_streets),
            "holeStreets": list(self.hole_streets),
            "communityStreets": list(self.community_streets),
            "discardStreets": list(self.discard_streets),
        }


HOLDEM_OMAHA_STREETS = StreetProfile(
    all_streets=("BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"),
    action_streets=("BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"),
    hole_streets=("PREFLOP",),
    community_streets=("FLOP", "TURN", "RIVER"),
    discard_streets=("PREFLOP",),
)

SINGLE_DRAW_STREETS = StreetProfile(
    all_streets=("BLINDSANTES", "DEAL", "DRAWONE"),
    action_streets=("BLINDSANTES", "DEAL", "DRAWONE"),
    hole_streets=("DEAL", "DRAWONE"),
    discard_streets=("DEAL", "DRAWONE"),
)

TRIPLE_DRAW_STREETS = StreetProfile(
    all_streets=("BLINDSANTES", "DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
    action_streets=("BLINDSANTES", "DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
    hole_streets=("DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
    discard_streets=("DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
)

DRAWMAHA_STREETS = StreetProfile(
    all_streets=("BLINDSANTES", "PREFLOP", "FLOP", "DRAWONE", "TURN", "RIVER"),
    action_streets=("BLINDSANTES", "PREFLOP", "FLOP", "DRAWONE", "TURN", "RIVER"),
    hole_streets=("PREFLOP", "DRAWONE"),
    community_streets=("FLOP", "TURN", "RIVER"),
    discard_streets=("DRAWONE",),
)

COURCHEVEL_STREETS = StreetProfile(
    all_streets=("BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"),
    action_streets=("BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"),
    hole_streets=("PREFLOP",),
    community_streets=("PREFLOP", "FLOP", "TURN", "RIVER"),
)

STUD_STREETS = StreetProfile(
    all_streets=("BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"),
    action_streets=("BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"),
    hole_streets=("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"),
    discard_streets=("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"),
)


@dataclass(frozen=True)
class CapturedGameDefinition:
    """Game metadata normalized to FPDB's Hand.gametype vocabulary."""

    label: str
    base: str
    category: str
    limit_type: str
    street_profile: StreetProfile
    mix: str = "none"
    fpdb_supported: bool = True
    aliases: tuple[str, ...] = ()

    def gametype(
        self,
        *,
        game_type: str = "ring",
        currency: str = "USD",
        small_blind: Decimal | int | str = 0,
        big_blind: Decimal | int | str = 0,
        ante: Decimal | int | str = 0,
        max_seats: int | None = None,
    ) -> dict[str, Any]:
        return {
            "type": game_type,
            "base": self.base,
            "category": self.category,
            "limitType": self.limit_type,
            "currency": currency,
            "sb": Decimal(str(small_blind)),
            "bb": Decimal(str(big_blind)),
            "ante": Decimal(str(ante)),
            "mix": self.mix,
            "maxSeats": max_seats,
        }

    def to_capture_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["street_profile"] = self.street_profile.to_dict()
        return data


UNKNOWN_GAME = CapturedGameDefinition(
    label="Unknown",
    base="unknown",
    category="unknown",
    limit_type="unknown",
    street_profile=HOLDEM_OMAHA_STREETS,
    fpdb_supported=False,
)

SWC_GAME_DEFINITIONS: dict[int, CapturedGameDefinition] = {
    0: CapturedGameDefinition("Hold'em", "hold", "holdem", "nl", HOLDEM_OMAHA_STREETS),
    1: CapturedGameDefinition("Omaha", "hold", "omahahi", "pl", HOLDEM_OMAHA_STREETS),
    2: CapturedGameDefinition("Omaha H/L", "hold", "omahahilo", "pl", HOLDEM_OMAHA_STREETS),
    3: CapturedGameDefinition("5 Card Omaha", "hold", "5_omahahi", "pl", HOLDEM_OMAHA_STREETS),
    4: CapturedGameDefinition(
        "5 Card Omaha H/L", "hold", "5_omahahi", "pl", HOLDEM_OMAHA_STREETS, fpdb_supported=False
    ),
    5: CapturedGameDefinition("6 Card Omaha", "hold", "6_omahahi", "pl", HOLDEM_OMAHA_STREETS),
    6: CapturedGameDefinition(
        "6 Card Omaha H/L", "hold", "6_omaha8", "pl", HOLDEM_OMAHA_STREETS
    ),
    10: CapturedGameDefinition("Stud", "stud", "studhi", "fl", STUD_STREETS),
    11: CapturedGameDefinition("Stud H/L", "stud", "studhilo", "fl", STUD_STREETS),
    12: CapturedGameDefinition("Razz", "stud", "razz", "fl", STUD_STREETS),
    20: CapturedGameDefinition("5 Card Draw", "draw", "fivedraw", "fl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    21: CapturedGameDefinition("2-7 Triple Draw", "draw", "27_3draw", "fl", TRIPLE_DRAW_STREETS),
    22: CapturedGameDefinition("2-7 Single Draw", "draw", "27_1draw", "nl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    23: CapturedGameDefinition("Badugi", "draw", "badugi", "fl", TRIPLE_DRAW_STREETS),
    24: CapturedGameDefinition("Badeucy", "draw", "badeucey", "fl", TRIPLE_DRAW_STREETS),
    25: CapturedGameDefinition("Badacey", "draw", "badacey", "fl", TRIPLE_DRAW_STREETS),
    30: CapturedGameDefinition("Short Deck", "hold", "holdem", "nl", HOLDEM_OMAHA_STREETS, fpdb_supported=False),
    50: CapturedGameDefinition("6 Card Omaha", "hold", "6_omahahi", "pl", HOLDEM_OMAHA_STREETS),
    70: CapturedGameDefinition("OFC", "ofc", "ofc", "pl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    72: CapturedGameDefinition("Hold'em", "hold", "holdem", "nl", HOLDEM_OMAHA_STREETS),
    73: CapturedGameDefinition("Turbo OFC", "ofc", "ofc", "pl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    74: CapturedGameDefinition("OFC/P", "ofc", "ofcp", "pl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    75: CapturedGameDefinition("OFC/P Progressive", "ofc", "ofcp", "pl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    76: CapturedGameDefinition("OFC/P 2-7", "ofc", "ofcp_27", "pl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    77: CapturedGameDefinition("OFC/P Variant", "ofc", "ofcp", "pl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    79: CapturedGameDefinition("Omaha", "hold", "omahahi", "pl", HOLDEM_OMAHA_STREETS),
    84: CapturedGameDefinition("OFC Variant", "ofc", "ofc", "pl", SINGLE_DRAW_STREETS, fpdb_supported=False),
    88: CapturedGameDefinition("5 Card Omaha", "hold", "5_omahahi", "pl", HOLDEM_OMAHA_STREETS),
}

# The public rules page names games, while Socket.IO game states identify them
# with numeric `gt` codes. Keep name-only aliases separate from that wire-code
# table: these titles can classify native table names and announced game labels
# without inventing numeric codes that have not been observed on the wire.
SWC_GAME_NAME_DEFINITIONS: dict[str, CapturedGameDefinition] = {
    # Chinese / OFC variants.
    "2 7 pineapple ofc": SWC_GAME_DEFINITIONS[76],
    "progressive pineapple ofc": SWC_GAME_DEFINITIONS[75],
    "pineapple ofc": SWC_GAME_DEFINITIONS[74],
    "open face chinese": SWC_GAME_DEFINITIONS[70],
    "open face chinese poker": SWC_GAME_DEFINITIONS[70],
    "chinese": SWC_GAME_DEFINITIONS[84],
    "chinese poker": SWC_GAME_DEFINITIONS[84],
    # Draw games already represented by a confirmed wire-code definition.
    "5 card draw": SWC_GAME_DEFINITIONS[20],
    "2 7 single draw": SWC_GAME_DEFINITIONS[22],
    "badacey": SWC_GAME_DEFINITIONS[25],
    "badeucy": SWC_GAME_DEFINITIONS[24],
    "badugi": SWC_GAME_DEFINITIONS[23],
    "2 7 triple draw": SWC_GAME_DEFINITIONS[21],
    # Drawmaha variants have no confirmed numeric `gt` values yet. They are
    # named and structurally described, but remain capture-only because the
    # importer cannot represent their Omaha + draw split pot faithfully.
    "drawmaha": CapturedGameDefinition(
        "Drawmaha", "draw", "drawmaha_high", "unknown", DRAWMAHA_STREETS, fpdb_supported=False
    ),
    "drawmaha sviten": CapturedGameDefinition(
        "Sviten Special", "draw", "sviten", "unknown", DRAWMAHA_STREETS, fpdb_supported=False
    ),
    "sviten special": CapturedGameDefinition(
        "Sviten Special", "draw", "sviten", "unknown", DRAWMAHA_STREETS, fpdb_supported=False
    ),
    "drawmaha 2 7": CapturedGameDefinition(
        "Drawmaha 2-7", "draw", "drawmaha", "unknown", DRAWMAHA_STREETS, fpdb_supported=False
    ),
    "drawmadugi": CapturedGameDefinition(
        "Drawmadugi", "draw", "drawmadugi", "unknown", DRAWMAHA_STREETS, fpdb_supported=False
    ),
    # Flop games with known FPDB categories. Courchevel and Big O remain
    # capture-only until their distinct dealing/street rules are verified.
    "6 card omaha": SWC_GAME_DEFINITIONS[50],
    "6 card omaha hi lo": SWC_GAME_DEFINITIONS[6],
    "courchevel hi lo": CapturedGameDefinition(
        "Courchevel Hi/Lo", "hold", "cour_hilo", "unknown", COURCHEVEL_STREETS, fpdb_supported=False
    ),
    "courchevel": CapturedGameDefinition(
        "Courchevel", "hold", "cour_hi", "unknown", COURCHEVEL_STREETS, fpdb_supported=False
    ),
    "big o": CapturedGameDefinition(
        "Big O", "hold", "5_omaha8", "unknown", HOLDEM_OMAHA_STREETS, fpdb_supported=False
    ),
    "5 card omaha": SWC_GAME_DEFINITIONS[88],
    "omaha hi lo": SWC_GAME_DEFINITIONS[2],
    "omaha h l": SWC_GAME_DEFINITIONS[2],
    "omaha": SWC_GAME_DEFINITIONS[79],
    "pineapple holdem": CapturedGameDefinition(
        "Pineapple Hold'em", "hold", "holdem", "unknown", HOLDEM_OMAHA_STREETS, fpdb_supported=False
    ),
    "short deck holdem": SWC_GAME_DEFINITIONS[30],
    "texas holdem": SWC_GAME_DEFINITIONS[72],
    "holdem": SWC_GAME_DEFINITIONS[72],
    # A mixed-game table is resolved per hand from the room's game-change
    # message; it is not a single hand category.
    "mixed games": CapturedGameDefinition(
        "Mixed Games", "unknown", "unknown", "unknown", HOLDEM_OMAHA_STREETS, fpdb_supported=False
    ),
    # Stud games.
    "razz": SWC_GAME_DEFINITIONS[12],
    "7 card stud hi lo": SWC_GAME_DEFINITIONS[11],
    "7 card stud": SWC_GAME_DEFINITIONS[10],
    "stud hi lo": SWC_GAME_DEFINITIONS[11],
    "stud h l": SWC_GAME_DEFINITIONS[11],
    "stud": SWC_GAME_DEFINITIONS[10],
}


def _normalize_swc_game_name(name: str) -> str:
    name = name.lower().replace("'", "").replace("’", "")
    normalized = " ".join(re.findall(r"[a-z0-9]+", name))
    if normalized.endswith(" poker"):
        normalized = normalized[:-6]
    return normalized


def swc_game_definition_by_name(name: str | None) -> CapturedGameDefinition:
    """Resolve a public/native SwC game label without guessing a numeric code."""
    if not name:
        return UNKNOWN_GAME
    normalized = _normalize_swc_game_name(name)

    # Mixed-game announcements use the room's wire labels, which are not all
    # spelled like the public rules catalogue (e.g. "OFC/P" and "6 Card Omaha
    # H/L"). Keep those confirmed labels ahead of broader public-name matches.
    wire_labels = {
        _normalize_swc_game_name(definition.label): definition for definition in SWC_GAME_DEFINITIONS.values()
    }
    if definition := wire_labels.get(normalized):
        return definition
    if definition := SWC_GAME_NAME_DEFINITIONS.get(normalized):
        return definition

    # Native table names add stakes and table descriptors around the game title.
    padded_name = f" {normalized} "
    titles = set(SWC_GAME_NAME_DEFINITIONS) | set(wire_labels)
    for title in sorted(titles, key=len, reverse=True):
        if f" {title} " in padded_name:
            return wire_labels.get(title, SWC_GAME_NAME_DEFINITIONS.get(title, UNKNOWN_GAME))
    return UNKNOWN_GAME


@dataclass
class CapturedHandEnvelope:
    """Site-agnostic hand envelope emitted by HTTP capture."""

    site: str
    hand_id: str | int
    table_id: str | int | None
    game: CapturedGameDefinition
    timestamp: str
    gametype: dict[str, Any]
    players: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    showdown: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    raw_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "hand_id": self.hand_id,
            "table_id": self.table_id,
            "timestamp": self.timestamp,
            "game": self.game.to_capture_dict(),
            "gametype": self.gametype,
            "streets": self.game.street_profile.to_dict(),
            "players": self.players,
            "steps": self.steps,
            "actions": self.actions,
            "showdown": self.showdown,
            "raw": self.raw,
            "raw_refs": self.raw_refs,
            "metadata": self.metadata,
        }


@dataclass
class RawCaptureMessage:
    """Lossless raw message metadata for HTTP/WebSocket capture archives."""

    site: str
    transport: str
    payload: Any
    captured_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    endpoint: str | None = None
    message_type: str | None = None
    table_id: str | int | None = None
    hand_id: str | int | None = None
    sequence: int | None = None
    direction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "transport": self.transport,
            "captured_at": self.captured_at,
            "endpoint": self.endpoint,
            "message_type": self.message_type,
            "table_id": self.table_id,
            "hand_id": self.hand_id,
            "sequence": self.sequence,
            "direction": self.direction,
            "payload": self.payload,
        }


def json_default(value: Any) -> str:
    """JSON fallback for Decimal and datetime values in capture artifacts."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    return str(value)


def swc_game_definition(game_code: int | None) -> CapturedGameDefinition:
    """Return the FPDB-aligned game definition for a SwC game type code."""

    if game_code is None:
        return UNKNOWN_GAME
    return SWC_GAME_DEFINITIONS.get(int(game_code), UNKNOWN_GAME)
