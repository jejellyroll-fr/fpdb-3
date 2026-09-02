"""Regressions for a HUD lost to a configuration that had simply aged.

A Winamax cash table was detected, attached and logged --

    HUD attach: table='Casablanca 04' site=Winamax hwnd=656448
                title='Winamax Casablanca 04' geometry=(361,250 898x669)

-- and then no HUD ever appeared, on any hand, with nothing in the log but

    HUD create refused: window 656448 already renders table 'Casablanca 04'
                        at generation 1

The user's configuration asked for the aux window ``Classic_HUD``, the spelling
of an older fpdb, while its own ``<aw>`` block defined ``ClassicHud``. Looking
that name up returned None, subscripting None raised out of the HUD
constructor, and because ``create_HUD`` claims the window *before* it builds,
the claim outlived the failure: every later hand was refused as a duplicate. So
one aged attribute cost the table its HUD permanently, and hid the reason after
the very first hand.

Nothing here is platform-specific -- the same configuration loses the HUD on
Windows, macOS and Linux alike.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock
from xml.dom import minidom

import pytest

from fpdb_3_legacy import HUD_main
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.hud_window_registry import HudWindowRegistry


def _config_with(aux_names: list[str]) -> Config:
    """A Config carrying only the aux window definitions a name is resolved against."""
    config = object.__new__(Config)
    config.file = "HUD_config.xml"
    config.aux_windows = {
        name: SimpleNamespace(name=name, module="Aux_Classic_Hud", **{"class": "ClassicHud"}) for name in aux_names
    }
    return config


# --------------------------------------------------------------------------
# Resolving an aux window name written by an older fpdb
# --------------------------------------------------------------------------


def test_an_older_spelling_still_finds_its_definition() -> None:
    """``Classic_HUD`` is what pre-rename configurations say; honour it."""
    config = _config_with(["ClassicHud", "mucked"])

    assert config._resolve_aux_name("Classic_HUD") == "ClassicHud"
    assert config.get_aux_parameters("Classic_HUD")["module"] == "Aux_Classic_Hud"


def test_an_exact_name_is_used_as_is() -> None:
    """A current configuration must resolve exactly as it always did."""
    config = _config_with(["ClassicHud", "classichud"])

    assert config._resolve_aux_name("ClassicHud") == "ClassicHud"


def test_an_aux_window_nothing_defines_still_resolves_to_nothing() -> None:
    """A genuine typo must not be healed into some unrelated window."""
    config = _config_with(["ClassicHud", "mucked"])

    assert config._resolve_aux_name("Mucked_Cards") is None
    assert config.get_aux_parameters("Mucked_Cards") is None


def test_an_ambiguous_respelling_is_not_guessed() -> None:
    """Two definitions differing only in spelling say nothing about which was meant."""
    config = _config_with(["Classic_Hud", "ClassicHud"])

    assert config._resolve_aux_name("CLASSICHUD") is None


# --------------------------------------------------------------------------
# Building the aux windows of a game whose configuration names an unknown one
# --------------------------------------------------------------------------


def _hud_for_aux_build(aux: str) -> object:
    from fpdb_3_legacy.Hud import Hud

    hud = object.__new__(Hud)
    hud.aux_windows = []
    hud.supported_games_parameters = {"aux": aux}
    hud.hud_context = SimpleNamespace(speed="normal")
    return hud


def test_an_undefined_aux_window_costs_only_itself(monkeypatch) -> None:
    """The rest of the table's aux windows must still be built."""
    import fpdb_3_legacy.Hud as hud_module

    built: list[str] = []

    class _Config:
        @staticmethod
        def get_aux_parameters(name):
            if name == "mucked":
                return {"module": "Mucked", "class": "Flop_Mucked"}
            return None

        @staticmethod
        def get_aux_windows():
            return ["ClassicHud", "mucked"]

    def _fake_import(_module, cls):
        def _make(*_a, **_k):
            built.append(cls)
            return SimpleNamespace(cls=cls)

        return _make

    monkeypatch.setattr(hud_module, "importName", _fake_import)
    hud = _hud_for_aux_build("Classic_HUD, mucked")

    hud._build_aux_windows(_Config())

    assert built == ["Flop_Mucked"]


def test_an_undefined_aux_window_names_itself_in_the_log(monkeypatch, caplog) -> None:
    """The first report of this said only that the window was already claimed."""
    import fpdb_3_legacy.Hud as hud_module

    class _Config:
        @staticmethod
        def get_aux_parameters(_name):
            return None

        @staticmethod
        def get_aux_windows():
            return ["ClassicHud", "mucked"]

    monkeypatch.setattr(hud_module, "importName", lambda *_a: None)
    hud = _hud_for_aux_build("Classic_HUD")

    with caplog.at_level("ERROR"):
        hud._build_aux_windows(_Config())

    assert "Classic_HUD" in caplog.text
    assert "ClassicHud" in caplog.text


