"""Tests for the All-in or Fold HUD: its stats, its notes, and its profile."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as Configuration
from fpdb_3_legacy.AutoNotes import generate_for_hand
from fpdb_3_legacy.autonotes_aof import classify_all_in, describe_all_in, is_aof_omaha
from fpdb_3_legacy.stats_aof import aof_allin, aof_fold, aof_showdowns

REPO_ROOT = Path(__file__).resolve().parent.parent


class _AofHand:
    """The parts of a Hand an All-in or Fold note reads."""

    gametype = {"category": "aof_omaha", "base": "hold", "type": "ring"}
    # fpdb models this game with the flop as street zero: there is no preflop.
    actionStreets = ("BLINDSANTES", "FLOP", "TURN", "RIVER")
    handsplayers: dict = {}
    dbid_hands = 99

    def __init__(self, holecards: dict[str, list[str]], flop: list[str], actions: list[tuple]) -> None:
        self.actions = {"FLOP": actions}
        self.board = {"FLOP": flop}
        self._holecards = holecards
        self.players = [[seat, name, ""] for seat, name in enumerate(holecards, start=1)]
        self.playerIds = {name: 10 * seat for seat, name in enumerate(holecards, start=1)}

    def join_holecards(self, player: str, asList: bool = False) -> list[str]:  # noqa: FBT002, N803
        return self._holecards[player]


def _shove(player: str) -> tuple:
    return (player, "raises", "2.0", True)


def _hand(cards: list[str], flop: list[str]) -> _AofHand:
    return _AofHand({"hero": cards}, flop, [_shove("hero")])


# --- the stats ---------------------------------------------------------------


def test_calling_a_shove_counts_as_being_all_in() -> None:
    """Whoever calls is all in exactly as much as whoever shoved.

    The stacks are equal and there is no later street to bet, so reading the
    aggressor instead reported nothing for the caller: on the captured hand
    villain1 shoved and hero called, and aggression put hero at 0% with their
    whole stack in the middle.
    """
    caller = {1: {"vpip_opp": 1, "vpip": 1, "pfr_opp": 1, "pfr": 0}}

    fraction, _display, short, _long, _detail, _description = aof_allin(caller, 1)

    assert fraction == pytest.approx(1.0)
    assert short == "AI=100.0%"


def test_the_single_decision_is_reported_as_all_in_not_as_a_raise() -> None:
    """The engine already measures the right street; only the name was wrong.

    ``DerivedStats.vpip`` reads ``actionStreets[1]``, which for this game is
    the flop, so the columns are filled from the one decision there is. A box
    reading "VPIP/PFR" invites the reader to compare it with ranges from a
    game that has a preflop, and to read the gap as limping -- which cannot
    happen when the only options are all-in and fold.
    """
    # Deliberately not vpip_opp == n: six of the twenty-six hands are ones the
    # player was dealt into without the decision ever reaching them, and a
    # denominator taken from the hand count would quietly include those.
    stats = {1: {"pfr_opp": 20, "pfr": 9, "vpip_opp": 20, "vpip": 11, "sd": 8, "n": 26}}

    fraction, _display, short, _long, detail, _description = aof_allin(stats, 1)

    assert fraction == pytest.approx(11 / 20)
    assert short == "AI=55.0%"
    assert detail == "(11/20)"


def test_folding_is_read_from_the_money_not_from_a_recorded_fold() -> None:
    # Of the two options only one costs anything, so whoever was asked and put
    # nothing in has folded. A hand that ended before the decision reached the
    # player is neither a fold nor an opportunity.
    stats = {1: {"vpip_opp": 20, "vpip": 11, "n": 26}}

    fraction, _display, short, _long, detail, _description = aof_fold(stats, 1)

    # Out of the decisions taken, not out of the hands dealt.
    assert fraction == pytest.approx(9 / 20)
    assert short == "F=45.0%"
    assert detail == "(9/20)"


def test_the_showdown_count_does_not_claim_the_cards_were_read() -> None:
    """Reaching showdown is not the same as having the four cards.

    On the captured hand villain1 reached one holding four unknown cards, so
    a box promising a seen sample would have promised a hand nobody can look
    at. The stat is named for what it measures.
    """
    stats = {1: {"sd": 8, "n": 26}}

    value, display, short, _long, detail, _description = aof_showdowns(stats, 1)

    assert (value, display, short, detail) == (8.0, "8", "SD=8", "(8/26)")


@pytest.mark.parametrize("stat", [aof_allin, aof_fold, aof_showdowns])
def test_a_player_with_no_hands_reads_as_no_data(stat) -> None:
    # Not as 0%, which would say the player never shoves.
    _value, display, _short, _long, _detail, _description = stat({1: {}}, 1)

    assert display == "-"


# --- classifying a shove -----------------------------------------------------


def test_the_category_is_recognised() -> None:
    assert is_aof_omaha(_hand(["As", "Ks", "8h", "7c"], ["5s", "4s", "5h"]))

    plain = _hand(["As", "Ks", "8h", "7c"], ["5s", "4s", "5h"])
    plain.gametype = {"category": "omahahi", "base": "hold"}
    assert not is_aof_omaha(plain)


def test_straight_outs_are_counted_in_cards_not_in_ranks() -> None:
    """An open-ender is eight outs, and everyone calls it eight.

    Counting the two completing ranks instead would read as a gutshot and get
    the holding backwards -- the opposite of what the note is for.
    """
    detail = classify_all_in(_hand(["9h", "8c", "2d", "3s"], ["7s", "6d", "2c"]), "hero")

    assert detail["straight_outs"] == 8


def test_a_wrap_counts_every_rank_and_no_card_twice() -> None:
    """Where Omaha straight draws differ from Hold'em ones.

    J T 9 8 on 7 6 x is completed by four ranks -- a ten, a nine, an eight or
    a five -- which would be sixteen cards if the deck were untouched. Three
    of them are in the player's own hand, so thirteen can actually arrive, and
    a note claiming sixteen would be counting cards nobody can be dealt.
    """
    detail = classify_all_in(_hand(["Jh", "Th", "9d", "8s"], ["7s", "6d", "2c"]), "hero")

    assert detail["straight_outs"] == 13


def test_the_nut_flush_draw_is_told_from_the_others() -> None:
    """The difference between a draw worth a stack and one that wins small.

    A non-nut draw loses the biggest pots it enters, so a note that did not
    say which it was would flatten the read it exists to give.
    """
    nut = classify_all_in(_hand(["As", "Ks", "8h", "7c"], ["5s", "4s", "5h"]), "hero")
    weak = classify_all_in(_hand(["Th", "9h", "4d", "3s"], ["Ah", "Kh", "2c"]), "hero")

    assert nut["flush_draw"] == "nut flush draw"
    assert weak["flush_draw"] == "non-nut flush draw"


def test_one_suited_card_is_not_a_flush_draw() -> None:
    # Omaha plays exactly two hole cards, so a single one of the suit draws to
    # nothing however high it is.
    detail = classify_all_in(_hand(["As", "Kh", "8d", "7c"], ["5s", "4s", "5h"]), "hero")

    assert detail["flush_draw"] is None


def test_made_hands_are_named_from_two_hole_cards() -> None:
    trips = classify_all_in(_hand(["Ah", "Ac", "Kd", "Qs"], ["Ad", "7h", "2c"]), "hero")
    two_pair = classify_all_in(_hand(["Ah", "7c", "4d", "3s"], ["Ad", "7h", "2c"]), "hero")
    nothing = classify_all_in(_hand(["Qd", "Jd", "9h", "8c"], ["5s", "4s", "2h"]), "hero")

    assert trips["made"] == "trips"
    assert two_pair["made"] == "two pair"
    assert nothing["made"] == "no made hand"


def test_a_made_straight_or_flush_is_recognised() -> None:
    """Reasoning about which ranks pair the board never noticed either.

    A shove with the straight already in hand is the opposite read from a
    shove drawing at one, so a classifier that reported both as "no made hand"
    was worse than silent.
    """
    straight = classify_all_in(_hand(["8h", "7c", "Ad", "Kc"], ["6h", "5h", "4s"]), "hero")
    flush = classify_all_in(_hand(["Ah", "Kh", "2d", "3c"], ["7h", "5h", "4h"]), "hero")

    assert straight["made"] == "a straight"
    assert flush["made"] == "a flush"


def test_one_card_matching_a_paired_board_is_trips_not_a_boat() -> None:
    # Omaha plays exactly two hole cards: a single five with 5-5-4 down makes
    # three fives, and the second hole card cannot also pair the board.
    detail = classify_all_in(_hand(["5d", "Ah", "Kc", "Qs"], ["5h", "4s", "5s"]), "hero")

    assert detail["made"] == "trips"


def test_a_draw_is_not_reported_once_it_is_made() -> None:
    """Counting the cards that complete a straight already held counts the deck.

    A made straight was coming out with forty-five outs, which reads as a
    monster draw rather than as a monster.
    """
    detail = classify_all_in(_hand(["8h", "7c", "Ad", "Kc"], ["6h", "5h", "4s"]), "hero")

    assert detail["straight_outs"] == 0


def test_a_fold_is_not_classified() -> None:
    # A fold shows nothing, so there is nothing to record.
    folded = _AofHand({"hero": ["As", "Ks", "8h", "7c"]}, ["5s", "4s", "5h"], [("hero", "folds")])

    assert classify_all_in(folded, "hero") is None


def test_a_shove_whose_cards_were_not_shown_is_not_classified() -> None:
    """Most shoves are never shown, and a guess would read like a reading.

    A note built on two visible cards is indistinguishable, once written, from
    one built on four.
    """
    hidden = _AofHand({"hero": ["0x", "0x", "0x", "0x"]}, ["5s", "4s", "5h"], [_shove("hero")])

    assert classify_all_in(hidden, "hero") is None


# --- the note ----------------------------------------------------------------


def test_the_note_names_the_holding() -> None:
    """Every other rule says the same sentence to whoever triggers it.

    Here the whole value is in what was held: two shoves are only worth
    comparing if the note says which was which.
    """
    hand = _AofHand(
        {"hero": ["As", "Ks", "8h", "7c"], "villain": ["0x", "0x", "0x", "0x"]},
        ["5s", "4s", "5h"],
        [_shove("hero"), ("villain", "folds")],
    )

    (note,) = generate_for_hand(hand)

    assert note.player_id == 10
    assert note.note_text == "hero: all-in with a pair, nut flush draw, 4 straight outs"
    assert note.evidence["hole"] == "As Ks 8h 7c"
    assert note.evidence["flop"] == "5s 4s 5h"


def test_no_note_is_written_for_another_game() -> None:
    # The Omaha rule sets are preflop rule sets; this game has no preflop, and
    # its own rules must not fire anywhere else either.
    hand = _hand(["As", "Ks", "8h", "7c"], ["5s", "4s", "5h"])
    hand.gametype = {"category": "omahahi", "base": "hold", "type": "ring"}

    assert not [note for note in generate_for_hand(hand) if note.rule_id.startswith("aof_")]


def test_the_summary_reads_as_one_line() -> None:
    detail = classify_all_in(_hand(["As", "Ks", "8h", "7c"], ["5s", "4s", "5h"]), "hero")

    assert describe_all_in(detail) == "a pair, nut flush draw, 4 straight outs"


# --- the profile -------------------------------------------------------------


def test_the_hud_has_a_profile_for_the_game(tmp_path, monkeypatch) -> None:
    """Without one the HUD does not start: it logs and returns.

    Pointing the game at the PLO profile instead would put "VPIP/PFR" on a
    game with no preflop.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / ".fpdb"
    config_dir.mkdir()
    config_file = config_dir / "HUD_config.xml"
    shutil.copy(REPO_ROOT / "HUD_config.xml.example", config_file)

    config = Configuration.Config(file=str(config_file))
    params = config.get_supported_games_parameters("aof_omaha", "ring")

    assert params is not None
    assert params["game_stat_set"].name == "aof_default"
    stat_names = [stat.stat_name for stat in config.stat_sets["aof_default"].stats.values()]
    assert {"aof_allin", "aof_fold", "aof_showdowns"} <= set(stat_names)


