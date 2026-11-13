"""PT4 parity of the HUD stats the Stats Guide pairs with PT4 stock stats (issue #751).

The PT4 formulas come from ``docs/pt4-stock-stat-coverage.md``, which
``pt4_import --coverage`` generates from PT4's own ``StatDefinitions.pt4``. Each
pair is run on the same random HudCache counters: a stat the guide calls "same
formula" must give PT4's number, and one it calls "different formula" must not,
so the guide cannot claim a parity the code does not have.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from fpdb_3_legacy import Stats
from fpdb_3_legacy.stats_guide_data import GUIDE

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    spec = importlib.util.spec_from_file_location("gen_stats_guide", ROOT / "tools" / "gen_stats_guide.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_stats_guide"] = module
    spec.loader.exec_module(module)
    return module


GEN = _generator()
ALIASES = GEN._hud_aliases()
PT4 = GEN.pt4_common_stats()
PAIRED = [(e["name"], e["pt4"]) for e in GUIDE["stats"] if e["origin"] == "native" and e["pt4"]]

# What the guide must keep saying; a change here is a change of parity, to be reviewed.
EXPECTED = {
    "vpip": "same formula",
    "pfr": "same formula",
    "three_B": "same formula",
    "f_3bet": "same formula",
    "cb1": "same formula",
    "f_cb1": "same formula",
    "wtsd": "same formula",
    "wmsd": "same formula",
    "steal": "same formula",
    "f_steal": "same formula",
    "agg_fact": "different formula",
    "a_freq1": "different formula",
    "a_freq_123": "different formula",
}


def test_every_translated_common_pt4_stat_is_paired() -> None:
    PT4_EQUIVALENTS = GEN.stats_guide_text.PT4_EQUIVALENTS  # noqa: N806

    for title in PT4:
        if title in PT4_EQUIVALENTS:
            assert any(pt4["stat"] == title for _name, pt4 in PAIRED), title


@pytest.mark.parametrize(("name", "parity"), sorted(EXPECTED.items()))
def test_guide_states_the_measured_parity(name: str, parity: str) -> None:
    pt4 = dict(PAIRED)[name]
    assert pt4["parity"] == parity
    if parity == "different formula":
        assert pt4["note"], f"{name}: a PT4 difference must be explained"


@pytest.mark.parametrize(("name", "parity"), sorted(EXPECTED.items()))
def test_fpdb_stat_matches_pt4_formula_when_the_guide_says_so(name: str, parity: str) -> None:
    pt4 = dict(PAIRED)[name]
    same, pairs = GEN.pt4_parity(getattr(Stats, name), pt4["formula"], ALIASES, trials=10)
    assert same == (parity == "same formula"), pairs


def test_pt4_formulas_come_from_the_coverage_report() -> None:
    for _name, pt4 in PAIRED:
        assert PT4[pt4["stat"]][0] == pt4["formula"]
