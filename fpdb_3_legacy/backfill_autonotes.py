#!/usr/bin/env python3
"""Backfill generated player autonotes for already-imported hands.

Usage:
    python -m fpdb_3_legacy.backfill_autonotes PATH [PATH ...] [--commit]
                                              [--config HUD_config.xml]

PATH may be a hand-history file or a directory scanned recursively. Without
--commit the run is a dry run that only reports what would be generated.
"""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any

from fpdb_3_legacy import Configuration, Database, IdentifySite, Importer
from fpdb_3_legacy.AutoNotes import (
    available_rule_id_to_rule_set_id,
    available_rule_ids,
    available_rule_set_ids,
    available_rule_sets,
    configured_rule_summary,
    format_note_evidence,
    format_rule_summary,
    generate_for_hand,
    rule_manifest,
    rule_set_enabled,
)
from fpdb_3_legacy.iPoker.dispatcher import get_parser_class_for_path as get_ipoker_parser_class_for_path
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.parser_registry import get_parser_class

log = get_logger("backfill_autonotes")

_HH_EXTENSIONS = (".txt", ".xml", ".hh", ".log")
STREET_BY_ID = {
    -1: "BLINDSANTES",
    0: "PREFLOP",
    1: "FLOP",
    2: "TURN",
    3: "RIVER",
    4: "SHOWDOWN",
}
AOF_STREET_BY_ID = {
    -1: "BLINDSANTES",
    0: "FLOP",
    1: "TURN",
    2: "RIVER",
    3: "SHOWDOWN",
}
CENTS_MULTIPLIER = Decimal("100")


class DatabaseAutoNoteHand:
    """Small Hand-compatible adapter reconstructed from imported DB rows."""

    def __init__(self, hand_row, player_rows, action_rows) -> None:
        self.dbid_hands = hand_row["id"]
        self.handid = hand_row.get("siteHandNo")
        self.siteId = hand_row.get("siteId")
        self.tourNo = hand_row.get("tourneyId")
        self.isSng = bool(hand_row.get("tourneyId"))
        self.gametype = {
            "base": hand_row.get("base"),
            "category": hand_row.get("category"),
            "limitType": hand_row.get("limitType"),
            "type": hand_row.get("type"),
            "siteId": hand_row.get("siteId"),
            "bigBlind": _chips_to_units(hand_row.get("bigBlind")),
            "smallBlind": _chips_to_units(hand_row.get("smallBlind")),
            "bb": _chips_to_units(hand_row.get("bigBlind")),
            "sb": _chips_to_units(hand_row.get("smallBlind")),
        }
        self.bb = self.gametype["bigBlind"]
        self.hands = {
            "finalPot": _chips_to_units(hand_row.get("finalPot")),
            "street0Pot": _chips_to_units(hand_row.get("street0Pot")),
            "street1Pot": _chips_to_units(hand_row.get("street1Pot")),
            "street2Pot": _chips_to_units(hand_row.get("street2Pot")),
            "street3Pot": _chips_to_units(hand_row.get("street3Pot")),
            "street4Pot": _chips_to_units(hand_row.get("street4Pot")),
        }
        self.finalPot = self.hands["finalPot"]
        self.players = []
        self.playerIds = {}
        self.handsplayers = {}
        self._holecards = {}
        for row in player_rows:
            player = row["name"]
            self.players.append((row.get("seatNo"), player, _chips_to_units(row.get("startCash"))))
            self.playerIds[player] = row["playerId"]
            self._holecards[player] = [
                card for card in (_decode_card(row.get(f"card{index}")) for index in range(1, 21)) if card
            ]
            self.handsplayers[player] = {
                "position": _normalise_position(row.get("position")),
                "startCash": _chips_to_units(row.get("startCash")),
                "effStack": _chips_to_units(row.get("effStack")),
                "totalProfit": _chips_to_units(row.get("totalProfit")),
                "showdownWinnings": _chips_to_units(row.get("winnings")),
                "wonAtSD": bool(row.get("wonAtSD")) if "wonAtSD" in row else None,
                "sawShowdown": bool(row.get("sawShowdown")) if "sawShowdown" in row else None,
                "handString": row.get("comment") or "",
                "cnt_f_spr": row.get("cnt_f_spr"),
                "val_f_spr": row.get("val_f_spr"),
                "cnt_t_spr": row.get("cnt_t_spr"),
                "val_t_spr": row.get("val_t_spr"),
                "cnt_r_spr": row.get("cnt_r_spr"),
                "val_r_spr": row.get("val_r_spr"),
            }

        if hand_row.get("category") in {"aof_omaha", "aof_holdem"}:
            self.actionStreets = ["BLINDSANTES", "FLOP", "TURN", "RIVER", "SHOWDOWN"]
            street_by_id = AOF_STREET_BY_ID
        else:
            self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER", "SHOWDOWN"]
            street_by_id = STREET_BY_ID
        self.actions: dict[str, list[Any]] = {street: [] for street in self.actionStreets}
        for row in action_rows:
            street = street_by_id.get(row.get("street"), self.actionStreets[1])
            action = _action_tuple(row)
            if action:
                self.actions.setdefault(street, []).append(action)

        self.board = {
            "FLOP": [
                card
                for card in (
                    _decode_card(hand_row.get("boardcard1")),
                    _decode_card(hand_row.get("boardcard2")),
                    _decode_card(hand_row.get("boardcard3")),
                )
                if card
            ],
            "TURN": [_decode_card(hand_row.get("boardcard4"))] if _decode_card(hand_row.get("boardcard4")) else [],
            "RIVER": [_decode_card(hand_row.get("boardcard5"))] if _decode_card(hand_row.get("boardcard5")) else [],
        }
        self.hero = ""

        self._reconstruct_pot()

    def _reconstruct_pot(self) -> None:
        committed: dict[str, Decimal] = {}
        folded: list[str] = []
        for street in self.actionStreets:
            for action in self.actions[street]:
                player = action[0]
                name = action[1]
                if name in ("small blind", "big blind", "post ante", "calls", "bets"):
                    committed[player] = committed.get(player, Decimal(0)) + action[2]
                elif name in ("raises", "completes"):
                    _, _, amount, raise_to, amount_called, _ = action
                    committed[player] = committed.get(player, Decimal(0)) + amount + amount_called
                elif name == "folds":
                    folded.append(player)

        class _ReconstructedPot:
            committed: dict[str, Decimal]
            common: dict[str, Decimal]
            contenders: set[str]
            stp: Decimal

        pot = _ReconstructedPot()
        pot.committed = {p: committed.get(p, Decimal(0)) for p in (player[1] for player in self.players)}
        pot.common = {}
        pot.contenders = {str(player[1]) for player in self.players} - {str(f) for f in folded}
        pot.stp = Decimal(0)
        self.pot = pot
        self.totalpot = self.finalPot
        self.rake = Decimal(0)
        self.folded = folded

    def assembleHand(self):
        return None

    def join_holecards(self, player_name, asList=False):
        cards = self._holecards.get(player_name, [])
        return cards if asList else " ".join(cards)