def test_the_real_hand_reaches_player_auto_notes() -> None:
    """The whole chain on a captured hand, not on a hand written to pass.

    The earlier version of this test asserted against a Mock and against a
    fabricated action carrying ``all_in=True``. The real hand produced no
    notes at all: its blinds were posted twice and its shove totals were
    added on top of them, so no stack ever reached exactly zero -- and zero is
    what marks an action all-in.
    """
    import json

    from fpdb_3_legacy.coinpoker_hand_builder import build_hands
    from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig, build_fpdb_hand

    raw = json.loads((Path(__file__).parent / "data" / "coinpoker_aof_hand_events.json").read_text())
    (hand_data,) = build_hands([tuple(raw["join"]), *[tuple(e) for e in raw["hand"]]], "PLO4")
    hand = build_fpdb_hand(hand_data, config=HttpCaptureHandConfig(site_ids={"CoinPoker": 30, "default": 30}))

    # Everyone who shoved is all in for exactly their stack, and no further.
    assert [stack for stack in hand.stacks.values() if stack < 0] == []
    assert any(action[-1] is True for action in hand.actions["FLOP"])
    # And the blinds are posted once each.
    assert [action[1] for action in hand.actions["BLINDSANTES"]] == ["small blind", "big blind"]

    hand.playerIds = {player[1]: 10 * seat for seat, player in enumerate(hand.players, start=1)}
    hand.dbid_hands = 1
    hand.handsplayers = {}

    (note,) = generate_for_hand(hand)

    assert note.rule_id == "aof_omaha_all_in_shown"
    assert note.evidence["hole"] == "As Qh 8h 7c"
    assert note.note_text == "hero: all-in with a pair, 4 straight outs"


