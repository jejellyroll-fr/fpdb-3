"""What a real button click delivers to a real refresh callback.

The wrapper that ends a tab's read transaction (#271) stands between
``QPushButton.clicked`` and every tab's refresh, and PySide decides what to
send a slot by reading that slot's own signature. A wrapper therefore replaces
the signature it is standing in for, and gets to choose what the callback sees.

Getting that wrong broke all six tabs at once: ``def run(*args)`` counts as
taking no argument, so Qt sent nothing and the nine refreshes that require
``checkState`` were called with none -- "Refresh Stats does nothing" on every
tab. The unit tests around the wrapper did not catch it because they called
the wrapper directly, supplying the argument Qt was not supplying. Only a real
click can answer this question, so these tests click.
"""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QPushButton

from fpdb_3_legacy.Filters import Filters

pytestmark = pytest.mark.qt


class RecordingFilters:
    """The wrapper under test, on a host reduced to what it touches."""

    _releasing_read_locks = Filters._releasing_read_locks

    def __init__(self) -> None:
        self.rollbacks = 0

    def end_read_transaction(self) -> None:
        self.rollbacks += 1


def clicked_with(qtbot, callback: Any) -> RecordingFilters:
    """Connect ``callback`` the way Filters does, then click the button."""
    host = RecordingFilters()
    button = QPushButton()
    qtbot.addWidget(button)
    button.clicked.connect(host._releasing_read_locks(callback))
    button.click()
    return host


def test_a_refresh_needing_the_flag_is_given_it(qtbot) -> None:
    """Nine of the twelve registered refreshes declare ``checkState``."""
    seen: list[Any] = []

    host = clicked_with(qtbot, lambda check_state: seen.append(check_state))

    assert len(seen) == 1, "the refresh was never called with its argument"
    assert host.rollbacks == 1


def test_a_refresh_taking_nothing_is_given_nothing(qtbot) -> None:
    """Both exportGraph methods and GuiTourneyPlayerStats.refreshStats."""
    calls: list[bool] = []

    host = clicked_with(qtbot, lambda: calls.append(True))

    assert calls == [True]
    assert host.rollbacks == 1


def test_a_refresh_with_a_second_optional_argument_still_runs(qtbot) -> None:
    """``GuiGraphViewer.generateGraph(widget, data=None)`` shape."""
    seen: list[tuple[Any, ...]] = []

    def refresh(widget, data=None) -> None:
        seen.append((widget, data))

    host = clicked_with(qtbot, refresh)

    assert len(seen) == 1
    assert seen[0][1] is None
    assert host.rollbacks == 1


def test_a_failing_refresh_still_ends_the_transaction(qtbot) -> None:
    """The failed refresh is the one that leaves a transaction behind.

    On PostgreSQL it is left aborted, and every later query on that connection
    fails until something ends it.
    """
    host = RecordingFilters()

    def explode(_check_state) -> None:
        msg = "the query blew up"
        raise RuntimeError(msg)

    wrapped = host._releasing_read_locks(explode)
    with pytest.raises(RuntimeError):
        wrapped(False)

    assert host.rollbacks == 1