def iter_files(paths):
    """Yield candidate hand-history files under the given paths."""
    for path in paths:
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for filename in sorted(files):
                    if filename.lower().endswith(_HH_EXTENSIONS):
                        yield os.path.join(root, filename)
        elif os.path.isfile(path):
            yield path


def _row_dict(cursor, row) -> dict:
    return {description[0]: value for description, value in zip(cursor.description, row, strict=False)}


def _chips_to_units(value):
    if value is None or value == "":
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        log.debug("Unable to convert chip value %r to Decimal units", value, exc_info=True)
        return value
    return decimal_value / CENTS_MULTIPLIER


def _decode_card(card_value) -> str:
    if not card_value:
        return ""
    try:
        card_number = int(card_value)
    except (TypeError, ValueError):
        return ""
    if card_number <= 0:
        return ""
    ranks = "23456789TJQKA"
    suits = "hdcs"
    rank_index = (card_number - 1) % 13
    suit_index = (card_number - 1) // 13
    if suit_index < 0 or suit_index >= len(suits):
        return ""
    return f"{ranks[rank_index]}{suits[suit_index]}"


def _normalise_position(position):
    if position is None:
        return None
    if isinstance(position, str):
        stripped = position.strip()
        if stripped in {"S", "B"}:
            return stripped
        try:
            return int(stripped)
        except ValueError:
            return stripped
    return position


def _amount_units(value):
    amount = _chips_to_units(value)
    return amount if amount is not None else 0


def _action_tuple(row) -> tuple | None:
    player = row.get("playerName")
    action = row.get("actionName")
    if not player or not action:
        return None
    amount = _amount_units(row.get("amount"))
    if action in {"raises", "completes"}:
        raise_to = _amount_units(row.get("raiseTo"))
        amount_called = _amount_units(row.get("amountCalled"))
        return (player, action, amount, raise_to, amount_called, bool(row.get("allIn")))
    if action == "discards":
        return (player, action, row.get("numDiscarded") or 0, row.get("cardsDiscarded"), bool(row.get("allIn")))
    if action in {"folds", "checks", "stands pat"}:
        return (player, action, bool(row.get("allIn")))
    return (player, action, amount, bool(row.get("allIn")))


def _lookup_hand_ids(db, site_hand_no, site_id, stats=None):
    placeholder = db.sql.query["placeholder"]
    c = db.get_cursor()
    q = (
        "SELECT H.id FROM Hands H JOIN Gametypes G ON H.gametypeId=G.id "
        f"WHERE H.siteHandNo={placeholder} AND G.siteId={placeholder}"
    )
    try:
        key = int(site_hand_no)
    except (TypeError, ValueError):
        key = site_hand_no
    c.execute(q, (key, site_id))
    rows = [row[0] for row in c.fetchall()]
    if rows or site_id is None:
        return rows

    c.execute(f"SELECT id FROM Hands WHERE siteHandNo={placeholder}", (key,))
    fallback_rows = [row[0] for row in c.fetchall()]
    if fallback_rows and stats is not None:
        stats["matched_by_site_hand_only"] = stats.get("matched_by_site_hand_only", 0) + len(fallback_rows)
    return fallback_rows


