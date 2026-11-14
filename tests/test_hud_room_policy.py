"""Room-specific HUD capabilities: what each room lets the HUD do at its tables (#756)."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fpdb_3_legacy import hud_room_policy as policy
from fpdb_3_legacy.hud_room_policy import CONSERVATIVE, UNRESTRICTED, HudCapabilities

SCHEMA = Path(__file__).resolve().parent.parent / "fpdb_3_legacy" / "database_schema.py"
SITE_ROW = re.compile(r"INSERT INTO Sites \(id,name,code\) VALUES \('(\d+)', '([^']+)', '([A-Z0-9]+)'\)")


def _sites_with_code(code: str) -> list[str]:
    return [name for _id, name, row_code in SITE_ROW.findall(SCHEMA.read_text(encoding="utf-8")) if row_code == code]


# --------------------------------------------------------------------------- #
# Identifying the room
# --------------------------------------------------------------------------- #


def test_every_ipoker_row_of_the_sites_table_is_an_ipoker_skin() -> None:
    # A skin reaches the HUD under its own name; a new 'IP' row must not slip
    # through as an unknown room with its own (conservative today) policy.
    skins = _sites_with_code("IP")
    assert "Betclic Poker" in skins and "Unibet Poker" in skins

    assert {site: policy.network_of(site) for site in skins} == dict.fromkeys(skins, "ipoker")


def test_every_pokerstars_row_of_the_sites_table_is_pokerstars() -> None:
    sites = _sites_with_code("PS")
    assert "PokerStars.DE" in sites

    assert {site: policy.network_of(site) for site in sites} == dict.fromkeys(sites, "pokerstars")


def test_the_unibet_client_is_not_the_historical_ipoker_skin() -> None:
    # Site 30 is the 2026 Relax Gaming client; site 87 the iPoker skin.
    assert policy.network_of("Unibet") == "unibet"
    assert policy.network_of("Unibet Poker") == "ipoker"
    assert policy.policy_for("Unibet").network == "unibet"
    assert policy.policy_for("Unibet Poker").network == "iPoker"


@pytest.mark.parametrize("site", ["  Betclic   Poker ", "BETCLIC POKER", "barrière poker"])
def test_skin_names_are_matched_whatever_their_case_and_spacing(site) -> None:
    assert policy.network_of(site) == "ipoker"


def test_the_2025_betclic_client_is_not_the_ipoker_skin() -> None:
    assert policy.network_of("Betclic") == "betclic"


# --------------------------------------------------------------------------- #
# The policies
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "site",
    ["PokerStars", "PokerStars.FR", "PokerStarsES", "Winamax", "iPoker", "PMU Poker", "FDJ Poker", "Bet365.fr Poker"],
)
def test_reviewed_restrictive_rooms_keep_the_static_hud_only(site) -> None:
    capabilities = policy.capabilities_at(site)

    assert capabilities.static_hud
    assert not capabilities.positional_hud
    assert not capabilities.dynamic_hud
    assert not capabilities.live_context


@pytest.mark.parametrize("site", ["Unibet", "GGPoker", "CoinPoker", "Americas Cardroom", "Some New Room", "", None])
def test_a_room_nobody_reviewed_gets_the_conservative_policy(site) -> None:
    assert policy.capabilities_at(site) == CONSERVATIVE
    assert policy.why_not("dynamic_hud", site) is not None
    assert policy.why_not("static_hud", site) is None


def test_the_reason_names_the_room() -> None:
    assert "PokerStars" in policy.why_not("positional_hud", "PokerStars.FR")
    assert "Winamax" in policy.why_not("dynamic_hud", "Winamax")
    assert "iPoker" in policy.why_not("positional_hud", "Betclic Poker")
    assert "GGPoker" in policy.why_not("dynamic_hud", "GGPoker")


def test_a_reviewed_room_gets_what_it_allows(reviewed_room) -> None:
    assert policy.capabilities_at(reviewed_room) == UNRESTRICTED
    assert policy.why_not("live_context", reviewed_room) is None


def test_a_configured_network_only_restricts(reviewed_room) -> None:
    # The hint comes from HUD_config.xml, which anyone can edit.
    assert policy.capabilities_at(reviewed_room, "iPoker") == CONSERVATIVE
    assert policy.capabilities_at("PokerStars.FR", reviewed_room) == CONSERVATIVE
    assert "iPoker" in policy.why_not("dynamic_hud", reviewed_room, "iPoker")


def test_the_network_hint_is_read_from_the_site_configuration() -> None:
    config = SimpleNamespace(
        supported_sites={
            "Bet365.fr Poker": SimpleNamespace(network="iPoker"),
            "Foo": SimpleNamespace(network="Unknown"),
        }
    )

    assert policy.network_hint(config, "Bet365.fr Poker") == "iPoker"
    assert policy.network_hint(config, "Foo") == ""
    assert policy.network_hint(config, "Missing") == ""
    assert policy.network_hint(None, "Bet365.fr Poker") == ""


def test_capabilities_combine_to_the_stricter() -> None:
    assert (UNRESTRICTED & CONSERVATIVE) == CONSERVATIVE
    assert (UNRESTRICTED & UNRESTRICTED) == UNRESTRICTED


def test_dynamic_panels_cannot_be_allowed_without_positional_ones() -> None:
    with pytest.raises(ValueError, match="positional"):
        HudCapabilities(static_hud=True, positional_hud=False, dynamic_hud=True, live_context=False)
    with pytest.raises(ValueError, match="dynamic"):
        HudCapabilities(static_hud=True, positional_hud=True, dynamic_hud=False, live_context=True)


# --------------------------------------------------------------------------- #
# The positional render path (Aux_Hud)
# --------------------------------------------------------------------------- #


def _aux(site: str, mode: str = "current"):
    from fpdb_3_legacy import Aux_Hud

    aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aux.hud = SimpleNamespace(site=site)
    aux.game_params = SimpleNamespace(name="SS", positional_mode=mode)
    aux.config = SimpleNamespace(stat_sets={}, supported_sites={})
    return aux


@pytest.mark.parametrize("site", ["PokerStars.FR", "Winamax", "Betclic Poker", "Unibet Poker", "GGPoker", ""])
def test_position_panels_are_stacked_where_the_room_refuses_a_positional_hud(site) -> None:
    # A profile set to "current" would show a different panel each hand; at
    # these tables every position panel shows, so nothing changes with the hand.
    assert _aux(site, "current")._positional_mode() == "all"


def test_a_reviewed_room_keeps_the_profile_choice(reviewed_room) -> None:
    assert _aux(reviewed_room, "current")._positional_mode() == "current"
    assert _aux(reviewed_room, "all")._positional_mode() == "all"


def test_a_configured_network_restricts_the_positional_path(reviewed_room) -> None:
    aux = _aux(reviewed_room)
    aux.config.supported_sites = {reviewed_room: SimpleNamespace(network="iPoker")}

    assert aux._positional_mode() == "all"


def test_a_profile_switch_cannot_bring_position_filtering_back() -> None:
    aux = _aux("Winamax", "all")
    assert aux._positional_mode() == "all"

    aux.game_params = SimpleNamespace(name="other", positional_mode="current")
    aux.config.stat_sets = {"other": SimpleNamespace(positional_mode="current")}

    assert aux._positional_mode() == "all"


def test_the_refusal_is_logged_once(monkeypatch) -> None:
    from fpdb_3_legacy import Aux_Hud

    log = Mock()
    monkeypatch.setattr(Aux_Hud, "log", log)
    aux = _aux("PokerStars")

    for _ in range(3):
        aux._positional_mode()

    said = [call for call in log.info.call_args_list if "stacked" in call.args[0]]
    assert len(said) == 1


# --------------------------------------------------------------------------- #
# Live sources (Hud)
# --------------------------------------------------------------------------- #


def _hud(site: str):
    from fpdb_3_legacy.Hud import Hud

    hud = Hud.__new__(Hud)
    hud.site = site
    hud.config = SimpleNamespace(supported_sites={})
    hud.aux_windows = []
    hud.live_state = {}
    return hud


@pytest.mark.parametrize("site", ["Winamax", "PokerStars", "CoinPoker", "Unibet"])
def test_a_live_action_is_dropped_where_the_room_refuses_live_context(site) -> None:
    hud = _hud(site)

    assert hud.accept_live_action(object()) is None
    assert getattr(hud, "_live_context_session", None) is None


def test_a_folded_live_context_is_dropped_where_the_room_refuses_it() -> None:
    from fpdb_3_legacy import hud_live_context as live

    hud = _hud("Winamax")
    hud.accept_live_context(live.LiveContext(street="flop"))

    assert not hud.live_state


def test_a_reviewed_room_takes_live_actions(reviewed_room) -> None:
    from fpdb_3_legacy import hud_live_context as live

    hud = _hud(reviewed_room)
    action = live.LiveAction(actor="P1", action="raises", street="preflop", to_cents=600, sequence=1, hand_id="h1")

    hud.accept_live_action(action)

    assert getattr(hud, "_live_context_session", None) is not None