def test_the_note_icon_can_be_opened() -> None:
    """An icon that lights up but does not open is a worse HUD than none.

    ``player_note`` needs the click action wired, or the reader is told a note
    exists and given no way to read it.
    """
    import defusedxml.minidom as minidom

    document = minidom.parse(str(REPO_ROOT / "HUD_config.xml.example"))
    (profile,) = [ss for ss in document.getElementsByTagName("ss") if ss.getAttribute("name") == "aof_default"]
    (note_stat,) = [
        stat for stat in profile.getElementsByTagName("stat") if stat.getAttribute("_stat_name") == "player_note"
    ]

    assert note_stat.getAttribute("click") == "open_comment_dialog"


def _flop_first_records(bb_player: str, bb: str, shove: str) -> list[tuple]:
    """A capture whose first betting action is on the flop."""
    return [
        (
            "game.dealer_chat_action",
            "1",
            {
                "gameActionMessagesHistory": [
                    {"username": bb_player, "action": "BB", "actionAmount": bb, "roundName": "ANTE"},
                    {"username": bb_player, "action": "ALLIN", "actionAmount": shove, "roundName": "FLOP"},
                ],
            },
        ),
    ]


def test_only_all_in_or_fold_carries_its_blinds_onto_the_flop() -> None:
    """Every other game has a preflop round of its own.

    A capture of one that began at the flop must not carry blinds from a round
    that finished before the recording started: they would count as money
    already in, and the shove total -- which includes them -- would be charged
    twice, exactly the bug this fixed for All-in or Fold.
    """
    from decimal import Decimal

    from fpdb_3_legacy.coinpoker_hand_builder import _explicit_betting_actions

    records = _flop_first_records("hero", "0.25", "2.0")
    common = {"sb": Decimal("0.1"), "bb": Decimal("0.25"), "sb_name": None, "bb_name": "hero"}

    aof = _explicit_betting_actions(records, **common, is_aof=True)
    ordinary = _explicit_betting_actions(records, **common, is_aof=False)

    # In All-in or Fold the blind is already in, so the shove raises over it.
    (aof_shove,) = [action for action in aof if action.get("street") == "FLOP"]
    assert aof_shove == {"type": "raises", "player": "hero", "street": "FLOP", "to": "2.0"}

    # Elsewhere the flop starts with nothing in front of anyone.
    (plain_shove,) = [action for action in ordinary if action.get("street") == "FLOP"]
    assert plain_shove == {"type": "bets", "player": "hero", "street": "FLOP", "amount": "2.0"}