def _player_ids_for_hand(db, db_hand_id):
    placeholder = db.sql.query["placeholder"]
    c = db.get_cursor()
    c.execute(
        "SELECT p.name, hp.playerId FROM HandsPlayers hp JOIN Players p ON hp.playerId=p.id "
        f"WHERE hp.handId={placeholder}",
        (db_hand_id,),
    )
    return {name: pid for name, pid in c.fetchall()}


def _database_hand_filters(db, date_from=None, date_to=None, site_id=None, limit_type=None):
    placeholder = db.sql.query["placeholder"]
    clauses = []
    params = []
    if date_from:
        clauses.append(f"H.startTime >= {placeholder}")
        params.append(date_from)
    if date_to:
        clauses.append(f"H.startTime <= {placeholder}")
        params.append(f"{date_to} 23:59:59" if len(str(date_to)) == 10 else date_to)
    if site_id is not None:
        clauses.append(f"G.siteId = {placeholder}")
        params.append(site_id)
    if limit_type:
        clauses.append(f"G.limitType = {placeholder}")
        params.append(limit_type)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _database_hand_ids(db, limit=1000, date_from=None, date_to=None, site_id=None, limit_type=None):
    placeholder = db.sql.query["placeholder"]
    where_clause, params = _database_hand_filters(
        db,
        date_from=date_from,
        date_to=date_to,
        site_id=site_id,
        limit_type=limit_type,
    )
    limit_clause = f" LIMIT {placeholder}" if limit else ""
    if limit:
        params.append(int(limit))
    c = db.get_cursor()
    c.execute(
        "SELECT H.id FROM Hands H JOIN Gametypes G ON H.gametypeId=G.id"
        f"{where_clause} ORDER BY H.startTime DESC, H.id DESC{limit_clause}",
        tuple(params),
    )
    return [row[0] for row in c.fetchall()]


def _database_hand_row(db, hand_id) -> dict | None:
    placeholder = db.sql.query["placeholder"]
    c = db.get_cursor()
    c.execute(
        "SELECT H.id, H.siteHandNo, H.tourneyId, H.startTime, H.seats, H.heroSeat, "
        "H.boardcard1, H.boardcard2, H.boardcard3, H.boardcard4, H.boardcard5, "
        "H.street0Pot, H.street1Pot, H.street2Pot, H.street3Pot, H.street4Pot, H.finalPot, "
        "G.siteId, G.type, G.base, G.category, G.limitType, G.smallBlind, G.bigBlind "
        "FROM Hands H JOIN Gametypes G ON H.gametypeId=G.id "
        f"WHERE H.id={placeholder}",
        (hand_id,),
    )
    row = c.fetchone()
    return _row_dict(c, row) if row else None


def _database_player_rows(db, hand_id) -> list[dict]:
    placeholder = db.sql.query["placeholder"]
    c = db.get_cursor()
    card_columns = ", ".join(f"HP.card{index}" for index in range(1, 21))
    c.execute(
        "SELECT HP.playerId, P.name, HP.seatNo, HP.position, HP.startCash, HP.effStack, "
        f"{card_columns}, HP.totalProfit, HP.winnings, HP.comment, HP.wonAtSD, HP.sawShowdown, "
        "HP.cnt_f_spr, HP.val_f_spr, HP.cnt_t_spr, HP.val_t_spr, HP.cnt_r_spr, HP.val_r_spr "
        "FROM HandsPlayers HP JOIN Players P ON HP.playerId=P.id "
        f"WHERE HP.handId={placeholder} ORDER BY HP.seatNo",
        (hand_id,),
    )
    return [_row_dict(c, row) for row in c.fetchall()]


def _database_action_rows(db, hand_id) -> list[dict]:
    placeholder = db.sql.query["placeholder"]
    c = db.get_cursor()
    c.execute(
        "SELECT HA.street, HA.actionNo, HA.streetActionNo, HA.amount, HA.raiseTo, HA.amountCalled, "
        "HA.numDiscarded, HA.cardsDiscarded, HA.allIn, P.name AS playerName, A.name AS actionName "
        "FROM HandsActions HA "
        "JOIN Players P ON HA.playerId=P.id "
        "LEFT JOIN Actions A ON HA.actionId=A.id "
        f"WHERE HA.handId={placeholder} ORDER BY HA.actionNo, HA.street, HA.streetActionNo",
        (hand_id,),
    )
    return [_row_dict(c, row) for row in c.fetchall()]


def load_hand_from_database(db, hand_id) -> DatabaseAutoNoteHand | None:
    hand_row = _database_hand_row(db, hand_id)
    if not hand_row:
        return None
    player_rows = _database_player_rows(db, hand_id)
    if not player_rows:
        return None
    return DatabaseAutoNoteHand(hand_row, player_rows, _database_action_rows(db, hand_id))


def _prepare_hand_for_autonotes(hand, db_hand_id, player_ids, config=None, rule_set_ids=None, rule_ids=None):
    hand.dbid_hands = db_hand_id
    hand.playerIds = player_ids
    if not getattr(hand, "handsplayers", None):
        hand.assembleHand()
    return generate_for_hand(hand, config=config, rule_set_ids=rule_set_ids, rule_ids=rule_ids)


