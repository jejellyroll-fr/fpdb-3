"""A capture that reaches into a poker client runs only once its user said yes (#451).

The SwC tap is loaded into the client and the CoinPoker capture records its
packets. Neither may start on a fresh install: the user turns each on after
reading what it does, and a mechanism that changes asks again.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from fpdb_3_legacy import live_capture_consent as consent
from fpdb_3_legacy import swc_native_capture
from fpdb_3_legacy.live_capture_consent import COINPOKER_PACKETS, SWC_NATIVE, LiveCaptureNotAccepted


@pytest.fixture
def answers(tmp_path) -> Path:
    return tmp_path / consent.CONSENT_NAME


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


# --------------------------------------------------------------------------
# The answers
# --------------------------------------------------------------------------


def test_a_fresh_install_has_turned_nothing_on(answers) -> None:
    assert not answers.exists()
    assert not consent.is_accepted(SWC_NATIVE, answers)
    assert not consent.is_accepted(COINPOKER_PACKETS, answers)
    with pytest.raises(LiveCaptureNotAccepted, match="Tools ▸ Live capture"):
        consent.require(SWC_NATIVE, answers)


def test_a_yes_turns_on_that_mechanism_only(answers) -> None:
    consent.accept(SWC_NATIVE, answers)

    assert consent.is_accepted(SWC_NATIVE, answers)
    assert not consent.is_accepted(COINPOKER_PACKETS, answers)
    consent.require(SWC_NATIVE, answers)
    recorded = json.loads(answers.read_text(encoding="utf-8"))["accepted"]["swc_native"]
    assert recorded["version"] == SWC_NATIVE.version
    assert recorded["accepted_at"]


def test_a_changed_mechanism_asks_again(answers) -> None:
    consent.accept(SWC_NATIVE, answers)
    changed = consent.Mechanism(SWC_NATIVE.key, SWC_NATIVE.version + 1, SWC_NATIVE.title, SWC_NATIVE.what_happens)

    assert not consent.is_accepted(changed, answers)


def test_withdrawing_turns_it_off_and_keeps_the_others(answers) -> None:
    consent.accept(SWC_NATIVE, answers)
    consent.accept(COINPOKER_PACKETS, answers)

    consent.withdraw(SWC_NATIVE, answers)

    assert not consent.is_accepted(SWC_NATIVE, answers)
    assert consent.is_accepted(COINPOKER_PACKETS, answers)


@pytest.mark.parametrize(
    "content",
    ["", "not json", "[]", '{"accepted": {"swc_native": 1}}', '{"accepted": ["swc_native"]}', '{"accepted": "yes"}'],
)
def test_an_unreadable_answers_file_is_a_no(answers, content) -> None:
    answers.write_text(content, encoding="utf-8")

    assert not consent.is_accepted(SWC_NATIVE, answers)
    consent.accept(SWC_NATIVE, answers)  # a yes replaces what could not be read
    assert consent.is_accepted(SWC_NATIVE, answers)


def test_the_answers_sit_beside_the_configuration(tmp_path) -> None:
    config = tmp_path / "profile" / "HUD_config.xml"

    assert consent.consent_path(config) == (tmp_path / "profile" / consent.CONSENT_NAME).resolve()


def test_the_statement_names_the_risk_and_the_rooms_terms() -> None:
    text = consent.statement(SWC_NATIVE)

    assert "SwC Poker client" in text
    assert "close the account" in text
    assert "terms prevail" in text


# --------------------------------------------------------------------------
# The terminal question
# --------------------------------------------------------------------------


def test_a_command_off_a_terminal_is_refused(answers) -> None:
    out = io.StringIO()

    assert not consent.confirm_on_terminal(SWC_NATIVE, answers, stdin=io.StringIO("yes\n"), stdout=out)
    assert not consent.is_accepted(SWC_NATIVE, answers)
    assert "terms prevail" in out.getvalue()


@pytest.mark.parametrize(("typed", "on"), [("yes\n", True), ("YES\n", True), ("y\n", False), ("\n", False)])
def test_only_a_typed_yes_turns_it_on(answers, typed, on) -> None:
    assert consent.confirm_on_terminal(SWC_NATIVE, answers, stdin=_Terminal(typed), stdout=io.StringIO()) is on
    assert consent.is_accepted(SWC_NATIVE, answers) is on


def test_a_mechanism_already_on_is_not_asked_again(answers) -> None:
    consent.accept(SWC_NATIVE, answers)
    out = io.StringIO()

    assert consent.confirm_on_terminal(SWC_NATIVE, answers, stdin=io.StringIO(), stdout=out)
    assert out.getvalue() == ""


# --------------------------------------------------------------------------
# The capture paths refuse without it
# --------------------------------------------------------------------------


def test_the_windows_attach_builds_and_injects_nothing_without_a_yes(answers, monkeypatch) -> None:
    built = []
    monkeypatch.setattr(swc_native_capture.platform, "system", lambda: "Windows")
    monkeypatch.setattr(swc_native_capture, "build_tap", lambda **_: built.append("tap"))

    with pytest.raises(LiveCaptureNotAccepted):
        swc_native_capture.attach_to_windows_client(consent=answers)

    assert built == []


def test_the_launch_preloads_nothing_without_a_yes(answers, monkeypatch, tmp_path) -> None:
    launched = []
    monkeypatch.setattr(swc_native_capture, "running_client_pids", list)
    monkeypatch.setattr(swc_native_capture, "build_tap", lambda **_: launched.append("tap"))
    monkeypatch.setattr(swc_native_capture.subprocess, "Popen", lambda *a, **k: launched.append(a))

    with pytest.raises(LiveCaptureNotAccepted):
        swc_native_capture.launch_client(tmp_path / "swc.raw", consent=answers)

    assert launched == []


def test_the_swc_command_stops_when_the_answer_is_no(monkeypatch) -> None:
    monkeypatch.setattr(consent, "confirm_on_terminal", lambda *_a, **_k: False)
    monkeypatch.setattr(swc_native_capture, "launch_client", lambda *_a, **_k: pytest.fail("launched"))
    monkeypatch.setattr(swc_native_capture, "attach_to_windows_client", lambda **_k: pytest.fail("attached"))

    assert swc_native_capture.main([]) == 2


def test_the_coinpoker_live_command_stops_without_a_yes(tmp_path, monkeypatch, capsys) -> None:
    from fpdb_3_legacy import coinpoker_live_capture, coinpoker_pcap

    config = tmp_path / "HUD_config.xml"
    monkeypatch.setattr(sys, "argv", ["coinpoker_live_capture", "--live", "--config-file", str(config)])
    monkeypatch.setattr(coinpoker_pcap, "capture_live", lambda *_a, **_k: pytest.fail("captured"))

    with pytest.raises(SystemExit) as exited:
        coinpoker_live_capture.main()

    assert exited.value.code == 1
    assert "CoinPoker packet capture is off" in capsys.readouterr().out


def test_the_coinpoker_replay_needs_no_yes(tmp_path, monkeypatch) -> None:
    # Reading a capture file back records nothing from the client.
    from fpdb_3_legacy import coinpoker_live_capture

    monkeypatch.setattr(sys, "argv", ["coinpoker_live_capture", "--replay", str(tmp_path / "x.pcap"), "--dry-run"])
    monkeypatch.setattr(coinpoker_live_capture, "_events_from_segments", lambda _s: [])
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_pcap.open_offline", lambda *_a: [])
    ran = []
    monkeypatch.setattr(coinpoker_live_capture, "run", lambda *a, **k: ran.append(k))

    coinpoker_live_capture.main()

    assert ran
