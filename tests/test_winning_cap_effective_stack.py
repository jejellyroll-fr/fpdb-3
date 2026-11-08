"""Cap tables (ACR/WPN's "Miramar (Cap)") measure the capped effective stack (#734).

On a cap table what a player may put into one hand is capped -- 30 big blinds
in the samples seen -- so a player sitting with 100 big blinds on a 30-big-
blind cap table plays at most 30. Stack-based figures (the stored effective
stack, the per-action effective stack / SPR, and everything reading them:
stack-depth filters, push/fold classifications) must use min(stack, cap).
The stored starting stack stays the real one.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.action_events import (
    CAP_TABLE_BIG_BLINDS,
    cap_limit_cents,
    cap_remaining,
)
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.hud_situation import stack_bucket_for
from fpdb_3_legacy.WinningToFpdb import Winning

ROOT = Path(__file__).resolve().parents[1]
PLO8_CAP = ROOT / "tests" / "fixtures" / "hands" / "winning" / "plo8_cap_2026.txt"
MIRAMAR_CAP = (
    ROOT
    / "regression-test-files"
    / "cash"
    / "Winning"
    / "Flop"
    / "NLHE-9max-USD-0.01-0.02-201911.CASHID-TN-Miramar (Cap) GAMETYPE.txt"
)
REGULAR = ROOT / "regression-test-files" / "cash" / "Winning" / "NLHE-6max-USD-0.02-0.05-201608.HH00000000 G0.txt"

# plo8_cap_2026: $0.50/$1.00 "Vesta (Cap)", dave "caps $19.50" on top of his
# $10.50 raise -> the cap is $30 = 30 big blinds. Stacks: Hero $41.20,
# bob $25.00, carol $52.75, dave $38.40.
PLO8_BB_CENTS = 100
PLO8_CAP_CENTS = CAP_TABLE_BIG_BLINDS * PLO8_BB_CENTS  # $30

# Miramar (Cap): $0.01/$0.02, IrishPimp2233 "caps $0.55" on top of his $0.05
# raise -> the cap is $0.60 = 30 big blinds.
MIRAMAR_BB_CENTS = 2
MIRAMAR_CAP_CENTS = CAP_TABLE_BIG_BLINDS * MIRAMAR_BB_CENTS  # $0.60


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _parse_one(config: Config, path: Path):
    hands = Winning(config=config, in_path=str(path), autostart=True).getProcessedHands()
    assert len(hands) == 1
    return hands[0]


def _stats(config: Config, path: Path):
    hand = _parse_one(config, path)
    stats = DerivedStats()
    stats.getStats(hand)
    return hand, stats


# -- the cap itself ---------------------------------------------------------


def test_cap_is_known_from_the_tables_blinds(config: Config) -> None:
    for path, bb_cents in ((PLO8_CAP, PLO8_BB_CENTS), (MIRAMAR_CAP, MIRAMAR_BB_CENTS)):
        hand = _parse_one(config, path)

        assert hand.gametype["buyinType"] == "cap"
        assert cap_limit_cents(hand) == CAP_TABLE_BIG_BLINDS * bb_cents


def test_cap_falls_back_to_the_hands_caps_action() -> None:
    # No usable big blind: the "caps" action the parser recorded is the cap.
    hand = SimpleNamespace(gametype={"buyinType": "cap", "bb": None}, capAmount=Decimal("12.34"))

    assert cap_limit_cents(hand) == 1234


def test_no_cap_off_cap_tables() -> None:
    assert cap_limit_cents(SimpleNamespace(gametype={"buyinType": "regular", "bb": "1.00"})) == 0
    assert (
        cap_limit_cents(SimpleNamespace(gametype={"buyinType": "cap", "bb": "1.00"}, capAmount=Decimal("30"))) == 3000
    )
    assert cap_limit_cents(SimpleNamespace(gametype={})) == 0


def test_cap_remaining_is_the_cap_not_yet_reached() -> None:
    remaining = {"a": 5000, "b": 1200}
    committed = {"a": 1000, "b": 2800}

    assert cap_remaining(remaining, committed, 0) == remaining
    # a may still commit 3000-1000=2000 of the 5000 behind; b has 2800 in, so
    # only 200 of the cap is left to him.
    assert cap_remaining(remaining, committed, 3000) == {"a": 2000, "b": 200}
    assert cap_remaining(remaining, {"a": 1000, "b": 3000}, 3000) == {"a": 2000, "b": 0}


# -- the stored effective stack ----------------------------------------------


def test_effective_stack_is_min_stack_cap_on_the_cap_fixture(config: Config) -> None:
    _, stats = _stats(config, PLO8_CAP)

    # min(stack, $30 cap): Hero 41.20 -> 30, bob 25.00 stays 25, carol 52.75 ->
    # 30, dave 38.40 -> 30; then min(own, deepest opponent).
    assert {p: row["effStack"] for p, row in stats.handsplayers.items()} == {
        "Hero": PLO8_CAP_CENTS,
        "bob": 2500,
        "carol": PLO8_CAP_CENTS,
        "dave": PLO8_CAP_CENTS,
    }


def test_the_stored_starting_stack_stays_the_real_one(config: Config) -> None:
    _, stats = _stats(config, PLO8_CAP)

    assert {p: row["startCash"] for p, row in stats.handsplayers.items()} == {
        "Hero": 4120,
        "bob": 2500,
        "carol": 5275,
        "dave": 3840,
    }


def test_miramar_corpus_hand_uses_the_capped_effective_stack(config: Config) -> None:
    _, stats = _stats(config, MIRAMAR_CAP)

    # Every seated player is capped at $0.60; the sitting-out BrokenRec keeps 0.
    assert {p: row["effStack"] for p, row in stats.handsplayers.items()} == {
        "BrokenRec": 0,
        "Papabear2016": MIRAMAR_CAP_CENTS,
        "ccZORBAcc": MIRAMAR_CAP_CENTS,
        "Itspinkynigga": MIRAMAR_CAP_CENTS,
        "IrishPimp2233": MIRAMAR_CAP_CENTS,
    }
    assert {p: row["startCash"] for p, row in stats.handsplayers.items()} == {
        "BrokenRec": 0,
        "Papabear2016": 90,
        "ccZORBAcc": 140,
        "Itspinkynigga": 69,
        "IrishPimp2233": 266,
    }


def test_regular_tables_keep_the_full_stack(config: Config) -> None:
    hand, stats = _stats(config, REGULAR)

    assert hand.gametype["buyinType"] == "regular"
    assert cap_limit_cents(hand) == 0
    # 30bb at $0.05 would be 150 cents; the deepest stacks here far exceed it.
    assert max(row["effStack"] for row in stats.handsplayers.values()) > 150


# -- the per-action effective stack and SPR ----------------------------------


def test_per_action_effective_stack_never_exceeds_the_cap(config: Config) -> None:
    _, stats = _stats(config, PLO8_CAP)

    events = list(stats.handsactions.values())
    assert events
    assert all(0 <= ev["effectiveStack"] <= PLO8_CAP_CENTS for ev in events)
    # The first action of the hand: everyone may still commit the whole $30
    # cap, so the effective stack is the cap itself, 30bb in centi-bb.
    first = events[0]
    assert first["effectiveStack"] == PLO8_CAP_CENTS
    assert first["effectiveStackBB"] == PLO8_CAP_CENTS * 100 // PLO8_BB_CENTS
    # dave's cap raise to $30: he has $30 - $10.50 already in, so $19.50 of
    # cap remains, and Hero can only call the $5.50 he has left under the cap.
    cap_raise = next(ev for ev in events if ev["player"] == "dave" and ev["allIn"])
    assert cap_raise["effectiveStack"] == 550


def test_street_spr_uses_the_capped_stack(config: Config) -> None:
    _, stats = _stats(config, MIRAMAR_CAP)

    # Entering the flop the pot is $0.15 and each of the three players has
    # $0.05 in, leaving $0.55 of the $0.60 cap: SPR = 55 * 100 // 15 = 366.
    for player in ("Papabear2016", "ccZORBAcc", "IrishPimp2233"):
        row = stats.handsplayers[player]
        assert row["cnt_f_spr"] == 1
        assert row["val_f_spr"] == 55 * 100 // 15


def test_stack_depth_classification_reads_the_capped_stack(config: Config) -> None:
    _, stats = _stats(config, MIRAMAR_CAP)

    # Every decision of the hand is classified against the capped stack: at
    # most 30bb (3000 centi-bb), never the deep stack the full $2.66 of
    # IrishPimp2233 would suggest (6900 centi-bb, "deep").
    assert stats.situations
    assert max(s.effective_stack_bb for s in stats.situations) <= MIRAMAR_CAP_CENTS * 100 // MIRAMAR_BB_CENTS
    assert {s.stack_bucket for s in stats.situations} <= {"short", "medium"}
    # IrishPimp2233's open: $0.60 cap against Papabear2016's $0.59 of remaining
    # cap -> 59 cents = 2950 centi-bb = 29.5bb, a medium stack.
    event = next(ev for ev in stats.handsactions.values() if ev["player"] == "IrishPimp2233")
    assert event["effectiveStackBB"] == 59 * 100 // MIRAMAR_BB_CENTS
    assert stack_bucket_for(event["effectiveStackBB"] // 100) == "medium"