def parse_id_filter(values) -> set[str] | None:
    if not values:
        return None
    selected: set[str] = set()
    for value in values:
        selected.update(part.strip() for part in value.split(",") if part.strip())
    return selected or None


parse_rule_set_filter = parse_id_filter


def unknown_filter_ids(selected_ids: set[str] | None, known_ids: set[str]) -> list[str]:
    if not selected_ids:
        return []
    return sorted(selected_ids - known_ids)


def _add_rule_counts(stats, notes):
    rule_counts = stats.setdefault("rules", {})
    rule_set_counts = stats.setdefault("rule_sets", {})
    _add_rule_counts_to_maps(rule_counts, rule_set_counts, notes)


def _add_raw_unmatched_rule_counts(stats, notes):
    rule_counts = stats.setdefault("raw_unmatched_rules", {})
    rule_set_counts = stats.setdefault("raw_unmatched_rule_sets", {})
    _add_rule_counts_to_maps(rule_counts, rule_set_counts, notes)


def _add_rule_counts_to_maps(rule_counts, rule_set_counts, notes):
    rule_to_rule_set = available_rule_id_to_rule_set_id()
    for note in notes:
        rule_counts[note.rule_id] = rule_counts.get(note.rule_id, 0) + 1
        rule_set_id = rule_to_rule_set.get(note.rule_id, "unknown")
        rule_set_counts[rule_set_id] = rule_set_counts.get(rule_set_id, 0) + 1


def _add_game_count(stats, hand):
    gametype = getattr(hand, "gametype", {}) or {}
    key = "/".join(
        str(value or "?")
        for value in (
            gametype.get("base"),
            gametype.get("category"),
            gametype.get("limitType"),
            gametype.get("type"),
        )
    )
    games = stats.setdefault("games", {})
    games[key] = games.get(key, 0) + 1


def _supported_rule_set_ids(hand, rule_set_ids=None) -> list[str]:
    return [
        rule_set.rule_set_id
        for rule_set in available_rule_sets()
        if (rule_set_ids is None or rule_set.rule_set_id in rule_set_ids) and rule_set.supports_hand(hand)
    ]


def _enabled_supported_rule_set_ids(hand, config, rule_set_ids=None) -> list[str]:
    return [
        rule_set.rule_set_id
        for rule_set in available_rule_sets()
        if (rule_set_ids is None or rule_set.rule_set_id in rule_set_ids)
        and rule_set.supports_hand(hand)
        and rule_set_enabled(config, rule_set.rule_set_id, default=rule_set.enabled_by_default)
    ]


def _add_no_note_diagnostics(stats, hand, config, rule_set_ids=None):
    _add_game_count(stats, hand)
    supported = _supported_rule_set_ids(hand, rule_set_ids=rule_set_ids)
    if not supported:
        stats["unsupported_hands"] = stats.get("unsupported_hands", 0) + 1
        return
    if not _enabled_supported_rule_set_ids(hand, config, rule_set_ids=rule_set_ids):
        stats["disabled_hands"] = stats.get("disabled_hands", 0) + 1
        return
    stats["no_note_hands"] = stats.get("no_note_hands", 0) + 1


def _preview_row(note, player_names_by_id=None, hand=None) -> dict:
    """Return a GUI/JSON-friendly preview row for a generated note."""
    player_names_by_id = player_names_by_id or {}
    rule_set_id = available_rule_id_to_rule_set_id().get(note.rule_id, "unknown")
    evidence = dict(note.evidence or {})
    return {
        "playerId": note.player_id,
        "playerName": player_names_by_id.get(note.player_id, ""),
        "handId": note.hand_id,
        "siteHandNo": getattr(hand, "handid", ""),
        "siteId": getattr(hand, "siteId", ""),
        "ruleSet": rule_set_id,
        "ruleId": note.rule_id,
        "ruleVersion": note.rule_version,
        "noteText": note.note_text,
        "evidence": evidence,
        "evidenceText": format_note_evidence(evidence),
    }


def format_rule_counts(rule_counts) -> str:
    """Format generated-note counts by rule for CLI output."""
    if not rule_counts:
        return ""
    return ", ".join(f"{rule_id}={count}" for rule_id, count in sorted(rule_counts.items()))


