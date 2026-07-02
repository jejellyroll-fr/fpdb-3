"""OFC-specific normalization for HTTP captures.

OFC is intentionally kept out of the generic Hand.py action model. The goal of
this module is to make OFC captures useful and auditable without pretending they
are Hold/Omaha hands.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


OFC_ROW_LIMITS = {"top": 3, "middle": 5, "bottom": 5}


@dataclass
class OFCPlayerState:
    """Final OFC state for one player."""

    name: str
    seat_idx: int | None
    starting_stack: Decimal
    top: list[str] = field(default_factory=list)
    middle: list[str] = field(default_factory=list)
    bottom: list[str] = field(default_factory=list)
    active: list[str] = field(default_factory=list)
    points: Decimal = Decimal("0")
    collected: Decimal = Decimal("0")


@dataclass
class OFCHand:
    """Dedicated OFC hand model for capture, replayer, and OFC DB storage."""

    site: str
    hand_id: str | int
    table_id: str | int | None
    timestamp: str | None
    variant: dict[str, Any]
    players: list[OFCPlayerState]
    rounds: list[dict[str, Any]]
    result: dict[str, Any]
    validation: dict[str, Any]
    raw_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "hand_id": self.hand_id,
            "table_id": self.table_id,
            "timestamp": self.timestamp,
            "variant": self.variant,
            "players": [asdict(player) for player in self.players],
            "rounds": self.rounds,
            "result": self.result,
            "validation": self.validation,
            "raw_refs": self.raw_refs,
        }


def _real_cards(cards: list[str] | tuple[str, ...] | None) -> list[str]:
    return [card for card in cards or [] if card and card != "--"]


def _row_delta(previous_cards: list[str], current_cards: list[str]) -> list[str]:
    previous = _real_cards(previous_cards)
    added = []
    remaining_previous = list(previous)
    for card in _real_cards(current_cards):
        if card in remaining_previous:
            remaining_previous.remove(card)
        else:
            added.append(card)
    return added


def _has_row_cards(rows: dict[str, Any]) -> bool:
    return any(_real_cards(rows.get(row, [])) for row in ("top", "middle", "bottom"))


def _row_slot_delta(previous_cards: list[str], current_cards: list[str]) -> list[dict[str, Any]]:
    additions = []
    remaining_previous = list(_real_cards(previous_cards))
    for index, card in enumerate(current_cards or []):
        if not card or card == "--":
            continue
        if card in remaining_previous:
            remaining_previous.remove(card)
        else:
            additions.append({"index": index, "card": card})
    return additions


def ofc_variant_metadata(hand_data: dict[str, Any]) -> dict[str, Any]:
    """Return stable OFC variant metadata for capture viewers/replayers."""

    category = (hand_data.get("game") or {}).get("category")
    label = (hand_data.get("game") or {}).get("label") or hand_data.get("game_type")
    pineapple = category in {"ofcp", "ofcp_27"} or "pineapple" in str(label).lower() or "/p" in str(label).lower()
    return {
        "family": "ofc",
        "variant": category or "ofc",
        "pineapple": pineapple,
        "deuce_to_seven": category == "ofcp_27" or "2-7" in str(label),
        "rows": dict(OFC_ROW_LIMITS),
        "hand_py_importable": False,
    }


def reconstruct_ofc_rounds(hand_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Reconstruct per-player OFC row changes from normalized snapshot steps."""

    rounds: list[dict[str, Any]] = []
    previous_by_player: dict[str, dict[str, Any]] = {}

    for step in hand_data.get("steps", []):
        placed = step.get("placed", {})
        for player, current in placed.items():
            if not isinstance(current, dict):
                continue
            previous = previous_by_player.get(player, {})
            if previous and not _has_row_cards(current) and not _real_cards(current.get("active", [])):
                continue
            row_additions = {}
            row_slot_additions = {}
            for row in ("top", "middle", "bottom"):
                added = _row_delta(previous.get(row, []), current.get(row, []))
                if added:
                    row_additions[row] = added
                slot_added = _row_slot_delta(previous.get(row, []), current.get(row, []))
                if slot_added:
                    row_slot_additions[row] = slot_added

            previous_active = _real_cards(previous.get("active", []))
            current_active = _real_cards(current.get("active", []))
            newly_active = [card for card in current_active if card not in previous_active]
            consumed_active = [card for card in previous_active if card not in current_active]
            placed_now = [card for cards in row_additions.values() for card in cards]
            discarded = [card for card in consumed_active if card not in placed_now]

            if row_additions or newly_active or discarded:
                rounds.append(
                    {
                        "round": len(rounds) + 1,
                        "step_num": step.get("step_num"),
                        "player": player,
                        "dealt": newly_active,
                        "placed": row_additions,
                        "placed_slots": row_slot_additions,
                        "layout": {
                            "top": list(current.get("top", [])),
                            "middle": list(current.get("middle", [])),
                            "bottom": list(current.get("bottom", [])),
                        },
                        "discarded": discarded,
                        "active": current_active,
                        "source": "ofc_snapshot_rows",
                    }
                )

            previous_by_player[player] = {
                "top": list(current.get("top", [])),
                "middle": list(current.get("middle", [])),
                "bottom": list(current.get("bottom", [])),
                "active": list(current.get("active", [])),
            }

    return rounds