# --------------------------------------------------------------------------
# A build that fails must hand its window back
# --------------------------------------------------------------------------


def _hud_main_for_create() -> HUD_main.HudMain:
    """A HudMain with only what create_HUD touches."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = {}
    hud_main._window_registry = HudWindowRegistry()
    hud_main._hud_generation = 0
    hud_main._fast_fold_tables = set()
    hud_main.config = MagicMock()
    hud_main.db_connection = MagicMock()
    hud_main._prepared_hands = {}
    hud_main.idle_create = MagicMock()
    return hud_main


def _creation_args(temp_key: str, window_id: int) -> HUD_main.HUDCreationArgs:
    return HUD_main.HUDCreationArgs(
        new_hand_id="hand1",
        table=SimpleNamespace(number=window_id, key=temp_key, hud=None),
        temp_key=temp_key,
        max_seats=6,
        poker_game="holdem",
        game_type="ring",
        stat_dict={},
        cards={},
        context=SimpleNamespace(speed="normal"),
        loading=True,
    )


def test_a_failed_build_releases_the_window(monkeypatch) -> None:
    """A claim outliving its failed build is what made one bad hand permanent."""
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=TypeError("'NoneType' is not subscriptable")))

    with pytest.raises(TypeError):
        hud_main.create_HUD(_creation_args("Casablanca 04", 656448))

    assert hud_main._window_registry.lookup(656448) is None
    assert "Casablanca 04" not in hud_main.hud_dict


def test_the_next_hand_can_still_build_a_hud_after_a_failed_one(monkeypatch) -> None:
    """The player's actual symptom: every hand after the first was refused."""
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=TypeError("boom")))
    with pytest.raises(TypeError):
        hud_main.create_HUD(_creation_args("Casablanca 04", 656448))

    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock()))
    hud_main.create_HUD(_creation_args("Casablanca 04", 656448))

    assert hud_main.idle_create.call_count == 1
    assert "Casablanca 04" in hud_main.hud_dict


def test_a_successful_build_keeps_its_claim(monkeypatch) -> None:
    """Releasing on failure must not release on success."""
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock()))

    hud_main.create_HUD(_creation_args("Casablanca 04", 656448))

    registration = hud_main._window_registry.lookup(656448)
    assert registration is not None
    assert registration.temp_key == "Casablanca 04"


# --------------------------------------------------------------------------
# The shipped configurations must not carry a dangling reference themselves
# --------------------------------------------------------------------------

CONFIG_TEMPLATES = ["HUD_config.xml", "HUD_config.xml.example"]


def _defined_names(doc: minidom.Document, tag: str) -> set[str]:
    return {node.getAttribute("name") for node in doc.getElementsByTagName(tag) if node.hasAttribute("name")}


def _dangling_references(path: pathlib.Path) -> list[str]:
    """Every name a configuration refers to but never defines."""
    doc = minidom.parse(str(path))
    defined = {tag: _defined_names(doc, tag) for tag in ("aw", "ss", "ls")}
    dangling = []

    for game in doc.getElementsByTagName("game"):
        game_name = game.getAttribute("game_name") or "?"
        for ref in (r.strip() for r in game.getAttribute("aux").split(",")):
            if ref and ref not in defined["aw"]:
                dangling.append(f"game {game_name!r}: aux={ref!r} has no <aw>")
        for attribute, tag in (("stat_set", "ss"), ("layout_set", "ls")):
            ref = game.getAttribute(attribute).strip()
            if ref and ref not in defined[tag]:
                dangling.append(f"game {game_name!r}: {attribute}={ref!r} has no <{tag}>")

    for site in doc.getElementsByTagName("site"):
        site_name = site.getAttribute("site_name") or "?"
        for attribute in ("layout_set_ring", "layout_set_tour"):
            ref = site.getAttribute(attribute).strip()
            if ref and ref not in defined["ls"]:
                dangling.append(f"site {site_name!r}: {attribute}={ref!r} has no <ls>")

    return sorted(set(dangling))


@pytest.mark.parametrize("template", CONFIG_TEMPLATES)
def test_a_shipped_configuration_defines_everything_it_refers_to(template: str) -> None:
    """A dangling name in a shipped template is what a stale user file looks like.

    The aux window is only the one that was noticed: a stat set or layout set
    the file names but never defines fails the same way, on the player's table
    rather than here.
    """
    path = pathlib.Path(__file__).resolve().parent.parent / template

    assert _dangling_references(path) == []