def format_stats_json(stats, commit=False, rule_set_ids=None, rule_ids=None) -> str:
    """Format backfill stats as stable JSON for automation."""
    payload = {
        "mode": "write" if commit else "dry_run",
        "source": stats.get("source", "files"),
        "files": stats.get("files", 0),
        "files_skipped": stats.get("files_skipped", 0),
        "hands": stats.get("hands", 0),
        "matched_hands": stats.get("matched_hands", 0),
        "unmatched_hands": stats.get("unmatched_hands", 0),
        "matched_by_site_hand_only": stats.get("matched_by_site_hand_only", 0),
        "hands_without_actions": stats.get("hands_without_actions", 0),
        "unsupported_hands": stats.get("unsupported_hands", 0),
        "disabled_hands": stats.get("disabled_hands", 0),
        "no_note_hands": stats.get("no_note_hands", 0),
        "raw_unmatched_hands": stats.get("raw_unmatched_hands", 0),
        "raw_unmatched_notes": stats.get("raw_unmatched_notes", 0),
        "raw_unmatched_rule_sets": dict(sorted((stats.get("raw_unmatched_rule_sets") or {}).items())),
        "raw_unmatched_rules": dict(sorted((stats.get("raw_unmatched_rules") or {}).items())),
        "games": dict(sorted((stats.get("games") or {}).items())),
        "unmatched_samples": stats.get("unmatched_samples", []),
        "import_files": stats.get("import_files", 0),
        "import_stored": stats.get("import_stored", 0),
        "import_duplicates": stats.get("import_duplicates", 0),
        "import_partial": stats.get("import_partial", 0),
        "import_skipped": stats.get("import_skipped", 0),
        "import_errors": stats.get("import_errors", 0),
        "notes": stats.get("notes", 0),
        "rule_sets": dict(sorted((stats.get("rule_sets") or {}).items())),
        "rules": dict(sorted((stats.get("rules") or {}).items())),
        "rule_sets_filter": sorted(rule_set_ids) if rule_set_ids else [],
        "rules_filter": sorted(rule_ids) if rule_ids else [],
    }
    return json.dumps(payload, sort_keys=True)


def format_rule_summary_json(summary) -> str:
    """Format configured rule details as stable JSON for automation."""
    return json.dumps({"rule_sets": summary}, sort_keys=True)


def _parser_for_path(config, idsite, path):
    try:
        idsite.processFile(path)
        fobj = idsite.get_fobj(path)
    except Exception as e:  # noqa: BLE001 - unidentifiable file: skip.
        log.debug("identify failed %s: %s", path, e)
        return None
    if not fobj or not getattr(fobj, "site", None):
        return None

    filter_name = fobj.site.filter_name
    parser_class = get_parser_class(filter_name)
    if filter_name == "iPoker":
        parser_class = get_ipoker_parser_class_for_path(path)
    if not callable(parser_class):
        return None
    return parser_class(config, in_path=path, autostart=False, sitename=fobj.site.name)


def backfill_preview(
    paths,
    commit=False,
    config_file="HUD_config.xml",
    db=None,
    rule_set_ids=None,
    rule_ids=None,
    diagnose_unmatched=True,
    status_callback=None,
):
    """Backfill PlayerAutoNotes and return stats plus generated-note preview rows."""
    config = Configuration.Config(file=config_file)
    owns_db = db is None
    if owns_db:
        db = Database.Database(config)
    if hasattr(db, "ensure_feature_tables"):
        db.ensure_feature_tables()

    idsite = IdentifySite.IdentifySite(config)
    stats: dict[str, Any] = {
        "files": 0,
        "files_skipped": 0,
        "hands": 0,
        "matched_hands": 0,
        "notes": 0,
        "rule_sets": {},
        "rules": {},
        "preview": [],
    }
    hand_lookup_cache = {}
    player_ids_cache = {}

    for path in iter_files(paths):
        if status_callback:
            status_callback(f"Parsing {os.path.basename(path)}")
        try:
            parser = _parser_for_path(config, idsite, path)
            if parser is None:
                stats["files_skipped"] += 1
                continue
            parser.start()
        except Exception as e:  # noqa: BLE001 - parser failure on this file: skip.
            log.debug("parse failed %s: %s", path, e)
            stats["files_skipped"] += 1
            continue

        stats["files"] += 1
        for hand in parser.getProcessedHands():
            stats["hands"] += 1
            site_id = getattr(hand, "siteId", None)
            site_hand_no = getattr(hand, "handid", None)
            if site_id is None or site_hand_no is None:
                continue
            lookup_key = (str(site_hand_no), site_id)
            if lookup_key not in hand_lookup_cache:
                hand_lookup_cache[lookup_key] = _lookup_hand_ids(db, site_hand_no, site_id, stats=stats)
            db_hand_ids = hand_lookup_cache[lookup_key]
            if not db_hand_ids:
                stats["unmatched_hands"] = stats.get("unmatched_hands", 0) + 1
                unmatched = stats.setdefault("unmatched_samples", [])
                if len(unmatched) < 20:
                    unmatched.append({"siteHandNo": site_hand_no, "siteId": site_id})
                if not diagnose_unmatched:
                    continue
                hand.dbid_hands = -stats["unmatched_hands"]
                hand.playerIds = _raw_player_ids(hand, start=hand.dbid_hands * 1000)
                if not getattr(hand, "handsplayers", None):
                    hand.assembleHand()
                raw_notes = generate_for_hand(hand, config=config, rule_set_ids=rule_set_ids, rule_ids=rule_ids)
                if raw_notes:
                    stats["raw_unmatched_hands"] = stats.get("raw_unmatched_hands", 0) + 1
                    stats["raw_unmatched_notes"] = stats.get("raw_unmatched_notes", 0) + len(raw_notes)
                    _add_raw_unmatched_rule_counts(stats, raw_notes)
                else:
                    _add_no_note_diagnostics(stats, hand, config, rule_set_ids=rule_set_ids)
            for db_hand_id in db_hand_ids:
                if db_hand_id not in player_ids_cache:
                    player_ids_cache[db_hand_id] = _player_ids_for_hand(db, db_hand_id)
                player_ids = player_ids_cache[db_hand_id]
                if not player_ids:
                    continue
                player_names_by_id = {player_id: name for name, player_id in player_ids.items()}
                notes = _prepare_hand_for_autonotes(
                    hand,
                    db_hand_id,
                    player_ids,
                    config=config,
                    rule_set_ids=rule_set_ids,
                    rule_ids=rule_ids,
                )
                if not notes:
                    _add_no_note_diagnostics(stats, hand, config, rule_set_ids=rule_set_ids)
                    continue
                stats["matched_hands"] += 1
                stats["notes"] += len(notes)
                _add_rule_counts(stats, notes)
                stats["preview"].extend(_preview_row(note, player_names_by_id, hand) for note in notes)
                if commit:
                    db.storePlayerAutoNotes(notes, doinsert=True)
            if status_callback and stats["hands"] % 100 == 0:
                status_callback(
                    f"Scanned {stats['hands']} hands, matched {stats['matched_hands']}, notes {stats['notes']}",
                )

    if commit:
        db.commit()
    if owns_db:
        db.close_connection()
    return stats