def validate_ofc_layout(hand_data: dict[str, Any]) -> dict[str, Any]:
    """Validate row sizes and report conservative OFC capture status."""

    errors = []
    warnings = []
    final_step = hand_data.get("steps", [])[-1] if hand_data.get("steps") else {}
    for player, rows in final_step.get("placed", {}).items():
        if not isinstance(rows, dict):
            continue
        for row, limit in OFC_ROW_LIMITS.items():
            count = len(_real_cards(rows.get(row, [])))
            if count > limit:
                errors.append(f"{player} has {count} cards in {row}, max is {limit}")
        active_count = len(_real_cards(rows.get("active", [])))
        if active_count:
            warnings.append(f"{player} still has {active_count} active OFC cards")

    if not hand_data.get("showdown"):
        warnings.append("OFC showdown/settlement is not complete")
    if not hand_data.get("ofc_rounds"):
        warnings.append("OFC placement rounds were not reconstructed")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def reconstruct_ofc_result(hand_data: dict[str, Any]) -> dict[str, Any]:
    """Return a compact OFC result projection from showdown and collections."""

    showdown = hand_data.get("showdown") or {}
    return {
        "points_settled": showdown.get("points_settled", {}),
        "rows": showdown.get("rows", {}),
        "points_breakdown": showdown.get("points_breakdown", {}),
        "collections": hand_data.get("collections", []),
    }


def normalize_ofc_capture(hand_data: dict[str, Any]) -> None:
    """Populate OFC-specific normalized fields on a hand envelope."""

    hand_data.setdefault("metadata", {})["state_model"] = "ofc_snapshot"
    hand_data["ofc_variant"] = ofc_variant_metadata(hand_data)
    hand_data["ofc_rounds"] = reconstruct_ofc_rounds(hand_data)
    hand_data["ofc_result"] = reconstruct_ofc_result(hand_data)
    hand_data["ofc_validation"] = validate_ofc_layout(hand_data)

    status = "complete" if hand_data["ofc_rounds"] and hand_data["showdown"] and hand_data["ofc_validation"]["valid"] else "partial"
    hand_data.setdefault("metadata", {})["ofc_reconstruction"] = {
        "status": status,
        "rounds": len(hand_data["ofc_rounds"]),
        "validation_errors": len(hand_data["ofc_validation"]["errors"]),
        "validation_warnings": len(hand_data["ofc_validation"]["warnings"]),
    }