def test_folding_from_a_blind_is_a_decision_in_this_game() -> None:
    """Elsewhere folding a blind is giving up a preflop; here it is the hand.

    Built on the real initializer, which starts every player at
    ``street0VPIChance=True``: a fixture that starts them empty cannot show
    what the negative cases do, and the earlier version of this test could not
    see that a player the decision never reached was being counted as one who
    declined it.
    """
    from fpdb_3_legacy.DerivedStats import DerivedStats, _buildStatsInitializer

    class _Hand:
        handid = "1"
        actionStreets = ["BLINDSANTES", "FLOP", "TURN", "RIVER"]

        def __init__(self, category: str) -> None:
            self.gametype = {"category": category, "base": "hold"}
            self.actions = {
                "BLINDSANTES": [("sb", "small blind", 0.1), ("bb", "big blind", 0.25)],
                "FLOP": [("utg", "raises", 2.0, 2.0, 0, True), ("sb", "folds"), ("bb", "folds")],
            }

    def _chances(category: str) -> dict[str, Any]:
        derived = DerivedStats()
        derived.handsplayers = {name: _buildStatsInitializer() for name in ("utg", "sb", "bb", "unacted")}
        derived.hands = {}
        derived.vpip(_Hand(category))
        return {name: stats["street0VPIChance"] for name, stats in derived.handsplayers.items()}

    # The blinds folded, and that was their decision. The fourth player never
    # had one, so they are not in the denominator at all.
    assert _chances("aof_omaha") == {"utg": True, "sb": True, "bb": True, "unacted": False}
    # And every other game keeps the conventions it had, both ways round.
    assert _chances("omahahi") == {"utg": True, "sb": False, "bb": False, "unacted": True}