def _raw_player_ids(hand, start=-1) -> dict[str, int]:
    player_ids = {}
    next_id = start
    for player in getattr(hand, "players", []) or []:
        if len(player) < 2:
            continue
        player_ids[player[1]] = next_id
        next_id -= 1
    return player_ids


def backfill_raw_preview(paths, config_file="HUD_config.xml", rule_set_ids=None, rule_ids=None):
    """Generate a read-only preview directly from hand-history files, without DB matching."""
    config = Configuration.Config(file=config_file)
    idsite = IdentifySite.IdentifySite(config)
    stats: dict[str, Any] = {
        "files": 0,
        "files_skipped": 0,
        "hands": 0,
        "matched_hands": 0,
        "notes": 0,
        "rule_sets": {},
        "rules": {},
        "preview": [],
        "source": "raw_files",
    }
    synthetic_hand_id = -1

    for path in iter_files(paths):
        try:
            parser = _parser_for_path(config, idsite, path)
            if parser is None:
                stats["files_skipped"] += 1
                continue
            parser.start()
        except Exception as e:  # noqa: BLE001 - parser failure on this file: skip.
            log.debug("parse failed %s: %s", path, e)
            stats["files_skipped"] += 1
            continue

        stats["files"] += 1
        for hand in parser.getProcessedHands():
            stats["hands"] += 1
            hand.dbid_hands = synthetic_hand_id
            hand.playerIds = _raw_player_ids(hand, start=synthetic_hand_id * 1000)
            synthetic_hand_id -= 1
            if not getattr(hand, "handsplayers", None):
                hand.assembleHand()
            notes = generate_for_hand(hand, config=config, rule_set_ids=rule_set_ids, rule_ids=rule_ids)
            if not notes:
                _add_no_note_diagnostics(stats, hand, config, rule_set_ids=rule_set_ids)
                continue
            stats["matched_hands"] += 1
            stats["notes"] += len(notes)
            _add_rule_counts(stats, notes)
            player_names_by_id = {player_id: name for name, player_id in hand.playerIds.items()}
            stats["preview"].extend(_preview_row(note, player_names_by_id, hand) for note in notes)

    return stats


def backfill_database_preview(
    commit=False,
    config_file="HUD_config.xml",
    db=None,
    rule_set_ids=None,
    rule_ids=None,
    limit=1000,
    date_from=None,
    date_to=None,
    site_id=None,
    limit_type=None,
    status_callback=None,
):
    """Backfill PlayerAutoNotes by reading already-imported hands from the DB."""
    config = Configuration.Config(file=config_file)
    owns_db = db is None
    if owns_db:
        db = Database.Database(config)
    if hasattr(db, "ensure_feature_tables"):
        db.ensure_feature_tables()

    stats: dict[str, Any] = {
        "files": 0,
        "files_skipped": 0,
        "hands": 0,
        "matched_hands": 0,
        "notes": 0,
        "rule_sets": {},
        "rules": {},
        "preview": [],
        "source": "database",
    }

    for hand_id in _database_hand_ids(
        db,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
        site_id=site_id,
        limit_type=limit_type,
    ):
        stats["hands"] += 1
        if status_callback and stats["hands"] % 100 == 1:
            status_callback(f"Scanning database hand {stats['hands']} / {limit}")
        hand = load_hand_from_database(db, hand_id)
        if hand is None:
            stats["unmatched_hands"] = stats.get("unmatched_hands", 0) + 1
            continue
        if not any(hand.actions.get(street) for street in hand.actionStreets):
            stats["hands_without_actions"] = stats.get("hands_without_actions", 0) + 1
        notes = generate_for_hand(
            hand,
            config=config,
            rule_set_ids=rule_set_ids,
            rule_ids=rule_ids,
        )
        if not notes:
            _add_no_note_diagnostics(stats, hand, config, rule_set_ids=rule_set_ids)
            continue
        stats["matched_hands"] += 1
        stats["notes"] += len(notes)
        _add_rule_counts(stats, notes)
        player_names_by_id = {player_id: name for name, player_id in hand.playerIds.items()}
        stats["preview"].extend(_preview_row(note, player_names_by_id, hand) for note in notes)
        if commit:
            db.storePlayerAutoNotes(notes, doinsert=True)

    if commit:
        db.commit()
    if owns_db:
        db.close_connection()
    return stats


