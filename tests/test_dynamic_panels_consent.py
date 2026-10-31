"""Dynamic HUD panels run only after a yes, and never at PokerStars tables (#647)."""

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


def test_a_fresh_install_has_not_said_yes(answers) -> None:
    assert not consent.is_confirmed(answers)
    assert "Preferences" in consent.why_not_at("Winamax", answers)


def test_a_yes_is_kept_with_its_version(answers) -> None:
    consent.confirm(answers)

    assert consent.is_confirmed(answers)
    assert consent.why_not_at("Winamax", answers) is None
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


def test_pokerstars_never_gets_them(answers) -> None:
    consent.confirm(answers)

    assert "PokerStars" in consent.why_not_at("PokerStars", answers)


def test_the_question_names_the_rooms_and_their_terms() -> None:
    text = consent.statement()

    assert "PokerStars" in text
    assert "Winamax" in text
    assert "terms prevail" in text
    assert "never shows a recommended action" in text
