"""Dynamic HUD panels run only after a yes, and only where the room allows them (#647, #756)."""

from __future__ import annotations

import json

import pytest

from fpdb_3_legacy import dynamic_panels_consent as consent
from fpdb_3_legacy.dynamic_panels_consent import DYNAMIC_PANELS


@pytest.fixture
def answers(tmp_path):
    return consent.consent_path(tmp_path / "HUD_config.xml")


def test_the_answer_sits_beside_the_configuration_apart_from_the_captures(tmp_path) -> None:
    config = tmp_path / "profile" / "HUD_config.xml"

    assert consent.consent_path(config) == (tmp_path / "profile" / "dynamic-panels-consent.json").resolve()


def test_a_fresh_install_has_not_said_yes(answers, reviewed_room) -> None:
    assert not consent.is_confirmed(answers)
    assert "Preferences" in consent.why_not_at(reviewed_room, answers)


def test_a_yes_is_kept_with_its_version(answers, reviewed_room) -> None:
    consent.confirm(answers)

    assert consent.is_confirmed(answers)
    assert consent.why_not_at(reviewed_room, answers) is None
    recorded = json.loads(answers.read_text(encoding="utf-8"))["accepted"][DYNAMIC_PANELS.key]
    assert recorded["version"] == DYNAMIC_PANELS.version


def test_a_changed_behaviour_asks_again(answers, monkeypatch) -> None:
    consent.confirm(answers)
    changed = consent.Mechanism(DYNAMIC_PANELS.key, DYNAMIC_PANELS.version + 1, "", "")
    monkeypatch.setattr(consent, "DYNAMIC_PANELS", changed)

    assert not consent.is_confirmed(answers)


def test_withdrawing_turns_them_off(answers) -> None:
    consent.confirm(answers)

    consent.withdraw(answers)

    assert not consent.is_confirmed(answers)


@pytest.mark.parametrize("site", ["PokerStars", "PokerStars.FR", "PokerStars.COM", "PokerStarsES", "pokerstars.it"])
def test_pokerstars_never_gets_them_on_any_regional_site(answers, site) -> None:
    consent.confirm(answers)

    assert consent.forbids_them(site)
    assert "PokerStars" in consent.why_not_at(site, answers)


@pytest.mark.parametrize(
    ("site", "named"),
    [
        ("Winamax", "Winamax"),
        ("iPoker", "iPoker"),
        ("Betclic Poker", "iPoker"),
        ("PMU Poker", "iPoker"),
        ("Unibet Poker", "iPoker"),
        ("Unibet", "Unibet"),
        ("GGPoker", "GGPoker"),
        ("CoinPoker", "CoinPoker"),
        ("Americas Cardroom", "Americas Cardroom"),
    ],
)
def test_a_yes_does_not_turn_them_on_where_the_room_has_not_allowed_them(answers, site, named) -> None:
    # Winamax pending its integrity team's approval, iPoker under every skin's
    # own name, and every room nobody has reviewed yet (#756).
    consent.confirm(answers)

    assert consent.forbids_them(site)
    assert named in consent.why_not_at(site, answers)


@pytest.mark.parametrize("site", ["", None])
def test_a_table_with_no_room_gets_the_conservative_policy(answers, site) -> None:
    consent.confirm(answers)

    assert consent.forbids_them(site)
    assert consent.why_not_at(site, answers) is not None


def test_a_reviewed_room_lets_the_yes_decide(answers, reviewed_room) -> None:
    assert not consent.forbids_them(reviewed_room)
    assert consent.why_not_at(reviewed_room, answers) is not None

    consent.confirm(answers)

    assert consent.why_not_at(reviewed_room, answers) is None


def test_a_configured_network_can_only_restrict(answers, reviewed_room) -> None:
    # HUD_config.xml's network attribute is user-editable: a stricter network
    # restricts a site, but naming a reviewed network never frees PokerStars.
    consent.confirm(answers)

    assert "iPoker" in consent.why_not_at(reviewed_room, answers, network="iPoker")
    assert "PokerStars" in consent.why_not_at("PokerStars.FR", answers, network=reviewed_room)


def test_a_rewritten_answer_file_is_read_again(answers) -> None:
    # The answer is memoised per file state; a new answer must not be hidden by it.
    consent.confirm(answers)
    assert consent.is_confirmed(answers)

    answers.unlink()
    assert not consent.is_confirmed(answers)

    consent.confirm(answers)
    consent.withdraw(answers)
    assert not consent.is_confirmed(answers)


def test_the_question_names_the_rooms_and_their_terms() -> None:
    text = consent.statement()

    assert "PokerStars" in text
    assert "Winamax" in text
    assert "iPoker" in text
    assert "does not change that" in text
    assert "terms prevail" in text
    assert "never shows a recommended action" in text