def build_ofc_hand(hand_data: dict[str, Any]) -> OFCHand:
    """Build a dedicated OFC hand model from a normalized capture envelope."""

    if (hand_data.get("game") or {}).get("base") != "ofc":
        raise ValueError("normalized hand is not an OFC capture")
    if "ofc_variant" not in hand_data:
        normalize_ofc_capture(hand_data)

    final_step = hand_data.get("steps", [])[-1] if hand_data.get("steps") else {}
    placed = final_step.get("placed", {})
    collections_by_player: dict[str, Decimal] = {}
    for collection in hand_data.get("ofc_result", {}).get("collections", []):
        player = collection.get("player")
        if not player:
            continue
        collections_by_player[player] = collections_by_player.get(player, Decimal("0")) + Decimal(str(collection.get("pot", "0")))

    players = []
    for player in hand_data.get("players", []):
        name = player.get("name")
        rows = placed.get(name, {}) if name else {}
        points = Decimal(str((hand_data.get("ofc_result", {}).get("points_settled") or {}).get(name, 0)))
        players.append(
            OFCPlayerState(
                name=name,
                seat_idx=player.get("seat_idx"),
                starting_stack=Decimal(str(player.get("starting_stack", 0))),
                top=_real_cards(rows.get("top", [])) if isinstance(rows, dict) else [],
                middle=_real_cards(rows.get("middle", [])) if isinstance(rows, dict) else [],
                bottom=_real_cards(rows.get("bottom", [])) if isinstance(rows, dict) else [],
                active=_real_cards(rows.get("active", [])) if isinstance(rows, dict) else [],
                points=points,
                collected=collections_by_player.get(name, Decimal("0")),
            )
        )

    return OFCHand(
        site=hand_data.get("site"),
        hand_id=hand_data.get("hand_id"),
        table_id=hand_data.get("table_id"),
        timestamp=hand_data.get("timestamp"),
        variant=hand_data.get("ofc_variant", {}),
        players=players,
        rounds=list(hand_data.get("ofc_rounds", [])),
        result=dict(hand_data.get("ofc_result", {})),
        validation=dict(hand_data.get("ofc_validation", {})),
        raw_refs=list(hand_data.get("raw_refs", [])),
    )


def ofc_hand_from_dict(data: dict[str, Any]) -> OFCHand:
    """Rehydrate an OFCHand from its serialized dictionary form."""

    return OFCHand(
        site=data.get("site"),
        hand_id=data.get("hand_id"),
        table_id=data.get("table_id"),
        timestamp=data.get("timestamp"),
        variant=dict(data.get("variant", {})),
        players=[
            OFCPlayerState(
                name=player.get("name"),
                seat_idx=player.get("seat_idx"),
                starting_stack=Decimal(str(player.get("starting_stack", "0"))),
                top=list(player.get("top", [])),
                middle=list(player.get("middle", [])),
                bottom=list(player.get("bottom", [])),
                active=list(player.get("active", [])),
                points=Decimal(str(player.get("points", "0"))),
                collected=Decimal(str(player.get("collected", "0"))),
            )
            for player in data.get("players", [])
        ],
        rounds=list(data.get("rounds", [])),
        result=dict(data.get("result", {})),
        validation=dict(data.get("validation", {})),
        raw_refs=list(data.get("raw_refs", [])),
    )


