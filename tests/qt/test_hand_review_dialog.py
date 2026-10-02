"""Offscreen checks for the solver review dialog and its entry points (#328)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from fpdb_3_legacy.GuiReplayer import GuiReplayer
from fpdb_3_legacy.hand_review_dialog import HandReviewDialog, add_review_action
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

pytestmark = pytest.mark.qt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hands" / "pokerstars"


def parse(config, relative: str):
    return PokerStars(config=config, in_path=str(FIXTURES / relative), autostart=True).getProcessedHands()[0]


def import_hand(importer, fresh_db, tmp_path, relative: str) -> int:
    source = FIXTURES / relative
    copy = tmp_path / source.name
    copy.write_bytes(source.read_bytes())
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()
    return hand_id


def test_the_dialog_previews_the_preflop_it_sends(qtbot, legacy_config) -> None:
    dialog = HandReviewDialog(parse(legacy_config, "review/nl_3bet_6max.txt"), applied_preflop=4)
    qtbot.addWidget(dialog)

    preview = dialog.preview.toPlainText()
    assert "Hero: CO [Ah Qd]" in preview
    # Facing the 3-bet: the call is the decision pointed at.
    assert "> CO: Call 5.53 BB" in preview
    assert "* CO: Raise to 2.47 BB" in preview
    assert dialog.decision_button.isChecked()
    assert dialog.save_button.isEnabled()

    dialog.hand_button.setChecked(True)
    assert "> CO" not in dialog.preview.toPlainText()
    assert dialog.document()["hands"][0]["selected_decision"] is None


def test_the_dialog_saves_the_document_preflop_advisor_loads(qtbot, legacy_config, tmp_path, monkeypatch) -> None:
    dialog = HandReviewDialog(parse(legacy_config, "review/plo_3bet_6max.txt"), fpdb_hand_id=42, applied_preflop=0)
    qtbot.addWidget(dialog)
    target = tmp_path / "review.json"
    seen: dict[str, str] = {}

    def save_name(_parent, _title, name, _filter):
        seen["name"] = name
        return str(target), ""

    monkeypatch.setattr("fpdb_3_legacy.hand_review_dialog.QFileDialog.getSaveFileName", save_name)

    dialog.save()

    assert seen["name"] == "fpdb-hand-review-42.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["version"] == 1
    hand = document["hands"][0]
    assert hand["hand_id"] == "42"
    assert hand["game"] == "PLO"
    assert hand["selected_decision"] == 4


def test_the_dialog_copies_the_json(qtbot, legacy_config) -> None:
    dialog = HandReviewDialog(parse(legacy_config, "review/nl_hu.txt"))
    qtbot.addWidget(dialog)

    dialog.copy()

    document = json.loads(QApplication.clipboard().text())
    assert document["hands"][0]["seats"] == ["SB", "BB"]
    # No replayed point given: the whole hand is reviewed.
    assert not dialog.decision_button.isEnabled()
    assert document["hands"][0]["selected_decision"] is None


def test_an_unsupported_hand_says_why_and_sends_nothing(qtbot, legacy_config) -> None:
    dialog = HandReviewDialog(parse(legacy_config, "holdem/straddle.txt"))
    qtbot.addWidget(dialog)

    assert "straddle" in dialog.preview.toPlainText()
    assert not dialog.save_button.isEnabled()
    assert not dialog.copy_button.isEnabled()


def test_an_unexpected_failure_is_shown_not_swallowed(qtbot, legacy_config, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise IndexError("tuple index out of range")

    monkeypatch.setattr("fpdb_3_legacy.hand_review_dialog.build_hand_review", broken)
    dialog = HandReviewDialog(parse(legacy_config, "review/nl_3bet_6max.txt"))
    qtbot.addWidget(dialog)

    assert dialog.preview.toPlainText() == "tuple index out of range"
    assert not dialog.save_button.isEnabled()


def test_the_hand_viewer_menu_offers_the_review(qtbot, legacy_config) -> None:
    menu = QMenu()
    add_review_action(menu, parse(legacy_config, "review/nl_3bet_6max.txt"), fpdb_hand_id=7)
    assert [action.text() for action in menu.actions()] == ["Solver review (PreflopAdvisor)..."]


def test_the_replayer_reviews_the_decision_on_screen(
    qtbot, importer, fresh_db, legacy_config, tmp_path, monkeypatch
) -> None:
    hand_id = import_hand(importer, fresh_db, tmp_path, "review/nl_3bet_6max.txt")
    replayer = GuiReplayer(legacy_config, fresh_db.sql, MagicMock(), [hand_id], db=fresh_db)
    qtbot.addWidget(replayer)
    assert not replayer.reviewButton.isEnabled()

    replayer.play_hand(0)
    assert replayer.reviewButton.isEnabled()
    assert replayer.shared_hand_id == hand_id

    preflop_start = next(index for index, state in enumerate(replayer.states) if state.street == "PREFLOP")
    opened: list[HandReviewDialog] = []
    monkeypatch.setattr(HandReviewDialog, "exec", lambda self: opened.append(self) or 0)

    # Paused right after the hero's open (the third preflop action).
    replayer.stateSlider.setValue(preflop_start + 3)
    assert replayer.preflop_actions_shown() == 3
    replayer.review_clicked()
    assert opened[-1].current_review().selected_decision == 2
    assert opened[-1].current_review().fpdb_hand_id == hand_id

    # On the flop: every preflop action has been played, the last decision is pointed at.
    replayer.stateSlider.setValue(replayer.stateSlider.maximum())
    assert replayer.preflop_actions_shown() == 7
    replayer.review_clicked()
    assert opened[-1].current_review().selected_decision == 6
    for dialog in opened:
        qtbot.addWidget(dialog)


def test_a_hand_that_fails_to_load_cannot_be_reviewed_as_the_previous_one(
    qtbot, importer, fresh_db, legacy_config, tmp_path
) -> None:
    hand_id = import_hand(importer, fresh_db, tmp_path, "review/nl_3bet_6max.txt")
    replayer = GuiReplayer(legacy_config, fresh_db.sql, MagicMock(), [hand_id, hand_id + 1], db=fresh_db)
    qtbot.addWidget(replayer)
    replayer.play_hand(0)
    assert replayer.reviewButton.isEnabled()

    replayer.play_hand(1)  # no such hand in the database

    assert replayer.shared_hand_id is None
    assert not replayer.reviewButton.isEnabled()


# -- opening in PreflopAdvisor (#413) ---------------------------------------------


class RememberedPath:
    """Stands in for the configuration: never the real HUD_config.xml."""

    def __init__(self, path: str | None = None) -> None:
        self.general = {"preflop_advisor": path} if path else {}
        self.saved: list[str | None] = []

    def set_preflop_advisor_path(self, path: str | None) -> None:
        self.saved.append(path)
        self.general["preflop_advisor"] = path


class Starts:
    """Records what would have been started, and answers whether it started."""

    def __init__(self, *answers: bool) -> None:
        self.answers = list(answers) or [True]
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, program: str, arguments: list[str]) -> bool:
        self.calls.append((program, arguments))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


@pytest.fixture
def program(tmp_path, monkeypatch) -> Path:
    """A PreflopAdvisor executable, and no other one on the PATH; documents go to tmp_path."""
    path = tmp_path / "preflop_advisor"
    path.write_bytes(b"")
    monkeypatch.setattr("fpdb_3_legacy.hand_review_payload.shutil.which", lambda _name: None)
    monkeypatch.setattr("fpdb_3_legacy.hand_review_dialog.tempfile.gettempdir", lambda: str(tmp_path))
    return path


def review_dialog(qtbot, legacy_config, **kwargs) -> HandReviewDialog:
    dialog = HandReviewDialog(parse(legacy_config, "review/nl_3bet_6max.txt"), fpdb_hand_id=7, **kwargs)
    qtbot.addWidget(dialog)
    return dialog


def test_open_starts_preflop_advisor_on_the_written_document(qtbot, legacy_config, program, tmp_path) -> None:
    starts = Starts()
    dialog = review_dialog(qtbot, legacy_config, config=RememberedPath(str(program)), start=starts)

    dialog.open_button.click()

    written = tmp_path / "fpdb-hand-reviews" / "fpdb-hand-review-7.json"
    assert starts.calls == [(str(program), ["--review", str(written)])]
    assert json.loads(written.read_text(encoding="utf-8"))["hands"][0]["fpdb_hand_id"] == 7
    assert dialog.result() == HandReviewDialog.DialogCode.Accepted


def test_open_asks_where_preflop_advisor_is_and_remembers_it(qtbot, legacy_config, program, monkeypatch) -> None:
    config = RememberedPath()
    starts = Starts()
    monkeypatch.setattr(
        "fpdb_3_legacy.hand_review_dialog.QFileDialog.getOpenFileName", lambda *args, **kwargs: (str(program), "")
    )
    dialog = review_dialog(qtbot, legacy_config, config=config, start=starts)

    dialog.open_button.click()

    assert config.saved == [str(program)]
    assert [program_started for program_started, _arguments in starts.calls] == [str(program)]


def test_open_without_preflop_advisor_does_nothing_when_not_located(qtbot, legacy_config, program, monkeypatch) -> None:
    starts = Starts()
    monkeypatch.setattr(
        "fpdb_3_legacy.hand_review_dialog.QFileDialog.getOpenFileName", lambda *args, **kwargs: ("", "")
    )
    dialog = review_dialog(qtbot, legacy_config, config=RememberedPath(), start=starts)

    dialog.open_button.click()

    assert starts.calls == []
    assert dialog.result() != HandReviewDialog.DialogCode.Accepted


def test_a_launch_that_fails_offers_to_locate_preflop_advisor_again(
    qtbot, legacy_config, program, tmp_path, monkeypatch
) -> None:
    other = tmp_path / "PreflopAdvisor-2"
    other.write_bytes(b"")
    config = RememberedPath(str(program))
    starts = Starts(False, True)
    asked: list[str] = []
    monkeypatch.setattr(
        "fpdb_3_legacy.hand_review_dialog.QMessageBox.question",
        lambda _parent, _title, text: asked.append(text) or QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "fpdb_3_legacy.hand_review_dialog.QFileDialog.getOpenFileName", lambda *args, **kwargs: (str(other), "")
    )
    dialog = review_dialog(qtbot, legacy_config, config=config, start=starts)

    dialog.open_button.click()

    assert "could not be started" in asked[0]
    assert [started for started, _arguments in starts.calls] == [str(program), str(other)]
    assert config.saved == [str(other)]
    assert dialog.result() == HandReviewDialog.DialogCode.Accepted


def test_an_unsupported_hand_cannot_be_opened(qtbot, legacy_config) -> None:
    dialog = HandReviewDialog(parse(legacy_config, "holdem/straddle.txt"), start=Starts())
    qtbot.addWidget(dialog)

    assert not dialog.open_button.isEnabled()
