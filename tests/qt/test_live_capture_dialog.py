"""Tools ▸ Live capture: the window over live_capture_consent (#451)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from fpdb_3_legacy import live_capture_consent, live_capture_dialog  # noqa: E402
from fpdb_3_legacy.live_capture_consent import COINPOKER_PACKETS, SWC_NATIVE  # noqa: E402
from fpdb_3_legacy.live_capture_dialog import LiveCaptureDialog, confirm  # noqa: E402

pytestmark = pytest.mark.qt

QMessageBox = live_capture_dialog.QMessageBox


@pytest.fixture
def config(tmp_path):
    return SimpleNamespace(file=str(tmp_path / "HUD_config.xml"))


@pytest.fixture
def answers(config):
    return live_capture_consent.consent_path(config.file)


@pytest.fixture
def answer(monkeypatch):
    """Click one of the confirmation's buttons instead of showing it."""
    shown: list[str] = []

    def click(accept: bool) -> None:
        def run(box) -> int:
            shown.append(box.informativeText())
            return 0

        def clicked(box):
            roles = {box.buttonRole(button): button for button in box.buttons()}
            return roles[QMessageBox.ButtonRole.AcceptRole if accept else QMessageBox.ButtonRole.RejectRole]

        monkeypatch.setattr(QMessageBox, "exec", run)
        monkeypatch.setattr(QMessageBox, "clickedButton", clicked)

    click.shown = shown  # type: ignore[attr-defined]
    return click


def test_the_confirmation_says_what_happens_and_records_a_yes(qtbot, answers, answer) -> None:
    answer(True)

    assert confirm(SWC_NATIVE, path=answers)

    assert live_capture_consent.is_accepted(SWC_NATIVE, answers)
    assert "SwC Poker client" in answer.shown[0]
    assert "terms prevail" in answer.shown[0]


def test_cancelling_the_confirmation_turns_nothing_on(qtbot, answers, answer) -> None:
    answer(False)

    assert not confirm(SWC_NATIVE, path=answers)

    assert not live_capture_consent.is_accepted(SWC_NATIVE, answers)


def test_a_mechanism_already_on_is_not_asked_again(qtbot, answers, answer) -> None:
    live_capture_consent.accept(SWC_NATIVE, answers)
    answer(False)

    assert confirm(SWC_NATIVE, path=answers)
    assert answer.shown == []


def test_the_window_starts_with_everything_off(qtbot, config) -> None:
    window = LiveCaptureDialog(config)
    qtbot.addWidget(window)

    assert window.boxes
    assert not any(box.isChecked() for box in window.boxes.values())


def test_a_room_whose_support_is_off_has_no_box(qtbot, config) -> None:
    # CoinPoker support is switched off (disabled_sites): nothing of it to turn on.
    window = LiveCaptureDialog(config)
    qtbot.addWidget(window)

    assert SWC_NATIVE.key in window.boxes
    assert COINPOKER_PACKETS.key not in window.boxes


def test_ticking_asks_and_a_yes_turns_it_on(qtbot, config, answers, answer) -> None:
    answer(True)
    window = LiveCaptureDialog(config)
    qtbot.addWidget(window)

    window.boxes[SWC_NATIVE.key].setChecked(True)

    assert answer.shown
    assert live_capture_consent.is_accepted(SWC_NATIVE, answers)


def test_ticking_then_cancelling_leaves_the_box_unticked(qtbot, config, answers, answer) -> None:
    answer(False)
    window = LiveCaptureDialog(config)
    qtbot.addWidget(window)

    window.boxes[SWC_NATIVE.key].setChecked(True)

    assert not window.boxes[SWC_NATIVE.key].isChecked()
    assert not live_capture_consent.is_accepted(SWC_NATIVE, answers)


def test_unticking_turns_it_off(qtbot, config, answers) -> None:
    live_capture_consent.accept(SWC_NATIVE, answers)
    window = LiveCaptureDialog(config)
    qtbot.addWidget(window)
    assert window.boxes[SWC_NATIVE.key].isChecked()

    window.boxes[SWC_NATIVE.key].setChecked(False)

    assert not live_capture_consent.is_accepted(SWC_NATIVE, answers)
