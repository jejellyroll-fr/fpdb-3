"""PT4 enum_*_action tests for DerivedStats.calcActionEnums.

Scenarios added after the Codex review of PR #266:
- squeeze F / 4-bet, not only the call
- final aggressor after a postflop raise
- IP float (Rust reference, validated ~99.4% against PT4 live)
- 3-bet/4-bet caller preservation (validated Rust reference)
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

try:
    import PySide6  # noqa: F401
except ImportError:
    _mock = MagicMock()
    sys.modules["PySide6"] = _mock
    for _sub in ("QtCore", "QtGui", "QtWidgets"):
        sys.modules[f"PySide6.{_sub}"] = MagicMock()

from fpdb_3_legacy import Configuration as LegacyConfiguration
from fpdb_3_legacy import Hand as LegacyHandModule
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars as PokerStarsConverter

STARS_HAND = """PokerStars Hand #261999999999:  Hold'em No Limit (€0.01/€0.02 EUR) - 2026/06/07 18:00:00 CET
Table 'Enum Test' 6-max Seat #2 is the button
Seat 1: OpenRaiser (€2.00 in chips)
Seat 2: Caller (€2.00 in chips)
Seat 3: ThreeBettor (€2.00 in chips)
OpenRaiser: posts small blind €0.01
Caller: posts big blind €0.02
*** HOLE CARDS ***
Dealt to OpenRaiser [As Kd]
OpenRaiser: raises €0.05 to €0.06
Caller: calls €0.05
ThreeBettor: raises €0.14 to €0.20
OpenRaiser: folds
Caller: calls €0.14
*** FLOP *** [9h Kd 9d]
Caller: checks
ThreeBettor: bets €0.30
Caller: calls €0.30
*** TURN *** [9h Kd 9d] [2c]
Caller: checks
ThreeBettor: bets €0.60
Caller: folds
*** SUMMARY ***
Total pot €1.90 | Rake €0.09
Board [9h Kd 9d 2c]
Seat 1: OpenRaiser folded before Flop
Seat 2: Caller folded on the Turn
Seat 3: ThreeBettor collected €1.81
"""

# Squeeze F: the open-raiser folds to the 3-bet after a cold call.
STARS_SQUEEZE_FOLD = """PokerStars Hand #261999999990:  Hold'em No Limit (€0.01/€0.02 EUR) - 2026/06/07 18:00:00 CET
Table 'Squeeze Fold' 6-max Seat #3 is the button
Seat 1: OpenRaiser (€2.00 in chips)
Seat 2: ColdCaller (€2.00 in chips)
Seat 3: Squeezer (€2.00 in chips)
OpenRaiser: posts small blind €0.01
ColdCaller: posts big blind €0.02
*** HOLE CARDS ***
Dealt to OpenRaiser [7s 2c]
OpenRaiser: raises €0.05 to €0.06
ColdCaller: calls €0.05
Squeezer: raises €0.18 to €0.24
OpenRaiser: folds
ColdCaller: calls €0.18
*** FLOP *** [9h Kd 9d]
ColdCaller: checks
Squeezer: bets €0.30
ColdCaller: folds
*** SUMMARY ***
Total pot €0.68 | Rake €0.03
Board [9h Kd 9d]
Seat 1: OpenRaiser folded before Flop
Seat 2: ColdCaller folded on the Flop
Seat 3: Squeezer collected €0.65
"""

# Aggressor chain: PFA c-bets the flop, villain raises, PFA calls, villain fires
# the turn. That turn barrel is the villain's own c-bet as the new flop
# aggressor, not a donk bet.
STARS_RAISE_CHAIN = """PokerStars Hand #261999999980:  Hold'em No Limit (€0.01/€0.02 EUR) - 2026/06/07 18:00:00 CET
Table 'Raise Chain' 6-max Seat #3 is the button
Seat 1: PFA (€2.00 in chips)
Seat 2: Villain (€2.00 in chips)
Seat 3: ColdCaller (€2.00 in chips)
PFA: posts small blind €0.01
Villain: posts big blind €0.02
*** HOLE CARDS ***
Dealt to PFA [As Kd]
PFA: raises €0.05 to €0.06
Villain: calls €0.05
ColdCaller: calls €0.05
*** FLOP *** [9h Kd 9d]
PFA: bets €0.20
Villain: raises €0.40 to €0.60
PFA: calls €0.40
*** TURN *** [9h Kd 9d] [2c]
Villain: bets €0.80
PFA: folds
*** SUMMARY ***
Total pot €2.10 | Rake €0.10
Board [9h Kd 9d 2c]
Seat 1: PFA folded on the Turn
Seat 2: Villain collected €2.00
Seat 3: ColdCaller folded on the Flop
"""

# IP float by a non-blind player: the button calls the flop c-bet of the PFA
# (small blind), then raises the turn barrel. pos_code has to compare an integer
# position (button = 0) against a blind position ("S") without discarding either.
STARS_FLOAT_IP = """PokerStars Hand #261999999977:  Hold'em No Limit (€0.01/€0.02 EUR) - 2026/06/07 18:00:00 CET
Table 'Float IP' 6-max Seat #3 is the button
Seat 1: PFA (€2.00 in chips)
Seat 2: BBGuy (€2.00 in chips)
Seat 3: Floater (€2.00 in chips)
PFA: posts small blind €0.01
BBGuy: posts big blind €0.02
*** HOLE CARDS ***
Dealt to PFA [As Kd]
Floater: calls €0.02
PFA: raises €0.06 to €0.08
BBGuy: folds
Floater: calls €0.06
*** FLOP *** [9h Kd 2d]
PFA: bets €0.10
Floater: calls €0.10
*** TURN *** [9h Kd 2d] [7c]
PFA: bets €0.20
Floater: raises €0.40 to €0.60
PFA: folds
*** SUMMARY ***
Total pot €0.96 | Rake €0.04
Board [9h Kd 2d 7c]
Seat 1: PFA folded on the Turn
Seat 3: Floater collected €0.92
"""


def _build_stats(hand_text: str) -> dict:
    config = LegacyConfiguration.Config()
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                      encoding="utf-8")
    tmp.write(hand_text)
    tmp.close()
    converter = PokerStarsConverter(config, tmp.name)
    gametype = converter.determineGameType(hand_text)
    hand = LegacyHandModule.HoldemOmahaHand(
        config, converter, "PokerStars", gametype, hand_text, builtFrom="HHC"
    )
    calc = DerivedStats()
    calc.getStats(hand)
    return calc.getHandsPlayers()


@pytest.fixture()
def stats_by_player():
    return _build_stats(STARS_HAND)


@pytest.fixture()
def squeeze_fold_stats():
    return _build_stats(STARS_SQUEEZE_FOLD)


@pytest.fixture()
def raise_chain_stats():
    return _build_stats(STARS_RAISE_CHAIN)


@pytest.fixture()
def float_ip_stats():
    return _build_stats(STARS_FLOAT_IP)


# ---------------------------------------------------------------------------
# Base scenario
# ---------------------------------------------------------------------------


def test_open_raiser_folds_facing_3bet(stats_by_player):
    assert stats_by_player["OpenRaiser"]["enum_p_3bet_action"] == "F"
    assert stats_by_player["OpenRaiser"]["enum_p_4bet_action"] == "N"


def test_caller_facing_3bet_calls(stats_by_player):
    assert stats_by_player["Caller"]["enum_p_3bet_action"] == "C"
    assert stats_by_player["Caller"]["enum_p_squeeze_action"] == "C"


def test_threebettor_never_faced_any_preflop_raise(stats_by_player):
    assert stats_by_player["ThreeBettor"]["enum_p_3bet_action"] == "N"
    assert stats_by_player["ThreeBettor"]["enum_p_squeeze_action"] == "N"


def test_cbet_faced_on_flop_then_turn(stats_by_player):
    assert stats_by_player["Caller"]["enum_f_cbet_action"] == "C"
    assert stats_by_player["Caller"]["enum_t_cbet_action"] == "F"
    assert stats_by_player["ThreeBettor"]["enum_f_cbet_action"] == "N"


def test_folded_street_enum(stats_by_player):
    assert stats_by_player["OpenRaiser"]["enum_folded"] == "P"
    assert stats_by_player["Caller"]["enum_folded"] == "T"
    assert stats_by_player["ThreeBettor"]["enum_folded"] == "N"


def test_no_donk_no_float_in_this_hand(stats_by_player):
    for player in ("OpenRaiser", "Caller", "ThreeBettor"):
        assert stats_by_player[player]["enum_f_donk_action"] == "N"
        assert stats_by_player[player]["enum_t_float_action"] == "N"


def test_all_enums_default_to_n_when_absent(stats_by_player):
    for player in ("OpenRaiser", "Caller", "ThreeBettor"):
        for key in ("enum_face_allin", "enum_face_allin_action",
                    "enum_r_cbet_action", "enum_r_float_action",
                    "enum_r_donk_action", "enum_r_3bet_action",
                    "enum_r_4bet_action"):
            assert stats_by_player[player].get(key) == "N", (player, key)


def test_os_path_guard_removed():
    """The file must no longer carry an auto-added guard."""
    path = os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy", "DerivedStats.py")
    src = open(path, encoding="utf-8").read()
    assert "AUTO-ADDED" not in src


# ---------------------------------------------------------------------------
# Codex P1: squeeze defence accepts F / C / R
# ---------------------------------------------------------------------------


def test_squeeze_open_raiser_folds_is_recorded_as_F(squeeze_fold_stats):
    """The open-raiser folds to the 3-bet with a cold caller in: squeeze F."""
    assert squeeze_fold_stats["OpenRaiser"]["enum_p_3bet_action"] == "F"
    assert squeeze_fold_stats["OpenRaiser"]["enum_p_squeeze_action"] == "F"


def test_squeeze_cold_caller_calls_is_recorded_as_C(squeeze_fold_stats):
    assert squeeze_fold_stats["ColdCaller"]["enum_p_3bet_action"] == "C"
    assert squeeze_fold_stats["ColdCaller"]["enum_p_squeeze_action"] == "C"


def test_squeezer_does_not_face_own_3bet(squeeze_fold_stats):
    assert squeeze_fold_stats["Squeezer"]["enum_p_3bet_action"] == "N"
    assert squeeze_fold_stats["Squeezer"]["enum_p_squeeze_action"] == "N"


# ---------------------------------------------------------------------------
# Codex P2: aggressor chain after a postflop raise
# ---------------------------------------------------------------------------


def test_postflop_raise_promotes_aggressor(raise_chain_stats):
    """PFA c-bets the flop -> villain raises -> PFA calls.

    The villain becomes the effective flop aggressor, so the turn barrel is his
    c-bet rather than a donk bet.
    """
    # The villain fires that barrel, so he never faces it himself.
    assert raise_chain_stats["Villain"]["enum_t_cbet_action"] == "N"
    # PFA folds to it, which is a c-bet answered.
    assert raise_chain_stats["PFA"]["enum_t_cbet_action"] == "F"


def test_postflop_chain_does_not_record_donk_for_re_raiser(raise_chain_stats):
    """The villain's turn barrel is not a donk bet.

    He was the last player to raise the flop, so it is his continuation bet.
    """
    assert raise_chain_stats["Villain"]["enum_t_donk_action"] == "N"


# ---------------------------------------------------------------------------
# Reference behaviour kept on purpose (Codex P1 #1 and P2 #4)
# ---------------------------------------------------------------------------


def test_float_requires_the_caller_to_be_in_position(stats_by_player):
    """The float enum follows the Rust semantics validated ~99.4% vs PT4 live.

    The aggressor fires two streets in a row and the enum records the caller's
    answer to the second barrel -- but only when that caller is in position.
    """
    # ThreeBettor (button) barrels flop and turn; Caller (BB) calls the flop
    # then folds the turn. The barrelling pattern is there, but Caller is out of
    # position against the button, and PT4 excludes an OOP float, hence N.
    assert stats_by_player["Caller"]["enum_t_float_action"] == "N"


def test_3bet_caller_already_acted_keeps_enum_n(stats_by_player):
    """A cold caller between the open and the 3-bet already faced that 3-bet.

    enum_p_3bet_action records it, and the Rust reference validated against PT4
    does not count it again in the postflop enums.
    """
    # Documented behaviour: Caller answered the 3-bet with a call.
    assert stats_by_player["Caller"]["enum_p_3bet_action"] == "C"


# ---------------------------------------------------------------------------
# IP float by a non-blind player (regression from PR #266)
# ---------------------------------------------------------------------------


def test_float_ip_records_the_raise_of_a_non_blind_caller(float_ip_stats):
    """The button calls the flop c-bet then raises the turn barrel: enum = R.

    Guards against a position comparison that would drop integer positions
    (button = 0) and keep only the "S"/"B" blinds, which leaves the float enums
    inert on virtually every hand.
    """
    assert float_ip_stats["Floater"]["position"] == 0
    assert float_ip_stats["PFA"]["position"] == "S"
    assert float_ip_stats["Floater"]["enum_t_float_action"] == "R"


def test_float_ip_leaves_the_aggressor_at_n(float_ip_stats):
    """The aggressor is never the floater of his own barrel."""
    assert float_ip_stats["PFA"]["enum_t_float_action"] == "N"
    assert float_ip_stats["BBGuy"]["enum_t_float_action"] == "N"
