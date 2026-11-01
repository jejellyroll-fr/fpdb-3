"""The HUD is notified only after the import transaction commits.

HUD_main reads each hand on its own DB connection; if the importer sends the
hand id while its write transaction is still open, that SELECT misses the
uncommitted row and the hand is dropped ("table info not found in DB"). This
locks the ordering so the send can never move back inside the transaction.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import Importer as ImporterModule
from fpdb_3_legacy.Importer import Importer


class _Recorder:
    """Shared event log so commit and send order can be compared."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def transaction(self):
        events = self.events

        class _Txn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                # Only a successful block commits; a real exception would roll back.
                if exc_type is None:
                    events.append("commit")
                return False

        return _Txn()


def _hand(dbid: int) -> MagicMock:
    hand = MagicMock(name=f"hand{dbid}")
    hand.dbid_hands = dbid
    hand.getHandId.return_value = dbid
    return hand


def _make_hhc(hands: list[MagicMock]) -> MagicMock:
    hhc = MagicMock(name="hhc")
    hhc.parsing_issues = []
    hhc.sitename = "PokerStars"
    hhc.getLastCharacterRead.return_value = 0
    hhc.numPartial = hhc.numSkipped = hhc.numErrors = 0
    hhc.numHands = len(hands)
    hhc.getProcessedHands.return_value = hands
    return hhc


@pytest.fixture
def importer(monkeypatch) -> Importer:
    """A bare Importer with only the attributes _import_hh_file touches."""
    imp = Importer.__new__(Importer)
    imp.config = MagicMock()
    imp.settings = {"testData": False, "cacheHHC": False}
    imp.pos_in_file = {}
    imp.import_issues = []
    imp.mode = "bulk"
    imp.caller = None
    imp.callHud = True
    imp.zmq_sender = None
    imp.hand_data_reporter = None

    recorder = _Recorder()
    database = MagicMock(name="database")
    database.transaction.side_effect = recorder.transaction
    database.nextHandId.return_value = 1
    imp.database = database
    imp._recorder = recorder

    def _record_send(hid) -> None:
        recorder.events.append(f"send:{hid}")

    sender = MagicMock(name="ZMQSender")
    sender.send_hand_id.side_effect = _record_send
    monkeypatch.setattr(ImporterModule, "ZMQSender", MagicMock(return_value=sender))
    return imp


def _fpdbfile() -> SimpleNamespace:
    site = SimpleNamespace(filter_name="PokerStars", name="PokerStars")
    return SimpleNamespace(path="/tmp/hh.txt", site=site, archive=False, fileId=7)


def _patch_parser(monkeypatch, hhc: MagicMock) -> None:
    monkeypatch.setattr(ImporterModule, "get_parser_class", lambda _name: lambda *a, **k: hhc)


def test_hands_are_sent_only_after_commit(importer, monkeypatch) -> None:
    hands = [_hand(101), _hand(102)]
    _patch_parser(monkeypatch, _make_hhc(hands))

    importer._import_hh_file(_fpdbfile())

    events = importer._recorder.events
    assert "commit" in events, "the import must commit"
    commit_at = events.index("commit")
    sends = [i for i, e in enumerate(events) if e.startswith("send:")]
    assert sends, "hands must be sent to the HUD"
    # Every send happens strictly after the single commit.
    assert all(i > commit_at for i in sends)
    assert events[commit_at + 1 :] == ["send:101", "send:102"]


def test_no_send_when_hud_disabled(importer, monkeypatch) -> None:
    importer.callHud = False
    _patch_parser(monkeypatch, _make_hhc([_hand(101)]))

    importer._import_hh_file(_fpdbfile())

    assert importer._recorder.events == ["commit"]


def test_nothing_sent_when_no_hands_stored(importer, monkeypatch) -> None:
    _patch_parser(monkeypatch, _make_hhc([]))

    importer._import_hh_file(_fpdbfile())

    # No stored hands means no transaction and no HUD notification.
    assert importer._recorder.events == []
