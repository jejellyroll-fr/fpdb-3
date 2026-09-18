"""Golden analytics corpus: fixtures, poker-semantic vocabulary, validation helpers.

The analytics epic (#310) adds an event model, a situation model, a query
engine and several new reports on top of the hand pipeline that already
exists. Every one of those layers is only as trustworthy as the poker
semantics underneath it, and those semantics are currently spread across
``DerivedStats``, ``HudCache`` and ``Stats`` with no single place that says
what a given situation is supposed to mean.

This module is the shared harness for the golden corpus that does say it:

* ``tests/fixtures/analytics/golden/`` holds a small, deterministic, hand
  written set of PokerStars NLHE hands, one file per scenario from #308.
* ``tests/fixtures/analytics/golden.json`` holds the manifest: for each
  scenario, the poker logic in prose, the expected money, the expected board
  and the semantic expectations per player -- plus the deviations where the
  current pipeline does not do what the poker word means.
* :func:`oracle_semantics` recomputes a handful of core preflop and flop
  semantics straight from the parsed action stream, so the stored flags are
  never the only witness of their own correctness.

The vocabulary in :data:`SEMANTIC_FIELDS` deliberately names poker concepts
(``cbet_flop_done``, ``fold_to_cbet_flop_done``, ``probe_turn_done``) rather
than schema columns. The schema is expected to move as the epic lands; the
poker meanings are not.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

from fpdb_3_legacy import Card

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "analytics" / "golden"
MANIFEST_PATH = GOLDEN_DIR.parent / "golden.json"

# Streets a hand block in the manifest can describe a board for.
BOARD_KEYS = ("flop", "turn", "river")

# Hand-level keys that belong to the whole hand rather than to a player.
HAND_KEYS = (
    "hand_id",
    "pot",
    "rake",
    "flop",
    "turn",
    "river",
    "players_dealt",
    "players_vpip",
    "players_at_flop",
    "players_at_turn",
    "players_at_river",
    "players_at_showdown",
)


class Field(NamedTuple):
    """One poker concept, and where the pipeline keeps it today."""

    column: str
    meaning: str
    kind: str = "bool"


# The semantic vocabulary. Keys are what the manifest talks about; the column
# is today's storage for it. When the epic moves a concept to another table,
# only this table changes -- the golden expectations do not.
SEMANTIC_FIELDS: dict[str, Field] = {
    # ---- preflop: participation ------------------------------------------
    "vpip": Field("street0VPI", "put money in voluntarily preflop"),
    "vpip_opportunity": Field("street0VPIChance", "was dealt in and could have played"),
    "pfr": Field("street0Aggr", "was the preflop aggressor (raised)"),
    "pfr_opportunity": Field("street0AggrChance", "could have raised preflop"),
    "rfi": Field("raisedFirstIn", "opened an unopened pot"),
    "rfi_opportunity": Field("raiseFirstInChance", "faced an unopened pot first"),
    "open_limp": Field("street0OpenLimp", "limped first into an unraised pot"),
    "over_limp": Field("street0Limp", "limped behind an earlier limper"),
    "limpers_faced": Field("street0_FaceLimpers", "number of limpers in front preflop", "int"),
    "calls_preflop": Field("street0Calls", "preflop calls made", "int"),
    "raises_preflop": Field("street0Raises", "preflop raises made", "int"),
    # ---- preflop: steal --------------------------------------------------
    "steal_opportunity": Field("stealChance", "could open from a steal seat with everyone folded"),
    "steal_done": Field("stealDone", "opened from a steal seat with everyone folded"),
    "steal_succeeded": Field("success_Steal", "raised a steal and took the pot down"),
    "folded_sb_to_steal": Field("foldedSbToSteal", "folded the small blind to a steal"),
    "folded_bb_to_steal": Field("foldedBbToSteal", "folded the big blind to a steal"),
    # ---- preflop: raises -------------------------------------------------
    "raise_made_bp_preflop": Field("val_p_raise_made_bp", "own preflop raise as basis points of the pot it faced", "int"),
    "raise_made_bp_flop": Field("val_f_raise_made_bp", "own flop raise as basis points of the pot it faced", "int"),
    "two_bet_done": Field("street0_2BDone", "made the second bet (opened) preflop"),
    "three_bet_opportunity": Field("street0_3BChance", "faced a raise, so could 3-bet"),
    "three_bet_done": Field("street0_3BDone", "made a preflop 3-bet"),
    "fold_to_three_bet_opportunity": Field("street0_FoldTo3BChance", "opened the pot, then faced a preflop 3-bet"),
    "fold_to_three_bet_done": Field("street0_FoldTo3BDone", "folded to a preflop 3-bet"),
    "four_bet_opportunity": Field("street0_4BChance", "faced a 3-bet having opened, so could 4-bet"),
    "cold_four_bet_opportunity": Field("street0_C4BChance", "faced a 3-bet without having opened"),
    "four_bet_done": Field("street0_4BDone", "made a preflop 4-bet"),
    "squeeze_opportunity": Field("street0_SqueezeChance", "faced a raise with callers behind, so could squeeze"),
    "squeeze_done": Field("street0_SqueezeDone", "squeezed preflop"),
    "faced_2bet_times": Field("cnt_p_2bet_facing", "times a preflop raise was faced", "int"),
    "faced_3bet_times": Field("cnt_p_3bet_facing", "times a preflop 3-bet was faced", "int"),
    # ---- streets reached / position --------------------------------------
    "saw_flop": Field("street1Seen", "reached the flop"),
    "saw_turn": Field("street2Seen", "reached the turn"),
    "saw_river": Field("street3Seen", "reached the river"),
    "saw_showdown": Field("sawShowdown", "reached showdown"),
    "showed_cards": Field("showed", "cards were shown"),
    "won_at_showdown": Field("wonAtSD", "won the hand at showdown"),
    "in_position_preflop": Field("street0InPosition", "acts last preflop"),
    "in_position_flop": Field("street1InPosition", "acts last on the flop"),
    "in_position_turn": Field("street2InPosition", "acts last on the turn"),
    "in_position_river": Field("street3InPosition", "acts last on the river"),
    "first_to_act_preflop": Field("street0FirstToAct", "acts first preflop"),
    "first_to_act_flop": Field("street1FirstToAct", "acts first on the flop"),
    "first_to_act_turn": Field("street2FirstToAct", "acts first on the turn"),
    "first_to_act_river": Field("street3FirstToAct", "acts first on the river"),
    # ---- postflop aggression --------------------------------------------
    "aggressor_flop": Field("street1Aggr", "took an aggressive action on the flop (bet or raise)"),
    "aggressor_turn": Field("street2Aggr", "took an aggressive action on the turn (bet or raise)"),
    "aggressor_river": Field("street3Aggr", "took an aggressive action on the river (bet or raise)"),
    "bets_flop": Field("street1Bets", "flop bets made", "int"),
    "bets_turn": Field("street2Bets", "turn bets made", "int"),
    "bets_river": Field("street3Bets", "river bets made", "int"),
    "raises_flop": Field("street1Raises", "flop raises made", "int"),
    "faced_raise_flop": Field("street1FaceRaise", "faced a flop raise"),
    "cbet_flop_opportunity": Field("street1CBChance", "reached the flop as preflop aggressor and could c-bet"),
    "cbet_flop_done": Field("street1CBDone", "c-bet the flop"),
    "cbet_turn_opportunity": Field("street2CBChance", "could barrel the turn after c-betting the flop"),
    "cbet_turn_done": Field("street2CBDone", "barrelled the turn after c-betting the flop"),
    "cbet_river_opportunity": Field("street3CBChance", "could barrel the river after barrelling the turn"),
    "cbet_river_done": Field("street3CBDone", "barrelled the river"),
    "delayed_cbet_turn_opportunity": Field("street2DelayedCBChance", "checked the flop as preflop aggressor and could bet the turn"),
    "delayed_cbet_turn_done": Field("street2DelayedCBDone", "delayed c-bet: checked the flop, bet the turn"),
    "probe_turn_opportunity": Field("street2ProbeChance", "could open the turn after the preflop aggressor checked the flop"),
    "probe_turn_done": Field("street2ProbeDone", "probed the turn"),
    "float_turn_opportunity": Field("flg_t_float_opp", "called a flop c-bet in position, so could float the turn"),
    "float_turn_done": Field("flg_t_float", "floated the turn after calling the flop c-bet in position"),
    "float_turn_defence_opportunity": Field("flg_t_float_def_opp", "faced a float bet on the turn"),
    "float_river_opportunity": Field("flg_r_float_opp", "could float the river"),
    "check_raise_flop_opportunity": Field("street1CheckCallRaiseChance", "checked the flop and could still raise"),
    "check_raise_flop_done": Field("street1CheckRaiseDone", "check-raised the flop"),
    "fold_to_cbet_flop_opportunity": Field("foldToStreet1CBChance", "faced a flop c-bet"),
    "fold_to_cbet_flop_done": Field("foldToStreet1CBDone", "folded to a flop c-bet"),
    "fold_to_cbet_turn_opportunity": Field("foldToStreet2CBChance", "faced a turn barrel"),
    "fold_to_cbet_turn_done": Field("foldToStreet2CBDone", "folded to a turn barrel"),
    "fold_to_cbet_river_opportunity": Field("foldToStreet3CBChance", "faced a river barrel"),
    "fold_to_cbet_river_done": Field("foldToStreet3CBDone", "folded to a river barrel"),
    "fold_to_other_raise_flop": Field("foldToOtherRaisedStreet1", "folded to a flop raise"),
    "fold_to_other_raise_turn": Field("foldToOtherRaisedStreet2", "folded to a turn raise"),
    "fold_to_other_raise_river": Field("foldToOtherRaisedStreet3", "folded to a river raise"),
    "folded_flop": Field("flg_f_fold", "folded on the flop"),
    "folded_turn": Field("flg_t_fold", "folded on the turn"),
    "folded_river": Field("flg_r_fold", "folded on the river"),
    # ---- all-in ----------------------------------------------------------
    "went_all_in": Field("wentAllIn", "was all-in at some point"),
    "all_in_preflop": Field("street0AllIn", "was all-in preflop"),
    "all_in_flop": Field("street1AllIn", "was all-in on the flop"),
    "all_in_turn": Field("street2AllIn", "was all-in on the turn"),
    "all_in_river": Field("street3AllIn", "was all-in on the river"),
    "faced_all_in_flop": Field("flg_faced_allin", "faced an all-in on the flop"),
    # ---- context ---------------------------------------------------------
    "position_code": Field("position", "position code: 0=button, 1=cutoff, ... S=small blind, B=big blind", "str"),
    "effective_stack_cents": Field("effStack", "effective stack in cents at hand start", "int"),
    "contributed_cents": Field("committed", "chips actually committed to the pot, in cents", "int"),
    "winnings_cents": Field("winnings", "chips won, in cents", "int"),
    "profit_cents": Field("totalProfit", "hand profit in cents", "int"),
    # ---- sizing / SPR ----------------------------------------------------
    "bet_made_bp_flop": Field("val_f_bet_made_bp", "own first flop bet as basis points of the pot it faced", "int"),
    "bet_made_bp_turn": Field("val_t_bet_made_bp", "own first turn bet as basis points of the pot it faced", "int"),
    "bet_made_bp_river": Field("val_r_bet_made_bp", "own first river bet as basis points of the pot it faced", "int"),
    "spr_flop": Field("val_f_spr", "effective stack / pot entering the flop, x100", "int"),
    "spr_turn": Field("val_t_spr", "effective stack / pot entering the turn, x100", "int"),
    "spr_river": Field("val_r_spr", "effective stack / pot entering the river, x100", "int"),
    # ---- situation responses (the enum family) ---------------------------
    "vs_preflop_3bet_response": Field("enum_p_3bet_action", "response when facing a preflop 3-bet: F/C/R", "enum"),
    "vs_preflop_4bet_response": Field("enum_p_4bet_action", "response when facing a preflop 4-bet: F/C/R", "enum"),
    "vs_squeeze_response": Field("enum_p_squeeze_action", "response when facing a squeeze: F/C/R", "enum"),
    "vs_cbet_flop_response": Field("enum_f_cbet_action", "response when facing a flop c-bet: F/C/R", "enum"),
    "vs_cbet_turn_response": Field("enum_t_cbet_action", "response when facing a turn barrel: F/C/R", "enum"),
    "vs_cbet_river_response": Field("enum_r_cbet_action", "response when facing a river barrel: F/C/R", "enum"),
    "vs_donk_flop_response": Field("enum_f_donk_action", "response when facing a flop donk bet: F/C/R", "enum"),
    "vs_donk_turn_response": Field("enum_t_donk_action", "response when facing a turn donk bet: F/C/R", "enum"),
    "vs_float_turn_response": Field("enum_t_float_action", "response to a turn barrel after calling the flop c-bet in position: F/C/R", "enum"),
    "vs_float_river_response": Field("enum_r_float_action", "response to a river barrel after calling the turn bet in position: F/C/R", "enum"),
    "folded_street": Field("enum_folded", "street the hand was folded on: N/P/F/T/R", "fold_street"),
}

# Human street names in the manifest vs. the letters enum_folded stores.
FOLD_STREET_LETTERS = {"none": "N", "preflop": "P", "flop": "F", "turn": "T", "river": "R"}

class GoldenDeviation(NamedTuple):
    """A place where the pipeline does not mean what the poker word means.

    ``column`` and ``observed_true_rows`` record the blast radius the deviation
    had when it was documented, so a fix moves a number the tests assert
    instead of quietly changing every stat built on the rule.
    """

    id: str
    note: str
    column: str | None = None
    observed_true_rows: int | None = None


class GoldenHand(NamedTuple):
    hand_id: int
    pot_cents: int
    rake_cents: int
    board: dict[str, list[str]]
    hand_expect: dict[str, Any]
    player_expect: dict[str, dict[str, Any]]


class GoldenScenario(NamedTuple):
    id: str
    file: str
    covers: tuple[str, ...]
    tags: tuple[str, ...]
    logic: tuple[str, ...]
    hands: tuple[GoldenHand, ...]


class GoldenManifest(NamedTuple):
    version: int
    room: str
    deviations: dict[str, GoldenDeviation]
    scenarios: tuple[GoldenScenario, ...]


def load_manifest(path: Path | None = None) -> GoldenManifest:
    """Read the golden manifest, indexed and validated for internal consistency."""
    raw = json.loads((path or MANIFEST_PATH).read_text())

    deviations = {}
    for entry in raw.get("deviations", []):
        deviations[entry["id"]] = GoldenDeviation(
            entry["id"],
            entry["note"],
            entry.get("column"),
            entry.get("observed_true_rows"),
        )

    scenarios = []
    for entry in raw["scenarios"]:
        hands = []
        for hand in entry["hands"]:
            hand_expect = {key: hand[key] for key in HAND_KEYS if key in hand}
            player_expect = {
                name: player["expect"] for name, player in hand.get("players", {}).items()
            }
            hands.append(
                GoldenHand(
                    hand_id=hand["hand_id"],
                    pot_cents=_cents(hand["pot"]),
                    rake_cents=_cents(hand["rake"]),
                    board={key: hand.get(key, []) for key in BOARD_KEYS},
                    hand_expect=hand_expect,
                    player_expect=player_expect,
                )
            )
        scenarios.append(
            GoldenScenario(
                id=entry["id"],
                file=entry["file"],
                covers=tuple(entry.get("covers", ())),
                tags=tuple(entry.get("tags", ())),
                logic=tuple(entry.get("logic", ())),
                hands=tuple(hands),
            )
        )
    return GoldenManifest(raw["version"], raw["room"], deviations, tuple(scenarios))


def _cents(amount: str | int | float) -> int:
    """Money in the manifest is written in chips; the database stores cents."""
    return int((Decimal(str(amount)) * 100).to_integral_value())


def golden_files() -> list[Path]:
    """Every corpus file on disk, in scenario order."""
    return sorted(GOLDEN_DIR.glob("*.txt"))


def scenario_file(scenario: GoldenScenario) -> Path:
    return GOLDEN_DIR / scenario.file


def decode_board(row: dict[str, Any]) -> list[str]:
    """Turn the five stored ``boardcard`` integers back into card strings."""
    cards = [Card.valueSuitFromCard(int(row[f"boardcard{i}"] or 0)) for i in range(1, 6)]
    return [card for card in cards if card not in ("", "0")]


def expectation_value(expectation: dict[str, Any], field: Field) -> tuple[Any, str | None]:
    """Return the value the pipeline should hold, and the deviation id if any.

    An expectation is either a plain value, or an object that says what poker
    says (``poker``) and what the pipeline stores instead (``current``), plus
    the id of the documented deviation. The second form is how the corpus
    keeps a known discrepancy reviewable instead of enshrining it silently.
    """
    if isinstance(expectation, dict) and "current" in expectation:
        return expectation["current"], expectation.get("deviation")
    return expectation, None


def coerce(field: Field, value: Any) -> Any:
    """Normalise one stored value so it can be compared with the manifest."""
    if field.kind == "bool":
        return bool(value)
    if field.kind == "int":
        return int(value or 0)
    if field.kind == "enum":
        return str(value or "N")
    if field.kind == "fold_street":
        return str(value or "N")
    return value


def expected_form(field: Field, value: Any) -> Any:
    """Normalise one manifest value to the same shape as :func:`coerce`."""
    if field.kind == "fold_street":
        return FOLD_STREET_LETTERS[str(value)]
    if field.kind == "bool":
        return bool(value)
    if field.kind == "int":
        return int(value)
    return value


def parse_golden_file(config: Any, path: Path) -> list[Any]:
    """Parse one corpus file without touching a database.

    The oracle reads the parsed action stream, not ``DerivedStats`` output:
    two independent readings of the same hand history is the point.
    """
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    return PokerStars(config=config, in_path=str(path), autostart=True).getProcessedHands()


def oracle_semantics(hand: Any) -> dict[str, dict[str, Any]]:
    """Recompute core poker semantics from the parsed action stream.

    Deliberately naive and independent of ``DerivedStats``: it answers the
    questions "did this player put money in voluntarily?", "who opened?",
    "who 3-bet?", "who c-bet the flop?", "who folded to it?" using nothing but
    the action list and the button. Where it disagrees with the stored flags,
    one of the two is wrong -- which is exactly what a golden corpus is for.
    """
    preflop = hand.actions.get("PREFLOP", [])
    flop = hand.actions.get("FLOP", [])
    players = [row[1] for row in hand.players]

    facts: dict[str, dict[str, Any]] = {
        name: {
            "vpip": False,
            "pfr": False,
            "rfi": False,
            "three_bet_done": False,
            "saw_flop": False,
            "cbet_flop_done": False,
        }
        for name in players
    }
    raises, folded_preflop = _oracle_preflop(preflop, facts)
    _oracle_flop(flop, raises[-1][1] if raises else None, folded_preflop, facts)
    return facts


VOLUNTARY_ACTIONS = ("calls", "bets", "raises", "completes")


def _oracle_preflop(
    preflop: list[Any], facts: dict[str, dict[str, Any]]
) -> tuple[list[tuple[int, str]], set[str]]:
    """Participation, opening, 3-betting and who folded, straight from the actions."""
    raises: list[tuple[int, str]] = []
    for index, action in enumerate(preflop):
        name, word = action[0], action[1]
        if name not in facts:
            continue
        if word in VOLUNTARY_ACTIONS:
            facts[name]["vpip"] = True
        if word in ("raises", "completes"):
            raises.append((index, name))

    # RFI: the first voluntary entrant of an unopened pot raised.
    for action in preflop:
        name, word = action[0], action[1]
        if word in VOLUNTARY_ACTIONS:
            facts[name]["rfi"] = word in ("raises", "completes")
            break

    for name in facts:
        facts[name]["pfr"] = any(raiser == name for _index, raiser in raises)

    if len(raises) >= 2:
        facts[raises[1][1]]["three_bet_done"] = True

    folded = {action[0] for action in preflop if action[1] == "folds"}
    return raises, folded


def _oracle_flop(
    flop: list[Any],
    preflop_aggressor: str | None,
    folded_preflop: set[str],
    facts: dict[str, dict[str, Any]],
) -> None:
    """Who reached the flop, and whether the preflop aggressor opened the betting."""
    for name in facts:
        facts[name]["saw_flop"] = bool(flop) and name not in folded_preflop

    if not flop:
        return
    first_aggressive = next((action for action in flop if action[1] in ("bets", "raises")), None)
    if first_aggressive is None or preflop_aggressor is None:
        return
    if first_aggressive[0] != preflop_aggressor:
        return
    facts[preflop_aggressor]["cbet_flop_done"] = first_aggressive[1] == "bets"


class GoldenCorpus(NamedTuple):
    """The imported corpus: hands, per-player rows and the HUD cache rows."""

    manifest: GoldenManifest
    hands: dict[int, dict[str, Any]]
    players: dict[int, dict[str, dict[str, Any]]]
    hud_cache: dict[str, dict[str, Any]]
    hand_count: int
    player_count: int

    def player_row(self, hand_id: int, name: str) -> dict[str, Any]:
        return self.players[hand_id][name]


def build_config(tmp_dir: Path) -> Any:
    """A throwaway SQLite configuration, shared by importing and parsing."""
    from fpdb_3_legacy.Configuration import Config

    db_file = tmp_dir / "golden.sqlite3"
    config = Config(file="HUD_config.xml")
    params = config.get_db_parameters()
    params.update(
        {
            "db-host": "localhost",
            "db-server": "sqlite",
            "db-port": 5432,
            "db-user": "test",
            "db-password": "test",
            "db-backend": 4,
            "db-databaseName": str(db_file),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    return config


def import_golden_corpus(tmp_dir: Path) -> GoldenCorpus:
    """Import every corpus file into a throwaway SQLite database and read it back."""
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    config = build_config(tmp_dir)
    db = Database(config)
    db.recreate_tables()

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()

    cursor = db.get_cursor()
    hands = _read_hands(cursor)
    players = _read_players(cursor, hands)
    hud_cache = _read_hud_cache(cursor)
    # Hands itself has no rake column: the rake is stored per player.
    for hand_id, rows in players.items():
        hands[hand_id]["rake"] = sum(row["rake"] or 0 for row in rows.values())

    return GoldenCorpus(
        manifest=load_manifest(),
        hands=hands,
        players=players,
        hud_cache=hud_cache,
        hand_count=len(hands),
        player_count=sum(len(rows) for rows in players.values()),
    )


HANDS_COLUMNS = (
    "id",
    "siteHandNo",
    "finalPot",
    "seats",
    "maxPosition",
    "playersVpi",
    "playersAtStreet1",
    "playersAtStreet2",
    "playersAtStreet3",
    "playersAtStreet4",
    "playersAtShowdown",
    "street0Raises",
    "street1Raises",
    "street2Raises",
    "street3Raises",
    "street4Raises",
    "boardcard1",
    "boardcard2",
    "boardcard3",
    "boardcard4",
    "boardcard5",
)


def _read_hands(cursor: Any) -> dict[int, dict[str, Any]]:
    cursor.execute(f"SELECT {', '.join(HANDS_COLUMNS)} FROM Hands")
    columns = [description[0] for description in cursor.description]
    return {
        int(row[columns.index("siteHandNo")]): dict(zip(columns, row))
        for row in cursor.fetchall()
    }


def _read_players(cursor: Any, hands: dict[int, dict[str, Any]]) -> dict[int, dict[str, dict[str, Any]]]:
    db_id_to_hand = {row["id"]: hand_id for hand_id, row in hands.items()}
    cursor.execute(
        "SELECT hp.*, p.name AS playerName FROM HandsPlayers hp JOIN Players p ON p.id = hp.playerId"
    )
    columns = [description[0] for description in cursor.description]
    rows: dict[int, dict[str, dict[str, Any]]] = {}
    for raw in cursor.fetchall():
        row = dict(zip(columns, raw))
        hand_id = db_id_to_hand[row["handId"]]
        rows.setdefault(hand_id, {})[row["playerName"]] = row
    return rows


def _read_hud_cache(cursor: Any) -> dict[str, dict[str, Any]]:
    cursor.execute("SELECT hc.*, p.name AS playerName FROM HudCache hc JOIN Players p ON p.id = hc.playerId")
    columns = [description[0] for description in cursor.description]
    rows: dict[str, list[dict[str, Any]]] = {}
    for raw in cursor.fetchall():
        row = dict(zip(columns, raw))
        rows.setdefault(row["playerName"], []).append(row)
    # A player can hold one cache row per position bucket; the corpus never
    # moves the button, so each player has exactly one. Sum defensively.
    return {name: _sum_cache_rows(entries) for name, entries in rows.items()}


CACHE_ROW_IDENTITY_COLUMNS = (
    "id",
    "playerId",
    "seats",
    "gametypeId",
    "tourneyTypeId",
    "position",
    "playerName",
)


def _sum_cache_rows(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Add one player's cache rows together.

    HudCache is keyed by position bucket as well as player, so a player who
    sat in several seats has several rows. Counters add; the columns that
    identify the row do not, and the enum columns are not counters at all.
    """
    totals: dict[str, Any] = {}
    for entry in entries:
        for key, value in entry.items():
            if key in CACHE_ROW_IDENTITY_COLUMNS or not isinstance(value, (int, float)):
                continue
            totals[key] = totals.get(key, 0) + value
    return totals
