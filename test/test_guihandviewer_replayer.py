"""Opening the replayer from a hand viewer must not stall the window.

Two things caused it. Every double-click built a fresh GuiReplayer, and every
GuiReplayer opened its own Database -- a connection and its caches, built on
the GUI thread. So the fix has two halves, and each is checked here: an open
replayer is reused rather than rebuilt, and the replayer reads through the
caller's connection rather than opening one.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import GuiReplayer as replayer_module
from fpdb_3_legacy.GuiHandViewer import GuiHandViewer
from fpdb_3_legacy.GuiReplayer import resolve_replayer_db
from fpdb_3_legacy.GuiTourHandViewer import TourHandViewer


class TestResolveReplayerDb:
    def test_an_explicit_connection_is_used_as_is(self) -> None:
        handed_over = MagicMock()
        mainwin = MagicMock(db=MagicMock())

        assert resolve_replayer_db(MagicMock(), MagicMock(), mainwin, handed_over) is handed_over

    def test_the_main_window_connection_is_the_next_choice(self) -> None:
        mainwin = MagicMock()
        mainwin.db = MagicMock()

        assert resolve_replayer_db(MagicMock(), MagicMock(), mainwin, None) is mainwin.db

    def test_a_connection_is_opened_only_when_there_is_none_to_borrow(self, monkeypatch) -> None:
        # The expensive path, and the one the freeze came from: it must be
        # reached only when neither the caller nor the main window has one.
        opened = MagicMock()
        monkeypatch.setattr(replayer_module.Database, "Database", MagicMock(return_value=opened))
        mainwin = MagicMock()
        mainwin.db = None

        assert resolve_replayer_db(MagicMock(), MagicMock(), mainwin, None) is opened

    def test_a_main_window_without_a_db_attribute_falls_through(self, monkeypatch) -> None:
        opened = MagicMock()
        monkeypatch.setattr(replayer_module.Database, "Database", MagicMock(return_value=opened))

        class Bare:
            pass

        assert resolve_replayer_db(MagicMock(), MagicMock(), Bare(), None) is opened


def _viewer(cls):
    """A viewer with just the attributes row_activated reads."""
    viewer = cls.__new__(cls)
    viewer.hands = {101: MagicMock(), 102: MagicMock()}
    viewer.colnum = {"HandId": 0}
    viewer.config = MagicMock()
    viewer.sql = MagicMock()
    viewer.main_window = MagicMock()
    viewer.db = MagicMock()
    return viewer


def _index_for(hand_id: int):
    index = MagicMock()
    sibling = MagicMock()
    sibling.data.return_value = str(hand_id)
    index.sibling.return_value = sibling
    return index


@pytest.mark.parametrize("viewer_cls", [GuiHandViewer, TourHandViewer])
class TestRowActivated:
    def test_an_open_replayer_is_reused(self, viewer_cls, monkeypatch) -> None:
        built = MagicMock()
        monkeypatch.setattr(replayer_module, "GuiReplayer", built)
        viewer = _viewer(viewer_cls)
        open_replayer = MagicMock()
        open_replayer.isVisible.return_value = True
        viewer.replayer = open_replayer

        viewer.row_activated(_index_for(102))

        built.assert_not_called()
        # Reused, pointed at the newly selected hand, and brought to the front.
        assert open_replayer.handlist == [101, 102]
        open_replayer.play_hand.assert_called_once_with(1)
        open_replayer.raise_.assert_called_once()
        open_replayer.activateWindow.assert_called_once()

    def test_a_closed_replayer_is_rebuilt_on_the_shared_connection(self, viewer_cls, monkeypatch) -> None:
        built = MagicMock()
        monkeypatch.setattr(replayer_module, "GuiReplayer", built)
        viewer = _viewer(viewer_cls)
        closed = MagicMock()
        closed.isVisible.return_value = False
        viewer.replayer = closed

        viewer.row_activated(_index_for(101))

        built.assert_called_once()
        # The viewer's own connection is handed over rather than a new one opened.
        assert built.call_args.kwargs["db"] is viewer.db
        closed.play_hand.assert_not_called()
        built.return_value.play_hand.assert_called_once_with(0)

    def test_the_first_open_builds_one(self, viewer_cls, monkeypatch) -> None:
        built = MagicMock()
        monkeypatch.setattr(replayer_module, "GuiReplayer", built)
        viewer = _viewer(viewer_cls)

        viewer.row_activated(_index_for(101))

        built.assert_called_once()
        assert built.call_args.kwargs["db"] is viewer.db
