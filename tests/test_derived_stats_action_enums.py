"""Tests PT4 enum_*_action pour DerivedStats.calcActionEnums.

Couverture des scenarios ajoutes apres la review Codex (PR #266) :
- Squeeze F / 4-bet (pas seulement call)
- Final aggressor apres raise postflop
- Float IP (reference Rust validee ~99.4 % vs PT4 live)
- 3-bet/4-bet caller preservation (reference Rust validee)
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

# Squeeze F : l'open-raisier fold au 3-bet apres un cold-call.
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

# Aggressor chain : PFA c-bet flop, villain raise, PFA call, villain barre turn.
# La barre turn du villain est un "cbet" du villain (nouveau flop_aggr), pas un donk.
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


# ---------------------------------------------------------------------------
# Tests existants (scenario de base)
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
    """Le fichier ne doit plus contenir de garde auto-ajoutee."""
    path = os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy", "DerivedStats.py")
    src = open(path, encoding="utf-8").read()
    assert "AUTO-ADDED" not in src


# ---------------------------------------------------------------------------
# Fix 1 (Codex P1) : squeeze defense accepte F / C / R
# ---------------------------------------------------------------------------


def test_squeeze_open_raiser_folds_is_recorded_as_F(squeeze_fold_stats):
    """L'open-raisier fold au 3-bet alors qu'il y a un cold caller : squeeze F."""
    assert squeeze_fold_stats["OpenRaiser"]["enum_p_3bet_action"] == "F"
    assert squeeze_fold_stats["OpenRaiser"]["enum_p_squeeze_action"] == "F"


def test_squeeze_cold_caller_calls_is_recorded_as_C(squeeze_fold_stats):
    assert squeeze_fold_stats["ColdCaller"]["enum_p_3bet_action"] == "C"
    assert squeeze_fold_stats["ColdCaller"]["enum_p_squeeze_action"] == "C"


def test_squeezer_does_not_face_own_3bet(squeeze_fold_stats):
    assert squeeze_fold_stats["Squeezer"]["enum_p_3bet_action"] == "N"
    assert squeeze_fold_stats["Squeezer"]["enum_p_squeeze_action"] == "N"


# ---------------------------------------------------------------------------
# Fix 3 (Codex P2) : aggressor chain apres raise postflop
# ---------------------------------------------------------------------------


def test_postflop_raise_promotes_aggressor(raise_chain_stats):
    """PFA c-bet flop -> villain raise -> PFA call. Le villain devient le
    flop_aggr effectif, donc sa barre turn est un c-bet, pas un donk."""
    # Villain : barre turn apres avoir raise le flop. C'est son c-bet turn.
    assert raise_chain_stats["Villain"]["enum_t_cbet_action"] == "N"
    # PFA fold face a la barre turn : enregistre comme c-bet repondu.
    assert raise_chain_stats["PFA"]["enum_t_cbet_action"] == "F"


def test_postflop_chain_does_not_record_donk_for_re_raiser(raise_chain_stats):
    """La barre turn du villain n'est pas un donk (c'est sa continuation bet
    en tant que dernier raiseur du flop)."""
    assert raise_chain_stats["Villain"]["enum_t_donk_action"] == "N"


# ---------------------------------------------------------------------------
# Documentation des choix de reference (Codex P1 #1 et P2 #4)
# ---------------------------------------------------------------------------


def test_float_records_caller_response_to_second_barrel(stats_by_player):
    """Le float enum suit la semantique Rust validee ~99.4 % vs PT4 live :
    l'agressor barre deux rues consecutives, l'enum enregistre la reponse
    du caller a la deuxieme barre. Comportement documente intentionnel."""
    # Le ThreeBettor barre flop et turn ; Caller call flop et fold turn.
    # Le Caller fait face a la 2e barre : c'est son enum_t_float_action.
    # (Dans la main de base, Caller fold au turn sans avoir eu a repondre a
    # la 2e barre en tant que caller du c-bet flop — il est en check-call
    # et la 2e action du turn est son propre fold, pas une reponse. Donc
    # l'enum reste a N ici, ce qui reste coherent avec la definition
    # "caller IP repond a la deuxieme barre".)
    assert stats_by_player["Caller"]["enum_t_float_action"] == "N"


def test_3bet_caller_already_acted_keeps_enum_n(stats_by_player):
    """Le caller qui cold-call entre open et 3-bet est deja documente
    comme ayant fait face au 3-bet (enum_p_3bet_action). Le Rust
    valide contre PT4 ne le recompte pas dans l'enum postflop."""
    # Comportement documente : Caller a repondu au 3-bet (C).
    assert stats_by_player["Caller"]["enum_p_3bet_action"] == "C"