def backfill(paths, commit=False, config_file="HUD_config.xml", db=None, rule_set_ids=None, rule_ids=None):
    """Backfill PlayerAutoNotes. Returns a stats dict."""
    stats = backfill_preview(
        paths,
        commit=commit,
        config_file=config_file,
        db=db,
        rule_set_ids=rule_set_ids,
        rule_ids=rule_ids,
    )
    stats.pop("preview", None)
    return stats


def _import_settings(config) -> dict:
    settings = {"os": "windows" if os.name == "nt" else "linuxmac"}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    settings["cl_options"] = "autonotes-import-missing"
    return settings


def import_missing_paths(paths, config_file="HUD_config.xml", status_callback=None) -> dict:
    """Import hand-history paths using the legacy bulk importer."""
    config = Configuration.Config(file=config_file)
    importer = Importer.Importer(caller=None, settings=_import_settings(config), config=config)
    importer.setThreads(-1)
    importer.setCallHud(False)
    for path in paths:
        if status_callback:
            status_callback(f"Discovering importable files in {path}")
        importer.addBulkImportImportFileOrDir(path, site="auto")
    file_count = len(getattr(importer, "filelist", {}) or {})
    if file_count == 0:
        importer.clearFileList()
        if getattr(importer, "database", None):
            importer.database.close_connection()
        for writer in getattr(importer, "writerdbs", []) or []:
            writer.close_connection()
        return {
            "import_files": 0,
            "import_stored": 0,
            "import_duplicates": 0,
            "import_partial": 0,
            "import_skipped": 0,
            "import_errors": 0,
            "import_seconds": 0,
        }
    if status_callback:
        status_callback(f"Importing {file_count} hand-history files")

    imported_files_seen = 0

    def import_started(total_files):
        if status_callback:
            status_callback(f"Import started: {total_files} files")

    def import_progress(filename, hand_count):
        nonlocal imported_files_seen
        imported_files_seen += 1
        if status_callback:
            status_callback(
                f"Importing {imported_files_seen}/{file_count}: {os.path.basename(filename)} ({hand_count} DB hands)",
            )

    def import_finished():
        if status_callback:
            status_callback("Import finished; preparing automatic-note generation")

    if hasattr(importer, "set_progress_callbacks"):
        importer.set_progress_callbacks(import_started, import_progress, import_finished)
    stored, duplicates, partial, skipped, errors, elapsed = importer.runImport()
    importer.clearFileList()
    if getattr(importer, "database", None):
        importer.database.close_connection()
    for writer in getattr(importer, "writerdbs", []) or []:
        writer.close_connection()
    return {
        "import_files": file_count,
        "import_stored": stored,
        "import_duplicates": duplicates,
        "import_partial": partial,
        "import_skipped": skipped,
        "import_errors": errors,
        "import_seconds": elapsed,
    }


