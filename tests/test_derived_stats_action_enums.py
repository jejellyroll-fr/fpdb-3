"""Tests PT4 enum_*_action pour DerivedStats.calcActionEnums."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# GUI optionnelle pour l'import du package legacy
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
import tempfile

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


@pytest.fixture()
def stats_by_player():
    config = LegacyConfiguration.Config()
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                      encoding="utf-8")
    tmp.write(STARS_HAND)
    tmp.close()

    converter = PokerStarsConverter(config, tmp.name)
    gametype = converter.determineGameType(STARS_HAND)
    hand = LegacyHandModule.HoldemOmahaHand(
        config, converter, "PokerStars", gametype, STARS_HAND, builtFrom="HHC"
    )
    calc = DerivedStats()
    calc.getStats(hand)
    return calc.getHandsPlayers()


def test_open_raiser_folds_facing_3bet(stats_by_player):
    # L'open-raiser fait face au 3-bet et fold.
    assert stats_by_player["OpenRaiser"]["enum_p_3bet_action"] == "F"
    # Pas de 4-bet face à lui.
    assert stats_by_player["OpenRaiser"]["enum_p_4bet_action"] == "N"


def test_caller_facing_3bet_calls(stats_by_player):
    # Le BB cold-call puis face au 3-bet : il call encore.
    assert stats_by_player["Caller"]["enum_p_3bet_action"] == "C"
    # Cold-caller présent entre open et 3-bet → situation de squeeze défendue.
    assert stats_by_player["Caller"]["enum_p_squeeze_action"] == "C"


def test_threebettor_never_faced_any_preflop_raise(stats_by_player):
    assert stats_by_player["ThreeBettor"]["enum_p_3bet_action"] == "N"
    assert stats_by_player["ThreeBettor"]["enum_p_squeeze_action"] == "N"


def test_cbet_faced_on_flop_then_turn(stats_by_player):
    # Caller (non-agresseur) répond au c-bet du flop : call.
    assert stats_by_player["Caller"]["enum_f_cbet_action"] == "C"
    # Puis face à la seconde barre au turn : fold.
    assert stats_by_player["Caller"]["enum_t_cbet_action"] == "F"
    # L'agresseur ne peut pas se confronter à son propre c-bet.
    assert stats_by_player["ThreeBettor"]["enum_f_cbet_action"] == "N"


def test_folded_street_enum(stats_by_player):
    assert stats_by_player["OpenRaiser"]["enum_folded"] == "P"
    assert stats_by_player["Caller"]["enum_folded"] == "T"
    assert stats_by_player["ThreeBettor"]["enum_folded"] == "N"


def test_no_donk_no_float_in_this_hand(stats_by_player):
    # Aucun donk (l'agresseur pré-flop parle en premier au flop).
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
    """Le fichier ne doit plus contenir de garde auto-ajoutée."""
    path = os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy", "DerivedStats.py")
    src = open(path, encoding="utf-8").read()
    assert "AUTO-ADDED" not in src
