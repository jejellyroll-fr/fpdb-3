"""A capture that reaches into a poker client runs only once its user said yes (#451).

The SwC tap is loaded into the client. It may not start on a fresh install: the
user turns it on after reading what it does, and a mechanism that changes asks
again.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from fpdb_3_legacy import live_capture_consent as consent
from fpdb_3_legacy.capture import swc_client
from fpdb_3_legacy.live_capture_consent import SWC_NATIVE, LiveCaptureNotAccepted

#: A second mechanism, so that answers can be shown to stay apart.
OTHER = consent.Mechanism("other_capture", 1, "Other capture", "Reads another client.")


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
    assert not consent.is_accepted(OTHER, answers)
    with pytest.raises(LiveCaptureNotAccepted, match="Tools ▸ Live capture"):
        consent.require(SWC_NATIVE, answers)


def test_a_yes_turns_on_that_mechanism_only(answers) -> None:
    consent.accept(SWC_NATIVE, answers)

    assert consent.is_accepted(SWC_NATIVE, answers)
    assert not consent.is_accepted(OTHER, answers)
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
    consent.accept(OTHER, answers)

    consent.withdraw(SWC_NATIVE, answers)

    assert not consent.is_accepted(SWC_NATIVE, answers)
    assert consent.is_accepted(OTHER, answers)


def test_an_answer_for_the_removed_coinpoker_capture_is_ignored(answers) -> None:
    # CoinPoker's packet capture was removed (#732); a file that still records
    # a yes to it turns nothing on and is still read for the others.
    answers.write_text(
        json.dumps({"accepted": {"coinpoker_packets": {"version": 1}, "swc_native": {"version": SWC_NATIVE.version}}}),
        encoding="utf-8",
    )

    assert "coinpoker_packets" not in consent.MECHANISMS
    assert consent.is_accepted(SWC_NATIVE, answers)


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
    monkeypatch.setattr(swc_client.platform, "system", lambda: "Windows")
    monkeypatch.setattr(swc_client, "build_tap", lambda **_: built.append("tap"))

    with pytest.raises(LiveCaptureNotAccepted):
        swc_client.attach_to_windows_client(consent=answers)

    assert built == []


def test_turning_it_off_during_the_build_injects_nothing(answers, monkeypatch) -> None:
    # The Windows attach builds off the GUI thread: unticking meanwhile must stop it.
    from fpdb_3_legacy.capture import swc_tap_build, swc_windows_inject

    consent.accept(SWC_NATIVE, answers)
    injected = []
    monkeypatch.setattr(swc_client.platform, "system", lambda: "Windows")

    def build_then_untick(**_):
        consent.withdraw(SWC_NATIVE, answers)
        return Path("tap.dll")

    monkeypatch.setattr(swc_client, "build_tap", build_then_untick)
    monkeypatch.setattr(swc_tap_build, "build_injector", lambda **_: Path("inj.exe"))
    monkeypatch.setattr(swc_windows_inject, "find_client_pids", lambda *_a, **_k: [100])
    monkeypatch.setattr(swc_windows_inject, "inject_into_pid", lambda *a: injected.append(a))

    with pytest.raises(swc_client.CaptureAttachCancelled):
        swc_client.attach_to_windows_client(consent=answers)

    assert injected == []


def test_the_launch_preloads_nothing_without_a_yes(answers, monkeypatch, tmp_path) -> None:
    launched = []
    monkeypatch.setattr(swc_client, "running_client_pids", list)
    monkeypatch.setattr(swc_client, "build_tap", lambda **_: launched.append("tap"))
    monkeypatch.setattr(swc_client.subprocess, "Popen", lambda *a, **k: launched.append(a))

    with pytest.raises(LiveCaptureNotAccepted):
        swc_client.launch_client(tmp_path / "swc.raw", consent=answers)

    assert launched == []


def test_turning_it_off_during_the_build_launches_nothing(answers, monkeypatch, tmp_path) -> None:
    # macOS and Linux preload the tap at launch: unticking while it compiles must stop it.
    consent.accept(SWC_NATIVE, answers)
    launched = []
    monkeypatch.setattr(swc_client, "running_client_pids", list)

    def build_then_untick(**_):
        consent.withdraw(SWC_NATIVE, answers)
        return tmp_path / "tap.dylib"

    monkeypatch.setattr(swc_client, "build_tap", build_then_untick)
    monkeypatch.setattr(swc_client.subprocess, "Popen", lambda *a, **k: launched.append(a))

    with pytest.raises(LiveCaptureNotAccepted):
        swc_client.launch_client(tmp_path / "swc.raw", consent=answers)

    assert launched == []


def test_the_swc_command_stops_when_the_answer_is_no(monkeypatch) -> None:
    monkeypatch.setattr(consent, "confirm_on_terminal", lambda *_a, **_k: False)
    monkeypatch.setattr(swc_client, "launch_client", lambda *_a, **_k: pytest.fail("launched"))
    monkeypatch.setattr(swc_client, "attach_to_windows_client", lambda **_k: pytest.fail("attached"))

    assert swc_client.main([]) == 2


def test_the_client_is_looked_for_with_a_resolved_pgrep(monkeypatch) -> None:
    from fpdb_3_legacy.capture import swc_client

    calls = []
    monkeypatch.setattr(swc_client.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        swc_client.subprocess,
        "run",
        lambda argv, **_k: calls.append(argv) or type("Done", (), {"stdout": "41\n42\nnot-a-pid\n"})(),
    )

    assert swc_client.running_client_pids() == [41, 42]
    assert calls[0][0] == "/usr/bin/pgrep"


def test_no_pgrep_is_said_rather_than_taken_for_no_client(monkeypatch) -> None:
    from fpdb_3_legacy.capture import swc_client

    monkeypatch.setattr(swc_client.shutil, "which", lambda _name: None)

    with pytest.raises(FileNotFoundError, match="pgrep"):
        swc_client.running_client_pids()