def backfill_with_optional_import(
    paths,
    commit=False,
    config_file="HUD_config.xml",
    rule_set_ids=None,
    rule_ids=None,
    import_missing=False,
    status_callback=None,
):
    """Backfill notes, optionally importing source hands before the write pass."""
    if commit and import_missing:
        import_stats = import_missing_paths(paths, config_file=config_file, status_callback=status_callback)
        if status_callback:
            status_callback("Generating automatic notes from imported hands")
        stats = backfill_preview(
            paths,
            commit=True,
            config_file=config_file,
            rule_set_ids=rule_set_ids,
            rule_ids=rule_ids,
            diagnose_unmatched=False,
            status_callback=status_callback,
        )
        stats.update(import_stats)
        return stats
    return backfill(
        paths,
        commit=commit,
        config_file=config_file,
        rule_set_ids=rule_set_ids,
        rule_ids=rule_ids,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill PlayerAutoNotes from hand-history files.")
    parser.add_argument("paths", nargs="*", help="Hand-history file(s) or directory(ies).")
    parser.add_argument("--commit", action="store_true", help="Write to the DB (default: dry run).")
    parser.add_argument("--config", default="HUD_config.xml", help="fpdb config file.")
    parser.add_argument("--from-db", action="store_true", help="Read already-imported hands directly from the DB.")
    parser.add_argument(
        "--import-missing",
        action="store_true",
        help="With --commit, import source hand histories before writing autonotes.",
    )
    parser.add_argument(
        "--raw-preview",
        action="store_true",
        help="Preview notes from hand-history files without requiring matching imported DB hands.",
    )
    parser.add_argument("--limit", type=int, default=1000, help="Maximum DB hands to scan with --from-db.")
    parser.add_argument("--date-from", help="Only scan DB hands on/after YYYY-MM-DD.")
    parser.add_argument("--date-to", help="Only scan DB hands on/before YYYY-MM-DD.")
    parser.add_argument("--site-id", type=int, help="Only scan DB hands for one numeric site id.")
    parser.add_argument("--limit-type", help="Only scan DB hands for one limit type, e.g. nl/pl/fl.")
    parser.add_argument("--list-rules", action="store_true", help="List configured autonote rule sets and exit.")
    parser.add_argument("--manifest", action="store_true", help="Print the legacy autonote parity manifest and exit.")
    parser.add_argument(
        "--ruleset",
        action="append",
        help="Limit generation to one ruleset id. May be repeated or comma-separated.",
    )
    parser.add_argument(
        "--rule",
        action="append",
        help="Limit generation to one rule id. May be repeated or comma-separated.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print machine-readable JSON stats.")
    args = parser.parse_args(argv)

    rule_set_ids = parse_id_filter(args.ruleset)
    rule_ids = parse_id_filter(args.rule)
    unknown_rule_sets = unknown_filter_ids(rule_set_ids, available_rule_set_ids())
    if unknown_rule_sets:
        parser.error(f"unknown ruleset id(s): {', '.join(unknown_rule_sets)}")
    unknown_rules = unknown_filter_ids(rule_ids, available_rule_ids())
    if unknown_rules:
        parser.error(f"unknown rule id(s): {', '.join(unknown_rules)}")

    if args.manifest:
        print(json.dumps(rule_manifest(), sort_keys=True))
        return 0

    if args.list_rules:
        config = Configuration.Config(file=args.config)
        summary = configured_rule_summary(config, rule_set_ids=rule_set_ids, rule_ids=rule_ids)
        if args.json_output:
            print(format_rule_summary_json(summary))
        else:
            print(format_rule_summary(summary))
        return 0
    if args.from_db and args.raw_preview:
        parser.error("--from-db and --raw-preview cannot be combined")
    if args.raw_preview and args.commit:
        parser.error("--raw-preview is read-only and cannot be combined with --commit")
    if args.import_missing and not args.commit:
        parser.error("--import-missing requires --commit")
    if args.import_missing and args.from_db:
        parser.error("--import-missing is only valid for hand-history file paths")
    if not args.from_db and not args.paths:
        parser.error("paths are required unless --list-rules is used")

    if args.from_db:
        stats = backfill_database_preview(
            commit=args.commit,
            config_file=args.config,
            rule_set_ids=rule_set_ids,
            rule_ids=rule_ids,
            limit=args.limit,
            date_from=args.date_from,
            date_to=args.date_to,
            site_id=args.site_id,
            limit_type=args.limit_type,
        )
        stats.pop("preview", None)
    elif args.raw_preview:
        stats = backfill_raw_preview(
            args.paths,
            config_file=args.config,
            rule_set_ids=rule_set_ids,
            rule_ids=rule_ids,
        )
        stats.pop("preview", None)
    else:
        stats = backfill_with_optional_import(
            args.paths,
            commit=args.commit,
            config_file=args.config,
            rule_set_ids=rule_set_ids,
            rule_ids=rule_ids,
            import_missing=args.import_missing,
        )
    if args.json_output:
        print(format_stats_json(stats, commit=args.commit, rule_set_ids=rule_set_ids, rule_ids=rule_ids))
        return 0
    mode = "WROTE" if args.commit else "DRY RUN (use --commit to write)"
    print(
        f"[{mode}] files={stats['files']} skipped={stats['files_skipped']} "
        f"hands={stats['hands']} matched={stats['matched_hands']} notes={stats['notes']}",
    )
    if (
        stats.get("unmatched_hands")
        or stats.get("matched_by_site_hand_only")
        or stats.get("hands_without_actions")
        or stats.get("unsupported_hands")
        or stats.get("disabled_hands")
        or stats.get("no_note_hands")
        or stats.get("raw_unmatched_notes")
    ):
        print(
            "diagnostics="
            f"unmatched={stats.get('unmatched_hands', 0)} "
            f"site_hand_only={stats.get('matched_by_site_hand_only', 0)} "
            f"without_actions={stats.get('hands_without_actions', 0)} "
            f"unsupported={stats.get('unsupported_hands', 0)} "
            f"disabled={stats.get('disabled_hands', 0)} "
            f"no_note={stats.get('no_note_hands', 0)} "
            f"raw_unmatched_notes={stats.get('raw_unmatched_notes', 0)}",
        )
    if stats.get("import_files") is not None:
        print(
            "import="
            f"files={stats.get('import_files', 0)} "
            f"stored={stats.get('import_stored', 0)} "
            f"duplicates={stats.get('import_duplicates', 0)} "
            f"partial={stats.get('import_partial', 0)} "
            f"skipped={stats.get('import_skipped', 0)} "
            f"errors={stats.get('import_errors', 0)}",
        )
    rule_counts = format_rule_counts(stats.get("rules", {}))
    if rule_counts:
        print(f"rules={rule_counts}")
    rule_set_counts = format_rule_counts(stats.get("rule_sets", {}))
    if rule_set_counts:
        print(f"rule_sets={rule_set_counts}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