def render_ofc_hand_text(ofc_hand: OFCHand) -> str:
    """Render a deterministic text view for OFC replayer/debugging."""

    lines = [
        f"OFC Hand #{ofc_hand.hand_id} - {ofc_hand.variant.get('variant', 'ofc')}",
        f"Table: {ofc_hand.table_id}",
        f"Timestamp: {ofc_hand.timestamp or ''}",
        "",
        "Players:",
    ]
    for player in ofc_hand.players:
        lines.extend(
            [
                f"Seat {player.seat_idx}: {player.name} stack={player.starting_stack} points={player.points} collected={player.collected}",
                f"  Top: {' '.join(player.top) or '-'}",
                f"  Middle: {' '.join(player.middle) or '-'}",
                f"  Bottom: {' '.join(player.bottom) or '-'}",
            ]
        )
        if player.active:
            lines.append(f"  Active: {' '.join(player.active)}")

    lines.append("")
    lines.append("Rounds:")
    for round_info in ofc_hand.rounds:
        placed = round_info.get("placed", {})
        placed_parts = [f"{row}={' '.join(cards)}" for row, cards in placed.items()]
        discarded = round_info.get("discarded") or []
        discard_text = f" discard={' '.join(discarded)}" if discarded else ""
        lines.append(
            f"  {round_info.get('round')}. {round_info.get('player')}: "
            f"{'; '.join(placed_parts) or 'no placement'}{discard_text}"
        )

    if ofc_hand.validation.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in ofc_hand.validation["warnings"])
    return "\n".join(lines).rstrip() + "\n"


def render_ofc_hand_html(ofc_hand: OFCHand) -> str:
    """Render a simple standalone HTML fragment for an OFC visual replayer."""

    def esc(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    player_cards = []
    for player in ofc_hand.players:
        rows = "".join(
            f'<div class="ofc-row ofc-{row}"><b>{label}</b> '
            f'<span>{" ".join(esc(card) for card in cards) or "-"}</span></div>'
            for row, label, cards in (
                ("top", "Top", player.top),
                ("middle", "Middle", player.middle),
                ("bottom", "Bottom", player.bottom),
            )
        )
        player_cards.append(
            '<section class="ofc-player">'
            f"<h3>Seat {esc(player.seat_idx)} - {esc(player.name)}</h3>"
            f'<p class="ofc-score">Points {esc(player.points)} | Collected {esc(player.collected)}</p>'
            f"{rows}</section>"
        )
    rounds = "".join(
        f"<li><b>{esc(round_info.get('round'))}. {esc(round_info.get('player'))}</b>: "
        f"{esc(round_info.get('placed'))}</li>"
        for round_info in ofc_hand.rounds
    )
    return (
        '<article class="ofc-replayer">'
        f"<h2>OFC Hand #{esc(ofc_hand.hand_id)} ({esc(ofc_hand.variant.get('variant', 'ofc'))})</h2>"
        f'<div class="ofc-players">{"".join(player_cards)}</div>'
        f"<ol>{rounds}</ol>"
        "</article>"
    )


def _cursor(db: Any) -> Any:
    return db.get_cursor() if hasattr(db, "get_cursor") else db.cursor()


def ensure_ofc_tables(db: Any) -> None:
    """Create dedicated OFC capture/stat tables if missing."""

    cursor = _cursor(db)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS HttpOFCHands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT NOT NULL,
            siteHandNo TEXT NOT NULL UNIQUE,
            tableName TEXT,
            startTime TEXT,
            variant TEXT,
            pineapple INTEGER,
            deuceToSeven INTEGER,
            rounds INTEGER,
            validationStatus TEXT,
            rawJson TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS HttpOFCPlayers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ofcHandId INTEGER NOT NULL,
            playerName TEXT NOT NULL,
            seatNo INTEGER,
            startStack REAL,
            points REAL,
            collected REAL,
            topCards TEXT,
            middleCards TEXT,
            bottomCards TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS HttpOFCRounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ofcHandId INTEGER NOT NULL,
            roundNo INTEGER,
            stepNo INTEGER,
            playerName TEXT,
            dealt TEXT,
            placedJson TEXT,
            discarded TEXT
        )
        """
    )
    if hasattr(db, "commit"):
        db.commit()


def import_ofc_hand(db: Any, ofc_hand: OFCHand, *, doinsert: bool = True) -> int | None:
    """Store an OFC hand into dedicated OFC tables and return the row id."""

    ensure_ofc_tables(db)
    if not doinsert:
        return None
    cursor = _cursor(db)
    cursor.execute("SELECT id FROM HttpOFCHands WHERE siteHandNo = ?", (str(ofc_hand.hand_id),))
    existing = cursor.fetchone()
    if existing:
        existing_id = existing[0]
        cursor.execute("DELETE FROM HttpOFCPlayers WHERE ofcHandId = ?", (existing_id,))
        cursor.execute("DELETE FROM HttpOFCRounds WHERE ofcHandId = ?", (existing_id,))
    cursor.execute("DELETE FROM HttpOFCHands WHERE siteHandNo = ?", (str(ofc_hand.hand_id),))
    cursor.execute(
        """
        INSERT INTO HttpOFCHands (
            site, siteHandNo, tableName, startTime, variant, pineapple,
            deuceToSeven, rounds, validationStatus, rawJson
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ofc_hand.site,
            str(ofc_hand.hand_id),
            str(ofc_hand.table_id or ""),
            ofc_hand.timestamp,
            ofc_hand.variant.get("variant"),
            1 if ofc_hand.variant.get("pineapple") else 0,
            1 if ofc_hand.variant.get("deuce_to_seven") else 0,
            len(ofc_hand.rounds),
            "valid" if ofc_hand.validation.get("valid") else "invalid",
            json.dumps(ofc_hand.to_dict(), default=str, sort_keys=True),
        ),
    )
    ofc_hand_id = cursor.lastrowid
    for player in ofc_hand.players:
        cursor.execute(
            """
            INSERT INTO HttpOFCPlayers (
                ofcHandId, playerName, seatNo, startStack, points, collected,
                topCards, middleCards, bottomCards
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ofc_hand_id,
                player.name,
                player.seat_idx,
                float(player.starting_stack),
                float(player.points),
                float(player.collected),
                " ".join(player.top),
                " ".join(player.middle),
                " ".join(player.bottom),
            ),
        )
    for round_info in ofc_hand.rounds:
        cursor.execute(
            """
            INSERT INTO HttpOFCRounds (
                ofcHandId, roundNo, stepNo, playerName, dealt, placedJson, discarded
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ofc_hand_id,
                round_info.get("round"),
                round_info.get("step_num"),
                round_info.get("player"),
                " ".join(round_info.get("dealt") or []),
                json.dumps(round_info.get("placed") or {}, sort_keys=True),
                " ".join(round_info.get("discarded") or []),
            ),
        )
    if hasattr(db, "commit"):
        db.commit()
    return int(ofc_hand_id)


