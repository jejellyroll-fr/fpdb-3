"""What the HUD Preferences editor decides without a window (#761).

Profile names, what follows a renamed profile, the unsaved-changes comparison
and where a selected item lives -- all on plain data, no Qt.
"""

from __future__ import annotations

from types import SimpleNamespace

import defusedxml.minidom
import pytest

from fpdb_3_legacy.hud_profiles import HudProfileRule
from fpdb_3_legacy.hud_situation import PanelRule
from fpdb_3_legacy.modern_hud_preferences import editor_state as es


# --- Names (B17) -------------------------------------------------------------
@pytest.mark.parametrize("name", ["", "   ", "\t"])
def test_an_empty_name_is_refused_and_says_so(name: str) -> None:
    assert es.name_problem(name, ["alice"]) == "A profile needs a name."


def test_a_taken_name_is_refused_and_named() -> None:
    problem = es.name_problem(" alice ", ["alice", "bob"])
    assert problem is not None
    assert '"alice"' in problem


def test_a_free_name_is_accepted() -> None:
    assert es.name_problem("carol", ["alice", "bob"]) is None


def test_keeping_its_own_name_is_not_a_clash() -> None:
    assert es.name_problem("alice", ["alice", "bob"], current="alice") is None
    assert es.name_problem("bob", ["alice", "bob"], current="alice") is not None


# --- Renaming ----------------------------------------------------------------
def test_a_renamed_profile_keeps_its_place_and_its_data() -> None:
    data = {"rows": 1}
    profiles = {"alice": {}, "bob": data, "carol": {}}
    es.rename_profile(profiles, "bob", "dave")
    assert list(profiles) == ["alice", "dave", "carol"]
    assert profiles["dave"] is data


def test_profile_rules_that_name_the_profile_follow_it() -> None:
    rules = [
        HudProfileRule(profile="bob", site="PokerStars", order=0),
        HudProfileRule(profile="alice", site="Winamax", order=1),
    ]
    renamed = es.rename_in_rules(rules, "bob", "dave")
    assert [r.profile for r in renamed] == ["dave", "alice"]
    assert renamed[0].site == "PokerStars"
    assert renamed[0].order == 0
    assert renamed[1] is rules[1]


def test_panel_rules_that_name_the_profile_follow_it_and_all_stays_all() -> None:
    rules = [PanelRule(panel="3bet", profile="bob"), PanelRule(panel="cbet", profile="all")]
    renamed = es.rename_in_rules(rules, "bob", "dave")
    assert [r.profile for r in renamed] == ["dave", "all"]
    assert renamed[0].panel == "3bet"


def test_a_chain_of_renames_remembers_the_name_in_the_file() -> None:
    renames: dict[str, str] = {}
    es.record_rename(renames, "alice", "bob")
    es.record_rename(renames, "bob", "carol")
    assert renames == {"carol": "alice"}
    es.record_rename(renames, "carol", "alice")
    assert not renames


def test_a_deleted_profile_gives_up_its_old_name() -> None:
    renames = {"bob": "alice"}
    es.forget_profile(renames, "bob")
    assert not renames


def test_each_profile_finds_the_stat_set_it_came_from() -> None:
    renames = {"bob": "alice"}
    assert es.file_name_for("bob", renames) == "alice"
    assert es.file_name_for("carol", renames) == "carol"
    # A new profile that took the old name gets a stat-set of its own.
    assert es.file_name_for("alice", renames) is None


def test_swapping_two_names_keeps_each_profile_on_its_own_stat_set() -> None:
    renames: dict[str, str] = {}
    es.record_rename(renames, "alice", "tmp")
    es.record_rename(renames, "bob", "alice")
    es.record_rename(renames, "tmp", "bob")
    assert es.file_name_for("alice", renames) == "bob"
    assert es.file_name_for("bob", renames) == "alice"


def test_a_new_profile_on_a_vacated_name_never_claims_its_stat_set() -> None:
    # alice -> bob, then a new "alice" is created and renamed to carol:
    # carol owns no stat-set, bob keeps alice's, and the game defaults follow bob.
    renames: es.Renames = {}
    es.record_rename(renames, "alice", "bob")
    es.record_rename(renames, "alice", "carol")
    assert es.file_name_for("bob", renames) == "alice"
    assert es.file_name_for("carol", renames) is None
    doc = defusedxml.minidom.parseString("<cfg><game_stat_set stat_set='alice'/></cfg>")
    es.follow_renames(doc, renames)
    assert doc.getElementsByTagName("game_stat_set")[0].getAttribute("stat_set") == "bob"
    # Renamed back to the vacated name, it still owns none.
    es.record_rename(renames, "carol", "alice")
    assert es.file_name_for("alice", renames) is None


def test_game_defaults_follow_a_renamed_profile() -> None:
    doc = defusedxml.minidom.parseString(
        "<cfg><supported_games><game game_name='holdem'>"
        "<game_stat_set game_type='ring' stat_set='alice'/>"
        "<game_stat_set game_type='tour' stat_set='carol'/>"
        "</game></supported_games></cfg>"
    )
    assert es.follow_renames(doc, {"bob": "alice"}) == 1
    bindings = [n.getAttribute("stat_set") for n in doc.getElementsByTagName("game_stat_set")]
    assert bindings == ["bob", "carol"]