# --- the whole chain ----------------------------------------------------------


def _sqlite_database():
    """A real in-memory FPDB database, with automatic notes left enabled."""
    from unittest.mock import MagicMock

    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.SQL import Sql

    config = MagicMock()
    config.get_db_parameters.return_value = {
        "db-backend": 4,
        "db-server": "sqlite",
        "db-databaseName": ":memory:",
        "db-user": "",
        "db-password": "",
        "db-host": "",
        "db-port": "",
        "db-path": "",
    }
    config.get_import_parameters.return_value = {
        "saveActions": True,
        "callFpdbHud": False,
        "cacheSessions": False,
        "publicDB": False,
        "fastStoreHudCache": False,
        "sessionTimeout": 30,
    }
    config.get_general_params.return_value = {}
    config.get_site_id.return_value = 30
    database = Database(config, Sql(db_server="sqlite"))
    # The note generator reads its settings off the config; a Mock would answer
    # every question with another Mock, so it is given nothing and takes its
    # documented defaults.
    database.config = None
    return database


def _real_aof_hand():
    import json

    from fpdb_3_legacy.coinpoker_hand_builder import build_hands
    from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig, build_fpdb_hand

    raw = json.loads((Path(__file__).parent / "data" / "coinpoker_aof_hand_events.json").read_text())
    (hand_data,) = build_hands([tuple(raw["join"]), *[tuple(e) for e in raw["hand"]]], "PLO4")
    return build_fpdb_hand(hand_data, config=HttpCaptureHandConfig(site_ids={"CoinPoker": 30, "default": 30}))


def test_the_captured_hand_reaches_the_notes_table() -> None:
    """The whole chain, with nothing standing in for anything.

    Every earlier version of this test replaced part of it: a Mock database, or
    player ids assigned by hand rather than by the insert. Each substitution
    hid a real failure -- the notes were never generated on this path at all,
    and when they were, the hand they were generated from had blinds counted
    twice and no all-in flag to trigger on.
    """
    import json

    from fpdb_3_legacy.http_capture_hand_builder import import_fpdb_hand

    db = _sqlite_database()
    hand = _real_aof_hand()

    import_fpdb_hand(hand, db, file_id=1, doinsert=True, starting_hand_id=1)
    db.commit()

    cursor = db.get_cursor()
    cursor.execute(
        "select p.name, n.ruleId, n.ruleVersion, n.noteText, n.evidence "
        "from PlayerAutoNotes n join Players p on p.id = n.playerId",
    )
    rows = cursor.fetchall()

    assert len(rows) == 1
    name, rule_id, rule_version, note_text, evidence = rows[0]
    assert name == "hero"
    assert (rule_id, rule_version) == ("aof_omaha_all_in_shown", 1)
    assert note_text == "hero: all-in with a pair, 4 straight outs"
    assert json.loads(evidence)["hole"] == "As Qh 8h 7c"

    # The note is attached to the hand that was actually inserted.
    cursor.execute("select handId from PlayerAutoNotes")
    cursor2 = db.get_cursor()
    cursor2.execute("select id from Hands")
    assert cursor.fetchone()[0] == cursor2.fetchone()[0]


