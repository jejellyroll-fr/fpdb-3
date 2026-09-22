"""The Qt-free navigation contract for the spot-first Study Explorer (#360)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy import research_studies as studies
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel


@pytest.fixture
def model(tmp_path):
    return StudyExplorerModel(studies.builtin_studies(), tmp_path / "study-history.json")


def test_landing_categories_are_generated_from_the_registry(model) -> None:
    categories = model.categories()

    assert [category.id for category in categories] == [
        "preflop",
        "single-raised",
        "three-bet-pot",
        "four-bet-pot",
        "population",
    ]
    # Counted per game and format, because the library ships a Hold'em cash
    # pack (#359), a PLO one (#368) and a tournament one (#369), and the
    # landing page offers one scope at a time.
    holdem = model.categories("holdem", tournament=False)
    assert [category.study_count for category in holdem[:4]] == [5, 3, 2, 1]
    omaha = model.categories("omahahi", tournament=False)
    assert [category.study_count for category in omaha[:4]] == [5, 5, 4, 0]
    mtt = model.categories("holdem", tournament=True)
    assert [category.study_count for category in mtt[:4]] == [6, 4, 0, 0]
    assert categories[0].study_count == sum(
        scope[0].study_count for scope in (holdem, omaha, mtt)
    )


@pytest.mark.parametrize("text", ["cbet", "c-bet", "BB defend", "3bet"])
def test_search_uses_poker_aliases_and_panel_terms(model, text: str) -> None:
    assert model.search(text)


def test_search_can_be_narrowed_to_a_taxonomy_node(model) -> None:
    results = model.search("flop", "three-bet-pot")

    assert results
    assert all(study.path[1] == "three-bet-pot" for study in results)


def test_opening_a_study_inherits_context_without_changing_the_spot(model) -> None:
    selection = model.open_study(
        "srp_pfr_ip_flop",
        context_filters={
            "game": "holdem",
            "tournament": False,
            "max_seats": [6, 6],
            "hero": True,
            "player": "Hero",
            "stake_bb": [1.0, None],
            "date_from": "2026-01-01",
        },
        variable_values={"position": "btn"},
    )

    assert selection.available
    assert selection.study.id == "srp_pfr_ip_flop"
    assert selection.effective_filters["game"] == "holdem"
    assert selection.effective_filters["max_seats"] == [6, 6]
    assert selection.effective_filters["hero"] is True
    assert selection.effective_filters["tournament"] is False
    assert selection.effective_filters["player"] == "Hero"
    assert selection.effective_filters["stake_bb"] == [1.0, None]
    assert selection.effective_filters["date_from"] == "2026-01-01"
    assert selection.effective_filters["position"] == "btn"


def test_incompatible_game_is_explained_before_opening(model) -> None:
    selection = model.open_study("preflop_rfi", context_filters={"game": "omaha"})

    assert not selection.available
    assert selection.unavailable_reason
    assert "requires game='holdem'" in selection.unavailable_reason
    assert model.history.recent == []


def test_recent_studies_persist_only_ids_and_variables(model, tmp_path) -> None:
    model.open_study("preflop_rfi", variable_values={"position": "btn"})
    restored = StudyExplorerModel(studies.builtin_studies(), tmp_path / "study-history.json")

    assert [study.id for study in restored.recent_studies()] == ["preflop_rfi"]
    assert restored.history.recent[0] == {"study_id": "preflop_rfi", "variables": {"position": "btn"}}


def test_favorites_are_lightweight_ids(model) -> None:
    assert model.toggle_favorite("preflop_rfi")
    assert model.is_favorite("preflop_rfi")
    assert not model.toggle_favorite("preflop_rfi")
    assert not model.is_favorite("preflop_rfi")
