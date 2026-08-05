"""Tests for the All-in or Fold HUD: its stats, its notes, and its profile."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as Configuration
from fpdb_3_legacy.AutoNotes import generate_for_hand
from fpdb_3_legacy.autonotes_aof import classify_all_in, describe_all_in, is_aof_omaha
from fpdb_3_legacy.stats_aof import (
    aof_allin,
    aof_big_wrap13,
    aof_decision_ev,
    aof_fold,
    aof_full_house,
    aof_known_equity,
    aof_known_ev,
    aof_made,
    aof_nfd,
    aof_no_made,
    aof_non_nfd,
    aof_observed,
    aof_pair,
    aof_range_equity,
    aof_showdowns,
    aof_splash_freq,
    aof_splash_won,
    aof_straight,
    aof_trips,
    aof_two_pair,
    aof_weak,
    aof_wrap9,
)

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


def test_the_objective_profile_keeps_the_observed_denominator_visible() -> None:
    stats = {
        1: {
            "aof_obs": 18,
            "aof_no_made": 10,
            "aof_made": 8,
            "aof_nfd": 6,
            "aof_non_nfd": 2,
            "aof_wrap9": 8,
            "aof_big_wrap13": 3,
        },
    }

    assert aof_observed(stats, 1)[1:4] == ("18", "Obs=18", "observed all-ins=18")
    assert aof_no_made(stats, 1)[3:5] == ("no made hand 10/18 55.6%", "(10/18)")
    assert aof_made(stats, 1)[3:5] == ("made hand 8/18 44.4%", "(8/18)")
    assert aof_nfd(stats, 1)[3:5] == ("nut flush draw 6/18 33.3%", "(6/18)")
    assert aof_non_nfd(stats, 1)[3:5] == ("non-nut flush draw 2/18 11.1%", "(2/18)")
    assert aof_wrap9(stats, 1)[3:5] == ("wrap 9+ 8/18 44.4%", "(8/18)")
    assert aof_big_wrap13(stats, 1)[3:5] == ("big wrap 13+ 3/18 16.7%", "(3/18)")


def test_draw_categories_are_independent_not_a_partition() -> None:
    stats = {
        1: {
            "aof_obs": 1,
            "aof_no_made": 1,
            "aof_nfd": 1,
            "aof_wrap9": 1,
            "aof_big_wrap13": 1,
        },
    }

    assert [stat(stats, 1)[0] for stat in (aof_no_made, aof_nfd, aof_wrap9, aof_big_wrap13)] == [1.0] * 4


@pytest.mark.parametrize(
    ("stat", "key", "long_label"),
    [
        (aof_pair, "aof_pair", "pair"),
        (aof_two_pair, "aof_two_pair", "two pair"),
        (aof_trips, "aof_trips", "trips"),
        (aof_straight, "aof_straight", "straight"),
        (aof_full_house, "aof_full_house", "full house"),
    ],
)
def test_made_hand_distribution_uses_the_same_observed_sample(stat, key, long_label) -> None:
    stats = {1: {"aof_obs": 5, key: 2}}

    result = stat(stats, 1)

    assert result[0] == pytest.approx(0.4)
    assert result[3] == f"{long_label} 2/5 40.0%"
    assert result[4] == "(2/5)"


def test_zero_observations_are_not_reported_as_zero_percent() -> None:
    stats = {1: {"aof_obs": 0, "aof_no_made": 0}}

    assert aof_observed(stats, 1)[1] == "0"
    assert aof_no_made(stats, 1)[1] == "-"
    assert aof_no_made(stats, 1)[4] == "(0/0)"


def test_decision_ev_cells_stay_empty_without_a_complete_model() -> None:
    assert aof_weak({1: {}}, 1)[1] == "-"
    assert aof_decision_ev({1: {}}, 1)[1] == "-"
    assert (
        aof_weak(
            {1: {"aof_decision_ev": 0, "aof_weak": 0}},
            1,
        )[1]
        == "-"
    )
    assert (
        aof_decision_ev(
            {1: {"aof_decision_ev": 0, "aof_decision_ev_bb_ppm": 0}},
            1,
        )[1]
        == "-"
    )


def test_weak_ai_reports_only_confidently_negative_modeled_decisions() -> None:
    result = aof_weak(
        {1: {"aof_decision_ev": 11, "aof_weak": 3}},
        1,
    )

    assert result[0] == pytest.approx(3 / 11)
    assert result[1:5] == (
        "27.3",
        "W=27.3%",
        "Weak AI=27.3%",
        "(3/11)",
    )
    assert "upper 95%" in result[5]
    assert "uncertain" in result[5]


def test_decision_ev_is_the_average_pre_rake_value_in_big_blinds() -> None:
    result = aof_decision_ev(
        {
            1: {
                "aof_decision_ev": 4,
                "aof_decision_ev_bb_ppm": -2_000_000,
            },
        },
        1,
    )

    assert result[1:5] == (
        "-0.50",
        "EV=-0.50bb",
        "Decision EV=-0.50bb",
        "(4 modeled)",
    )
    assert "pre-rake" in result[5]


def test_known_card_stats_name_their_conditional_sample() -> None:
    stats = {
        1: {
            "aof_known": 2,
            "aof_known_equity_ppm": 1_100_000,
            "aof_known_ev_bb_ppm": 500_000,
        },
    }

    assert aof_known_equity(stats, 1)[1:5] == (
        "55.0",
        "EqK=55.0%",
        "known-card equity=55.0%",
        "(2 analyzed)",
    )
    assert aof_known_ev(stats, 1)[1:5] == (
        "+0.25",
        "EVact=+0.25bb",
        "EV vs actual callers=+0.25bb",
        "(2 analyzed)",
    )


@pytest.mark.parametrize("stat", [aof_known_equity, aof_known_ev])
def test_known_card_stats_show_no_data_without_a_complete_sample(stat) -> None:
    assert stat({1: {}}, 1)[1] == "-"
    assert (
        stat(
            {
                1: {
                    "aof_known": 0,
                    "aof_known_equity_ppm": 0,
                    "aof_known_ev_bb_ppm": 0,
                },
            },
            1,
        )[1]
        == "-"
    )


def test_population_range_equity_names_its_bias_and_historical_sample() -> None:
    stats = {1: {"aof_range": 4, "aof_range_equity_ppm": 2_200_000}}

    result = aof_range_equity(stats, 1)

    assert result[1:5] == (
        "55.0",
        "EqR=55.0%",
        "population-range equity=55.0%",
        "(4 modeled)",
    )
    assert "showdown-biased" in result[5]
    assert "earlier hands" in result[5]


def test_population_range_equity_is_blank_without_a_complete_model() -> None:
    assert aof_range_equity({1: {}}, 1)[1] == "-"
    assert (
        aof_range_equity(
            {1: {"aof_range": 0, "aof_range_equity_ppm": 0}},
            1,
        )[1]
        == "-"
    )


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
    assert params["game_stat_set"].name == "aof_advanced"
    # The parsed set keys its cells by row and column across the whole
    # profile, so a block layout -- where each block numbers its own cells
    # from one -- is lossy there by construction, exactly as it is for the
    # shipped PLO4 package. What the profile actually offers is asserted
    # against the blocks themselves, in the placement test below.
    assert config.stat_sets["aof_default"].stats
    assert {"aof_observed", "aof_weak", "aof_decision_ev"} <= {
        stat.stat_name for stat in config.stat_sets["aof_advanced"].stats.values()
    }
    assert "aof_profile" in config.popup_windows
    assert "aof_range_equity" in config.popup_windows["aof_profile"].pu_stats
    assert "aof_decision_ev" in config.popup_windows["aof_profile"].pu_stats


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

    notes = {note.note_text.split(":")[0]: note for note in generate_for_hand(hand)}

    # Both players who shoved were turned face up, so both are on record.
    assert set(notes) == {"hero", "villain1"}
    assert notes["villain1"].note_text == "villain1: all-in with two pair, non-nut flush draw"
    note = notes["hero"]
    assert note.rule_id == "aof_omaha_all_in_shown"
    assert note.evidence["hole"] == "As Qh 8h 7c"
    assert note.note_text == "hero: all-in with a pair, 4 straight outs"


def test_the_notes_can_still_be_opened_from_the_box_and_seen_in_the_popup() -> None:
    """The profile offers direct note access and the rich popup exposes it.

    Clicking either the player name or the dedicated note icon opens the note dialog.
    """
    import defusedxml.minidom as minidom

    document = minidom.parse(str(REPO_ROOT / "HUD_config.xml.example"))
    (profile,) = [ss for ss in document.getElementsByTagName("ss") if ss.getAttribute("name") == "aof_default"]
    clickable = [
        stat.getAttribute("_stat_name")
        for stat in profile.getElementsByTagName("stat")
        if stat.getAttribute("click") == "open_comment_dialog"
    ]

    assert clickable == ["playershort", "player_note"]

    (popup,) = [pu for pu in document.getElementsByTagName("pu") if pu.getAttribute("pu_name") == "aof_profile"]
    assert "player_note" in [s.getAttribute("pu_stat_name") for s in popup.getElementsByTagName("pu_stat")]


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

    # The hero's cards arrive dealt; an opponent's only at showdown, and both
    # are on record.
    assert {row[0] for row in rows} == {"hero", "villain1"}
    (row,) = [r for r in rows if r[0] == "hero"]
    name, rule_id, rule_version, note_text, evidence = row
    assert (rule_id, rule_version) == ("aof_omaha_all_in_shown", 1)
    assert note_text == "hero: all-in with a pair, 4 straight outs"
    assert json.loads(evidence)["hole"] == "As Qh 8h 7c"

    # The note is attached to the hand that was actually inserted.
    cursor.execute("select distinct handId from PlayerAutoNotes")
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


def test_an_opponents_hand_is_read_from_the_showdown_reveal() -> None:
    """Only the hero's cards arrive dealt; everyone else's come at showdown.

    Reading just ``game.hole_cards`` meant no opponent ever had a holding on
    record. Across six hundred captured hands the hero's cards were known in
    every one and no other player's in any, so every read that rests on what
    someone turns up with was empty for exactly the people it describes.
    """
    import json

    from fpdb_3_legacy.coinpoker_hand_builder import build_hands

    raw = json.loads((Path(__file__).parent / "data" / "coinpoker_aof_hand_events.json").read_text())
    (hand,) = build_hands([tuple(raw["join"]), *[tuple(e) for e in raw["hand"]]], "PLO4")

    by_player = {entry["player"]: entry for entry in hand["holecards"]}
    assert by_player["villain1"]["closed"] == ["Ks", "9s", "Td", "9d"]
    assert by_player["villain1"]["shown"] is True
    # The hero's own cards are not marked shown: they were dealt to us.
    assert by_player["hero"]["shown"] is False


def test_a_player_who_never_showed_has_no_holding_invented() -> None:
    # villain2 folded, so nothing was revealed and nothing is recorded.
    import json

    from fpdb_3_legacy.coinpoker_hand_builder import build_hands

    raw = json.loads((Path(__file__).parent / "data" / "coinpoker_aof_hand_events.json").read_text())
    (hand,) = build_hands([tuple(raw["join"]), *[tuple(e) for e in raw["hand"]]], "PLO4")

    assert "villain2" not in {entry["player"] for entry in hand["holecards"]}


def test_the_shows_up_with_marker_reads_without_being_read() -> None:
    """The notes' facts, in a form usable while a hand is in progress.

    "all-in with two pair, non-nut flush draw" is exact and useless mid-hand:
    one hand, in a sentence, in a window that has to be opened. The markers
    carry a whole history instead, and the observed count travels with them --
    four out of six is a coincidence and four out of sixty is a habit.
    """
    from fpdb_3_legacy.stats_aof import aof_summary

    stats = {1: {"aof_obs": 54, "aof_nfd": 10, "aof_wrap9": 8, "aof_two_pair": 6, "aof_no_made": 4}}

    _value, display, short, long_label, detail, _description = aof_summary(stats, 1)

    assert display == "NFD×10 W9×8 2p×6 air×4"
    assert short == "Shows NFD×10 W9×8 2p×6 air×4"
    assert long_label.endswith("over 54 observed all-ins")
    assert detail == "(54)"


def test_a_marker_never_runs_into_its_count() -> None:
    # "W9" and eight of them is not ninety-eight.
    from fpdb_3_legacy.stats_aof import aof_summary

    assert aof_summary({1: {"aof_obs": 9, "aof_wrap9": 8}}, 1)[1] == "W9×8"


def test_nothing_observed_shows_nothing_rather_than_zeroes() -> None:
    from fpdb_3_legacy.stats_aof import aof_summary

    assert aof_summary({1: {"aof_obs": 0}}, 1)[1] == "-"
    assert aof_summary({1: {"aof_obs": 12}}, 1)[1] == "-"


def test_a_marker_that_cannot_be_parsed_is_skipped() -> None:
    from fpdb_3_legacy.stats_aof import aof_summary

    result = aof_summary({1: {"aof_obs": 10, "aof_nfd": "bad_value"}}, 1)
    assert result[1] == "-"


def test_no_splash_hands_shows_no_data() -> None:

    assert aof_splash_won({1: {}}, 1)[1] == "-"
    assert aof_splash_won({1: {"aof_splash_seen": 0}}, 1)[1] == "-"
    assert aof_splash_freq({1: {}}, 1)[1] == "-"
    assert aof_splash_freq({1: {"aof_splash_seen": 0}}, 1)[1] == "-"


def test_the_profile_offers_every_cell_to_the_renderer() -> None:
    """A flat grid, because that is the one the classic HUD actually draws.

    A block layout parsed and validated, and drew nothing: blocks place
    themselves in pixels and number their cells from their own first row, and
    reading either as the other put the box's contents outside it. The data
    behind those cells was correct throughout -- the query returns 118
    observed all-ins for the hero and 54 for the largest opponent -- so the
    only thing between them and the screen was the shape of this profile.
    """
    document = Configuration.Config(file=str(REPO_ROOT / "HUD_config.xml.example"))
    profile = document.stat_sets["aof_default"]

    assert {stat.stat_name for stat in profile.stats.values()} == {
        "playershort",
        "player_note",
        "n",
        "aof_observed",
        "aof_showdowns",
        "aof_allin",
        "aof_fold",
        "aof_weak",
        "aof_decision_ev",
        "aof_no_made",
        "aof_two_pair",
        "aof_trips",
        "aof_nfd",
        "aof_splash_won",
        "aof_splash_freq",
    }
    assert "aof_profile" in document.popup_windows

    # The rich profile is strictly richer, which is what it is for. It used to
    # number three of its cells on row one, colliding with its own identity
    # row, so three statistics and the player's name overwrote each other.
    advanced = document.stat_sets["aof_advanced"]
    assert len(advanced.stats) > len(profile.stats)
    assert {stat.stat_name for stat in profile.stats.values()} <= {
        stat.stat_name for stat in advanced.stats.values()
    } | {"aof_showdowns"}


def test_the_deal_order_identifies_a_table_nobody_named() -> None:
    """The last thing left when the capture saw neither join nor catalogue.

    A capture that begins with the client already seated sees no lobby at all.
    All-in or Fold deals its flop before opening the betting and no other game
    does: measured over eighteen captured tables the two never overlap, ~98%
    against 0-11%. It is the order of the room's own packets, not a guess
    about how the players behaved.
    """
    from fpdb_3_legacy.coinpoker_hand_builder import looks_like_all_in_or_fold, note_deal_order

    flop_first = [("game.dealer_cards", "1", {}), ("game.user_turn", "1", {})]
    betting_first = [("game.user_turn", "1", {}), ("game.dealer_cards", "1", {})]
    shape: dict = {}

    for hand in range(4):
        note_deal_order(flop_first, "124415", str(hand), shape)
    # Four hands is not yet a table: a capture joined mid-hand looks like this.
    assert not looks_like_all_in_or_fold("124415", shape)

    note_deal_order(flop_first, "124415", "4", shape)
    assert looks_like_all_in_or_fold("124415", shape)

    for hand in range(20):
        note_deal_order(betting_first, "982246", str(hand), shape)
    assert not looks_like_all_in_or_fold("982246", shape)


def test_each_hand_counts_once_however_often_it_is_rebuilt() -> None:
    """A hand is rebuilt on every sweep until it is complete.

    Counting per build weighted the long hands heavily enough to drag a real
    All-in or Fold table from 77-against-1 down to 1007-against-378, below the
    threshold, and it went unrecognised for seventy hands.
    """
    from fpdb_3_legacy.coinpoker_hand_builder import note_deal_order

    flop_first = [("game.dealer_cards", "1", {}), ("game.user_turn", "1", {})]
    shape: dict = {}

    for _rebuild in range(10):
        note_deal_order(flop_first, "124415", "same-hand", shape)

    assert shape["124415"][:2] == [1, 0]


# --- the splash, paid beside the pot ------------------------------------------


def _splash_events(splash: float, winners: list[tuple], *, ev_cashout: bool = False) -> list[tuple]:
    """A settlement carrying a splash, shaped as the room sends it."""
    events: list[tuple] = [
        (
            "game.winnerInfo",
            "1",
            {
                "winnerDataList": [
                    {
                        "potId": 0,
                        "potAmountAfterRake": sum(paid for _n, paid, _m in winners),
                        "winnerDetails": {
                            "winnerList": [
                                {"playerName": name, "winAmountFromPot": paid} for name, paid, _m in winners
                            ],
                        },
                    },
                ],
            },
        ),
        (
            "game.cumulativeWinnerInfo",
            "1",
            {
                "splashPotAmount": splash,
                "winnersData": [{"userName": name, "isSplashPotWinner": marked} for name, _p, marked in winners],
            },
        ),
    ]
    if ev_cashout:
        events.insert(
            0,
            ("game.ev_chop_opted_action", "1", {"optedEvChopActionData": [{"optedForEVChop": True}]}),
        )
    return events


def test_the_splash_is_shared_in_proportion_to_what_was_taken() -> None:
    """Not equally, and not all to the winner of the biggest pot.

    On a captured hand of 2.00 the two marked players received 1.50 and 0.50 --
    the ratio of what they took from the settlement, 4.76 against 1.59.
    """
    from fpdb_3_legacy.coinpoker_hand_builder import _extract_splash_winnings

    events = _splash_events(2.0, [("jeje1976", 4.76, True), ("lilOmaha", 1.59, True)])

    paid = {entry["player"]: entry["amount"] for entry in _extract_splash_winnings(events)}

    assert paid == {"jeje1976": "1.50", "lilOmaha": "0.50"}


def test_a_lone_marked_player_takes_the_whole_splash() -> None:
    from fpdb_3_legacy.coinpoker_hand_builder import _extract_splash_winnings

    events = _splash_events(0.20, [("ajr4444", 0.65, True)])

    assert _extract_splash_winnings(events) == [{"player": "ajr4444", "amount": "0.20"}]


def test_an_unmarked_winner_receives_no_splash() -> None:
    # Winning a pot and receiving splash money are different things; the room
    # says which is which.
    from fpdb_3_legacy.coinpoker_hand_builder import _extract_splash_winnings

    events = _splash_events(0.40, [("winner", 1.00, False), ("marked", 1.00, True)])

    assert _extract_splash_winnings(events) == [{"player": "marked", "amount": "0.40"}]


def test_a_hand_with_an_accepted_ev_cashout_is_left_alone() -> None:
    """The one settlement shape the room's own figures could not be reproduced from.

    A player's equity is bought out instead of played, which moves money
    outside both the pot and the splash. Crediting it on a rule that does not
    describe it would put a number in the database that is known to be wrong.
    """
    from fpdb_3_legacy.coinpoker_hand_builder import _extract_splash_winnings

    events = _splash_events(1.0, [("SH1976", 6.18, True)], ev_cashout=True)

    assert _extract_splash_winnings(events) == []