def _table_counts(db, *tables: str) -> dict[str, int]:
    counts = {}
    for table in tables:
        cursor = db.get_cursor()
        cursor.execute(f"select count(*) from {table}")  # noqa: S608 - fixed names
        counts[table] = cursor.fetchone()[0]
    return counts


def test_a_failing_rule_engine_costs_the_note_and_not_the_hand() -> None:
    """The reading of a hand is expendable; the hand is not.

    Generated among the inserts, one exception from the rule engine left a
    Hands row with no players and no actions behind it -- and the pump marks a
    hand imported before inserting it, so nothing ever came back for it. The
    notes are now worked out before anything durable is written.
    """
    from unittest.mock import patch

    from fpdb_3_legacy.http_capture_hand_builder import import_fpdb_hand

    db = _sqlite_database()
    hand = _real_aof_hand()

    with patch(
        "fpdb_3_legacy.AutoNotes.generate_for_hand",
        side_effect=RuntimeError("rule engine failed"),
    ):
        import_fpdb_hand(hand, db, file_id=1, doinsert=True, starting_hand_id=1)
    db.commit()

    counts = _table_counts(db, "Hands", "HandsPlayers", "HandsActions", "PlayerAutoNotes")
    assert counts["Hands"] == 1
    assert counts["HandsPlayers"] > 0, "the hand must be complete, not an orphan row"
    assert counts["HandsActions"] > 0
    assert counts["PlayerAutoNotes"] == 0


def test_a_failing_note_store_leaves_the_hand_complete() -> None:
    """A note failure, generation or persistence, never costs the hand.

    Letting the storage error through left exactly what generating the notes
    inside the transaction did: a Hands row with no players and no actions,
    which the pump never comes back for. A PlayerAutoNotes table that is
    missing, or briefly unavailable, would have destroyed every live hand that
    followed it.
    """
    from unittest.mock import patch

    from fpdb_3_legacy.http_capture_hand_builder import import_fpdb_hand

    db = _sqlite_database()
    hand = _real_aof_hand()

    with patch.object(
        type(db),
        "storePlayerAutoNotes",
        side_effect=RuntimeError("database refused the note"),
    ):
        import_fpdb_hand(hand, db, file_id=1, doinsert=True, starting_hand_id=1)

    counts = _table_counts(db, "Hands", "HandsPlayers", "HandsActions", "PlayerAutoNotes")
    assert counts["Hands"] == 1
    assert counts["HandsPlayers"] > 0, "the hand must be complete, not an orphan row"
    assert counts["HandsActions"] > 0
    assert counts["PlayerAutoNotes"] == 0


def test_a_failing_note_store_is_reported(capsys) -> None:
    # Visible and repeatable in the log: the note can be regenerated from the
    # hand that was stored.
    from unittest.mock import patch

    from fpdb_3_legacy.http_capture_hand_builder import import_fpdb_hand

    db = _sqlite_database()
    hand = _real_aof_hand()

    with patch.object(
        type(db),
        "storePlayerAutoNotes",
        side_effect=RuntimeError("database refused the note"),
    ):
        import_fpdb_hand(hand, db, file_id=1, doinsert=True, starting_hand_id=1)

    assert "automatic notes not stored" in capsys.readouterr().out


def test_a_failing_note_store_does_not_replay_an_unbounded_backlog() -> None:
    """A permanent note-table failure must stay O(one note per new hand)."""
    from fpdb_3_legacy.http_capture_hand_builder import _store_auto_notes

    class _FailingStore:
        def __init__(self) -> None:
            self.panbulk: list[str] = []
            self.attempted: list[tuple[str, ...]] = []

        def storePlayerAutoNotes(self, notes, _doinsert) -> None:
            self.panbulk.extend(notes)
            self.attempted.append(tuple(self.panbulk))
            raise RuntimeError("note table unavailable")

        def rollback(self) -> None:
            return

    db = _FailingStore()

    _store_auto_notes(db, ["first"], True)
    _store_auto_notes(db, ["second"], True)

    assert db.attempted == [("first",), ("second",)]
    assert db.panbulk == []