def query_ofc_player_stats(db: Any) -> list[dict[str, Any]]:
    """Return aggregate OFC stats from dedicated OFC tables."""

    ensure_ofc_tables(db)
    cursor = _cursor(db)
    cursor.execute(
        """
        SELECT
            playerName,
            COUNT(*) AS hands,
            SUM(points) AS points,
            SUM(collected) AS collected
        FROM HttpOFCPlayers
        GROUP BY playerName
        ORDER BY playerName
        """
    )
    return [
        {
            "player": row[0],
            "hands": int(row[1] or 0),
            "points": Decimal(str(row[2] or 0)),
            "collected": Decimal(str(row[3] or 0)),
        }
        for row in cursor.fetchall()
    ]


def load_ofc_hand(db: Any, row_id_or_site_hand_no: int | str) -> OFCHand:
    """Load an OFCHand from dedicated OFC DB tables."""

    ensure_ofc_tables(db)
    cursor = _cursor(db)
    key = str(row_id_or_site_hand_no)
    if key.isdigit():
        cursor.execute("SELECT rawJson FROM HttpOFCHands WHERE id = ? OR siteHandNo = ?", (int(key), key))
    else:
        cursor.execute("SELECT rawJson FROM HttpOFCHands WHERE siteHandNo = ?", (key,))
    row = cursor.fetchone()
    if not row:
        raise KeyError(f"OFC hand not found: {row_id_or_site_hand_no}")
    return ofc_hand_from_dict(json.loads(row[0]))
