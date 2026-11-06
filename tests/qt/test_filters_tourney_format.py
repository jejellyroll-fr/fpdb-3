"""The tournament reports' Format card: every tournament, knockouts only or freezeouts only (#447)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QGroupBox

from fpdb_3_legacy.Filters import Filters

pytestmark = pytest.mark.qt


class FormatHost:
    """The two Filters methods under test, on a host reduced to what they touch."""

    tourneyFormat = None
    fill = Filters.fillTourneyFormatFrame
    selected = Filters.getTourneyFormat


def test_the_card_offers_every_format_and_starts_on_all(qtbot) -> None:
    host, frame = FormatHost(), QGroupBox()
    qtbot.addWidget(frame)

    host.fill(frame)

    combo = host.tourneyFormat
    assert [combo.itemData(index) for index in range(combo.count())] == ["all", "knockout", "freezeout"]
    assert host.selected() == "all"


def test_the_choice_is_what_the_reports_read(qtbot) -> None:
    host, frame = FormatHost(), QGroupBox()
    qtbot.addWidget(frame)
    host.fill(frame)

    host.tourneyFormat.setCurrentIndex(1)

    assert host.selected() == "knockout"


def test_a_report_without_the_card_reads_every_tournament() -> None:
    assert FormatHost().selected() == "all"
