"""The tournament graph's ICM $EV-adjusted line, drawn next to the results (#446)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6.QtWidgets")

from fpdb_3_legacy import tourney_icm_line  # noqa: E402 - after the Qt availability probe
from fpdb_3_legacy.GuiTourneyGraphViewer import GuiTourneyGraphViewer  # noqa: E402
from fpdb_3_legacy.tourney_icm_line import IcmLine  # noqa: E402


def viewer() -> SimpleNamespace:
    return SimpleNamespace(
        db=MagicMock(), conf=None, icm_cache={}, plot_widget=MagicMock(), graph_rows=[(7, -1100), (8, 500)]
    )


@pytest.mark.qt
def test_the_line_is_drawn_from_the_graph_s_rows_and_says_how_much_is_priced(qtbot, monkeypatch) -> None:
    asked = {}

    def line(_db, results, hands, _load_hand, *, cache):
        asked.update(results=results, hands=hands, cache=cache)
        return IcmLine((-9.5, -4.5), priced=1, allins=3)

    monkeypatch.setattr(tourney_icm_line, "allin_hands", lambda _db, ids: {7: [(70, "Hero")]} if ids == [5] else {})
    monkeypatch.setattr(tourney_icm_line, "icm_line", line)
    shown = viewer()

    GuiTourneyGraphViewer.plot_icm_line(shown, [5], "USD", "#0369a1")

    assert asked["results"] == [(7, -11.0), (8, 5.0)]  # hundredths to currency units, in graph order
    assert asked["hands"] == {7: [(70, "Hero")]} and asked["cache"] is shown.icm_cache
    (values,), kwargs = shown.plot_widget.plot.call_args
    assert list(values) == [-9.5, -4.5] and "1 of 3 all-ins priced" in kwargs["name"]
    shown.db.rollback.assert_called()


@pytest.mark.qt
def test_a_failed_line_leaves_the_results_alone(qtbot, monkeypatch) -> None:
    def broken(*_args, **_kwargs):
        raise RuntimeError("no database")

    monkeypatch.setattr(tourney_icm_line, "allin_hands", broken)
    shown = viewer()

    GuiTourneyGraphViewer.plot_icm_line(shown, [5], "USD", "#0369a1")

    shown.plot_widget.plot.assert_not_called()
    shown.db.rollback.assert_called()
