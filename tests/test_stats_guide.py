"""The HUD Stats Guide must describe the stats the code supports (issue #751)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from fpdb_3_legacy.modern_hud_preferences import stat_catalog
from fpdb_3_legacy.stats_guide_data import GUIDE

ROOT = Path(__file__).resolve().parent.parent
BY_NAME = {(e["origin"], e["name"]): e for e in GUIDE["stats"]}


def _entry(name: str) -> dict:
    return next(e for e in GUIDE["stats"] if e["name"] == name and e["origin"] == "native")


def test_guide_lists_every_catalog_entry_and_nothing_else() -> None:
    catalog = stat_catalog.build_catalog()
    expected = {(("native" if e.origin == "classic" else e.origin), e.name) for e in catalog}
    assert set(BY_NAME) == expected


def test_every_entry_has_description_formula_and_sql() -> None:
    for entry in GUIDE["stats"]:
        for field in ("description", "formula", "sql"):
            assert entry[field].strip(), f"{entry['name']} has no {field}"


def test_picker_choices_all_resolve_to_a_documented_stat() -> None:
    catalog = stat_catalog.build_catalog()
    for _label, key in catalog.choices():
        entry = catalog.get(key)
        origin = "native" if entry.origin == "classic" else entry.origin
        assert (origin, entry.name) in BY_NAME


def test_wmsd_and_wmsf_are_distinct() -> None:
    wmsd, wmsf = _entry("wmsd"), _entry("WMsF")
    assert "sawShowdown" in wmsd["sql"] and "wonAtSD" in wmsd["sql"]
    assert "street1Seen" in wmsf["sql"] and "wonWhenSeenStreet1" in wmsf["sql"]
    assert "W$wsF" in wmsf["xml_titles"] and "W$wsF" not in wmsd["xml_titles"]
    assert "W$SD" in wmsd["xml_titles"]


def test_similar_names_stay_distinct() -> None:
    assert _entry("three_B")["abbr"] == "3B"
    assert BY_NAME[("registry", "three_bet")]["abbr"] == "3Bet"
    assert _entry("a_freq2")["abbr"] == "a2"
    assert "turn" in _entry("a_freq2")["description"].lower()


def test_estimates_and_deprecated_stats_are_flagged() -> None:
    assert _entry("overbet_frequency")["status"] == "estimate"
    assert _entry("resteal")["status"] == "estimate"
    assert _entry("iso")["status"] == "deprecated"


def test_ring_columns_carry_the_legacy_xml_titles() -> None:
    columns = {row["col_name"]: row for row in GUIDE["ring_columns"]}
    assert columns["wmsf"]["xml_title"] == "W$wsF"
    assert "wonWhenSeenStreet1" in columns["wmsf"]["sql"]
    assert "wonAtSD" in columns["wmsd"]["sql"]


def test_generated_files_are_not_stale() -> None:
    spec = importlib.util.spec_from_file_location("gen_stats_guide", ROOT / "tools" / "gen_stats_guide.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_stats_guide"] = module
    spec.loader.exec_module(module)
    data = module.build()
    assert module._render_module(data) == (ROOT / "fpdb_3_legacy" / "stats_guide_data.py").read_text(), (
        "run .venv/bin/python tools/gen_stats_guide.py"
    )
    assert module._render_markdown(data) == (ROOT / "docs" / "hud-stats-guide.md").read_text()


def test_guide_search_matches_abbreviation_and_xml_title() -> None:
    from fpdb_3_legacy import GuiStatsInfo as gui  # noqa: PLC0415

    assert gui._matches(_entry("WMsF"), "W$wsF")
    assert gui._matches(_entry("a_freq2"), "a2")
    assert not gui._matches(_entry("wmsd"), "W$wsF")
    assert sum(len(v) for v in gui._grouped_stats().values()) == len(GUIDE["stats"])


@pytest.mark.parametrize("name", ["vpip", "pfr", "wtsd"])
def test_core_stats_have_a_percentage_formula(name: str) -> None:
    assert "× 100" in _entry(name)["formula"]


def test_every_native_stat_has_a_title_and_a_detailed_description() -> None:
    for entry in GUIDE["stats"]:
        if entry["origin"] != "native":
            continue
        assert entry["title"].strip() and entry["detail"].strip(), entry["name"]
        assert len(entry["detail"]) > len(entry["description"]) or entry["name"] in {"playername", "blank"}, entry[
            "name"
        ]


def test_ratio_stats_spell_out_their_formula() -> None:
    for entry in GUIDE["stats"]:
        if entry["origin"] == "native" and "/" in entry["formula"] and entry["status"] != "deprecated":
            assert entry["formula_words"], entry["name"]
            assert "`" not in entry["formula_words"], entry["name"]


def test_wwsf_is_documented_as_an_alias_of_wmsf() -> None:
    assert _entry("wwsf")["alias_of"] == "WMsF"
    assert "Alias" in _entry("wwsf")["note"]
    assert _entry("fold_to_cbet_flop")["alias_of"] == "f_cb1"


def test_cb_ip_and_cb_oop_are_flagged_as_not_split_by_position() -> None:
    from fpdb_3_legacy import Stats  # noqa: PLC0415

    row = {"saw_f": 50, "street1InPosition": 20, "cb_1": 9, "cb_opp_1": 30}
    overall = Stats.cb1({1: row}, 1)[0]
    for name in ("cb_ip", "cb_oop"):
        assert Stats.do_stat({1: row}, 1, name)[0] == pytest.approx(overall)
        assert _entry(name)["status"] == "estimate"
        assert "cancels" in _entry(name)["note"]