def test_parsed_game_defaults_follow_a_renamed_profile() -> None:
    ring = SimpleNamespace(stat_set="alice")
    tour = SimpleNamespace(stat_set="carol")
    games = {"holdem": SimpleNamespace(game_stat_set={"ring": ring, "tour": tour})}
    es.follow_renames_in_games(games, {"bob": "alice"})
    assert (ring.stat_set, tour.stat_set) == ("bob", "carol")
    es.follow_renames_in_games(None, {"bob": "alice"})


# --- Unsaved changes (B8) ----------------------------------------------------
def _state(**overrides) -> es.EditorState:
    values = {
        "profiles": {"alice": {"rows": 1, "stats": [{"stat": "vpip"}]}},
        "popups": {},
        "settings": (True, True, 10),
        "profile_rules": [HudProfileRule(profile="alice")],
        "panel_rules": [PanelRule(panel="3bet")],
        "panel_rules_enabled": False,
        "panel_fallback": "",
    }
    values.update(overrides)
    return es.EditorState.capture(**values)


def test_an_identical_state_has_no_differences() -> None:
    assert es.differences(_state(), _state()) == []


def test_the_saved_state_is_a_copy_later_edits_do_not_reach() -> None:
    profiles = {"alice": {"rows": 1, "stats": []}}
    saved = es.EditorState.capture(profiles=profiles)
    profiles["alice"]["stats"].append({"stat": "pfr"})
    current = es.EditorState.capture(profiles=profiles, keep=False)
    assert es.differences(saved, current) == ["profiles"]


@pytest.mark.parametrize(
    ("change", "part"),
    [
        (
            {"profile_rules": [HudProfileRule(profile="alice"), HudProfileRule(profile="alice", site="Winamax")]},
            "profile_rules",
        ),
        ({"panel_rules": []}, "panel_rules"),
        ({"panel_rules": [PanelRule(panel="3bet", priority=2)]}, "panel_rules"),
        ({"panel_rules_enabled": True}, "panel_rules_enabled"),
        ({"panel_fallback": "core"}, "panel_fallback"),
        ({"settings": (False, True, 10)}, "settings"),
        ({"popups": {"p": {}}}, "popups"),
    ],
)
def test_every_part_save_writes_is_compared(change: dict, part: str) -> None:
    assert es.differences(_state(), _state(**change)) == [part]


def test_reordering_panel_rules_is_a_change() -> None:
    a, b = PanelRule(panel="3bet"), PanelRule(panel="cbet")
    assert es.differences(_state(panel_rules=[a, b]), _state(panel_rules=[b, a])) == ["panel_rules"]


def test_renumbering_profile_rules_alone_is_not_a_change() -> None:
    # ``order`` is not compared: deleting a rule renumbers the others.
    before = _state(profile_rules=[HudProfileRule(profile="alice", order=3)])
    after = _state(profile_rules=[HudProfileRule(profile="alice", order=0)])
    assert es.differences(before, after) == []


def test_the_differences_read_as_words() -> None:
    assert es.describe_differences(["profiles", "panel_rules"]) == "HUD profiles, panel rules"


# --- Selection (B11) and panel labels (B12) ----------------------------------
def test_an_item_is_located_by_identity_in_its_block() -> None:
    twin_a, twin_b = {"stat": "vpip", "row": 0, "col": 0}, {"stat": "vpip", "row": 0, "col": 0}
    text = {"label": "Pre", "rowcol": (1, 0)}
    profile = {
        "blocks": [
            {"rows": 2, "cols": 2, "stats": [twin_a], "texts": [], "hlines": []},
            {"rows": 2, "cols": 2, "stats": [twin_b], "texts": [text], "hlines": []},
        ]
    }
    assert es.locate(profile, twin_a) == (0, "stat")
    assert es.locate(profile, twin_b) == (1, "stat")
    assert es.locate(profile, text) == (1, "text")
    assert es.locate(profile, dict(twin_a)) is None


def test_an_item_of_a_flat_profile_has_no_block() -> None:
    stat = {"stat": "vpip", "row": 0, "col": 0}
    assert es.locate({"rows": 1, "cols": 1, "stats": [stat]}, stat) == (None, "stat")
    assert es.locate([stat], stat) == (None, "stat")


def test_nothing_is_located_without_an_item_or_a_profile() -> None:
    assert es.locate({"stats": []}, None) is None
    assert es.locate(None, {}) is None


def test_a_flat_profile_is_one_single_grid_entry() -> None:
    assert es.panel_labels({"rows": 1, "cols": 1, "stats": []}) == ["(single grid)"]
    assert es.panel_labels([]) == ["(single grid)"]


def test_only_a_panel_without_a_label_is_unnamed() -> None:
    profile = {"blocks": [{"label": "Core"}, {"label": ""}, {}]}
    assert es.panel_labels(profile) == ["Core", "(unnamed)", "(unnamed)"]
