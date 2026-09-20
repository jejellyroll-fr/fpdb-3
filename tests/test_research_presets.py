"""The shipped preset library (issue #330).

The library is *data*: JSON files under ``research_presets.d/`` holding queries
in the engine's own vocabulary plus the metadata a picker needs. These tests
hold the issue's acceptance criteria:

* a fresh install has useful presets, measured against a real count rather than
  "the file exists";
* every shipped preset is valid by the same vocabulary a user preset is checked
  against -- and compiles, so a filter *value* (a flag name, a position) is
  checked too, not only the filter name;
* the format carries no SQL and no Python;
* a bad pack is refused with its reason, which is what makes CI the gate;
* built-ins cannot be overwritten by a user save.

The compile check is the interesting one: it runs the shipped questions through
``analytics_query``'s own translation, so a pack that names a board texture flag
that no longer exists fails here instead of in front of a user.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy import player_situations as situations
from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy import research_presets as rp
from fpdb_3_legacy.analytics_query import (
    DIMENSIONS,
    FILTERS,
    IMPLIED_NUMERATORS,
    KNOWN_METRICS,
    compile_query,
)

# A minimal pack that is valid, so a failure in the invalid-pack tests cannot be
# blamed on the happy path.
_VALID_PRESET = {
    "id": "ok",
    "name": "A valid question",
    "description": "Counts decisions facing a flop c-bet.",
    "category": "postflop",
    "metric": "fold_frequency",
    "filters": {"street": "flop", "primary_situation": "facing_cbet"},
    "group_by": ["street"],
}


def _write_pack(directory: Path, presets, **overrides) -> Path:
    payload = {
        "schema_version": rp.PRESET_LIBRARY_SCHEMA_VERSION,
        "pack": "test-pack",
        "label": "Test pack",
        "description": "",
        "presets": presets,
        **overrides,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "test.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The shipped library itself.
# ---------------------------------------------------------------------------


def test_the_shipped_library_loads() -> None:
    presets = rp.load_library()
    assert len(presets) >= 20, "the issue asks for at least twenty useful presets"


def test_the_shipped_library_covers_the_categories_the_issue_names() -> None:
    present = set(rp.categories(rp.load_library()))
    for category in ("preflop", "postflop", "population", "range"):
        assert category in present


def test_every_shipped_preset_uses_the_engine_vocabulary() -> None:
    for preset in rp.load_library():
        assert preset.metric in KNOWN_METRICS
        assert set(preset.filters) <= set(FILTERS)
        assert set(preset.numerator) <= set(FILTERS)
        assert set(preset.group_by) <= set(DIMENSIONS)


def test_every_shipped_preset_compiles_with_its_values() -> None:
    """Names *and* values: a stale flag or seat name fails here, not in the UI."""
    for preset in rp.load_library():
        compiled = compile_query(rb.preset_to_query(preset.query), "?", "sqlite")
        assert compiled.sql and compiled.description


def test_shipped_presets_have_presentable_metadata() -> None:
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for preset in rp.load_library():
        assert preset.id not in seen_ids
        assert preset.name not in seen_names
        seen_ids.add(preset.id)
        seen_names.add(preset.name)
        assert preset.description
        assert preset.category in rp.CATEGORIES
        assert preset.recommended_view in rp.RESULT_VIEWS
        assert preset.min_sample is None or preset.min_sample > 0
        assert set(preset.variables) <= set(FILTERS)
        assert preset.tags


def test_the_shipped_pack_carries_no_sql_and_no_python() -> None:
    """The format is data: the loader can only ever name engine vocabulary."""
    path = next(rp.library_dir().glob("*.json"))
    text = path.read_text(encoding="utf-8").lower()
    for forbidden in ("select ", "insert ", "update ", "delete ", "import ", "exec(", "eval("):
        assert forbidden not in text


def test_no_shipped_preset_leaves_a_boolean_unset_that_should_not_be() -> None:
    """A saved preset states its booleans explicitly, unlike a fresh control."""
    for preset in rp.load_library():
        for name in ("hero", "hand_state_known", "hole_cards_known"):
            if name in preset.filters:
                assert isinstance(preset.filters[name], bool)


# ---------------------------------------------------------------------------
# A rate is measured over its opportunities, not over its own numerator.
# ---------------------------------------------------------------------------


def _shipped(preset_id: str) -> Any:
    preset = rp.find_preset(rp.load_library(), preset_id)
    assert preset is not None, f"{preset_id} is not shipped"
    return preset


def _names(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    return ()


def test_vpip_and_pfr_are_counted_per_hand_not_per_decision() -> None:
    """A player who limps and then calls a raise entered one hand, not two.

    Counting decisions would report two voluntary entries for that single hand,
    so both stats use the engine's per-hand frequency: the numerator and the
    denominator are distinct ``handId``s, which is what VPIP has always meant.
    """
    for preset_id in ("vpip_by_position", "pfr_by_position"):
        preset = _shipped(preset_id)
        assert preset.metric == "hand_frequency"
        assert preset.filters.get("street") == "preflop"
        compiled = compile_query(rb.preset_to_query(preset.query), "?", "sqlite")
        assert "COUNT(DISTINCT A.handId) AS opportunities" in compiled.sql
        assert "COUNT(DISTINCT CASE WHEN" in compiled.sql


def test_a_per_hand_rate_is_not_reported_over_decisions() -> None:
    """The two denominators differ exactly when a player acts twice in a street."""
    for preset_id in ("vpip_by_position", "pfr_by_position"):
        compiled = compile_query(
            rb.preset_to_query(_shipped(preset_id).query), "?", "sqlite",
        )
        assert "COUNT(*) AS opportunities" not in compiled.sql


def test_no_frequency_preset_measures_an_outcome_population() -> None:
    """"How often did they raise?" over a population that is already only
    raises is not a rate: it reads 100% however the player plays. The ones that
    name an outcome (``three_bet``, ``cbet``, ``open_raise``) say what was done,
    not what was faced, so a frequency must be asked over the ``*_spot`` /
    ``facing_*`` labels instead.
    """
    fixes_response = {
        rule.name: set(_names(rule.response)) for rule in situations.SITUATION_RULES if rule.response
    }
    for preset in rp.load_library():
        implied = IMPLIED_NUMERATORS.get(preset.metric)
        if implied is None:
            continue
        wanted = set(_names(implied.get("response")))
        for name in _names(preset.filters.get("primary_situation")):
            already = fixes_response.get(name)
            assert not (already and already <= wanted), (
                f"{preset.id}: {preset.metric} over the {name!r} population, which is already "
                f"only {sorted(already)} -- it would read 100%"
            )


# ---------------------------------------------------------------------------
# Loading, validation and refusal.
# ---------------------------------------------------------------------------


def test_a_pack_loads_from_a_directory(tmp_path: Path) -> None:
    _write_pack(tmp_path, [_VALID_PRESET])
    (pack,) = rp.load_packs(tmp_path)
    assert pack.id == "test-pack"
    (preset,) = pack.presets
    assert preset.id == "ok" and preset.pack == "test-pack"
    assert preset.query["metric"] == "fold_frequency"


def test_a_localized_name_resolves_with_an_english_fallback(tmp_path: Path) -> None:
    _write_pack(tmp_path, [{**_VALID_PRESET, "name": {"en": "English name", "fr": "Nom francais"}}])
    (preset,) = rp.load_library(tmp_path)
    assert preset.name == "English name"


def test_a_localized_name_falls_back_to_anything(tmp_path: Path) -> None:
    _write_pack(tmp_path, [{**_VALID_PRESET, "name": {"de": "Deutscher Name"}}])
    (preset,) = rp.load_library(tmp_path)
    assert preset.name == "Deutscher Name"


@pytest.mark.parametrize(
    "broken, message",
    [
        ({**_VALID_PRESET, "metric": "nope"}, "Unknown metric"),
        ({**_VALID_PRESET, "filters": {"nope": 1}}, "Unknown filters"),
        ({**_VALID_PRESET, "group_by": ["nope"]}, "Unknown dimensions"),
        ({**_VALID_PRESET, "category": "nope"}, "unknown category"),
        ({**_VALID_PRESET, "recommended_view": "nope"}, "unknown recommended_view"),
        ({**_VALID_PRESET, "min_sample": -1}, "min_sample"),
        ({**_VALID_PRESET, "sql": "SELECT 1"}, "unknown preset field"),
    ],
)
def test_a_bad_preset_is_refused_with_its_reason(tmp_path: Path, broken, message) -> None:
    _write_pack(tmp_path, [broken])
    with pytest.raises(ValueError, match=message):
        rp.load_packs(tmp_path)


def test_a_duplicate_preset_id_is_refused(tmp_path: Path) -> None:
    _write_pack(tmp_path, [_VALID_PRESET, dict(_VALID_PRESET)])
    with pytest.raises(ValueError, match="duplicate preset id"):
        rp.load_packs(tmp_path)


def test_a_future_schema_version_is_refused(tmp_path: Path) -> None:
    _write_pack(tmp_path, [_VALID_PRESET], schema_version=rp.PRESET_LIBRARY_SCHEMA_VERSION + 1)
    with pytest.raises(ValueError, match="schema_version"):
        rp.load_packs(tmp_path)


def test_an_unknown_pack_field_is_refused(tmp_path: Path) -> None:
    _write_pack(tmp_path, [_VALID_PRESET], handler="python")
    with pytest.raises(ValueError, match="unknown pack field"):
        rp.load_packs(tmp_path)


def test_a_broken_json_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        rp.load_packs(tmp_path)


def test_a_missing_directory_is_simply_empty(tmp_path: Path) -> None:
    assert rp.load_packs(tmp_path / "nope") == ()
    assert rp.load_library(tmp_path / "nope") == ()


# ---------------------------------------------------------------------------
# Read-only by construction, and explicitly switchable off.
# ---------------------------------------------------------------------------


def test_a_user_save_cannot_overwrite_a_shipped_preset(tmp_path: Path, monkeypatch) -> None:
    pack = _write_pack(tmp_path / "server-files", [_VALID_PRESET])
    shipped = tmp_path / "server-files" / pack.name
    before = shipped.read_text(encoding="utf-8")

    user = tmp_path / "config"
    store = rb.ResearchPresets(directory=user)
    store.save("A user preset", {"metric": "frequency", "filters": {"hero": True}})

    assert shipped.read_text(encoding="utf-8") == before
    assert json.loads((user / "research_presets.json").read_text())["presets"].keys() == {"A user preset"}


def test_builtin_names_are_recognized() -> None:
    presets = rp.load_library()
    name = presets[0].name
    assert rp.is_builtin_name(presets, name)
    assert not rp.is_builtin_name(presets, "definitely not a preset")


def test_the_library_can_be_disabled_explicitly(monkeypatch) -> None:
    assert rp.builtins_enabled() is True
    assert rp.builtin_presets()
    monkeypatch.setenv(rp.DISABLE_BUILTINS_ENV, "1")
    assert rp.builtins_enabled() is False
    assert rp.builtin_presets() == ()


def test_find_preset_by_id() -> None:
    presets = rp.load_library()
    target = presets[-1]
    assert rp.find_preset(presets, target.id) is target
    assert rp.find_preset(presets, "no-such-preset") is None


def test_categories_are_in_canonical_order() -> None:
    presets = rp.load_library()
    order = [rp.CATEGORIES.index(category) for category in rp.categories(presets)]
    assert order == sorted(order)
