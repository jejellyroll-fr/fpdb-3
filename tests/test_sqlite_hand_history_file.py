"""A hand history stored in a SQLite file must still be readable.

The Microgaming client writes GameHistory.dat, a SQLite database whose
HandHistory.XMLDump column holds exactly the <Game> XML of its text export.
fpdb only read text, so the file was rejected whole ("Unable to read file with
any codec in list") even though the parser understands every hand in it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.HandHistoryConverter import unpack_sqlite_hand_history
from fpdb_3_legacy.MicrogamingToFpdb import Microgaming

GAME_HISTORY = Path("regression-test-files/unsupported-sites/microgaming/GameHistory.dat")


def test_plain_text_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "history.txt"
    path.write_bytes(b"----PRIMA.DAT----\n<Game id=\"1\" ...")

    assert unpack_sqlite_hand_history(str(path), path.read_bytes()) is None


def test_a_database_without_hand_histories_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "other.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE Something (id INTEGER)")
    conn.commit()
    conn.close()

    assert unpack_sqlite_hand_history(str(path), path.read_bytes()) is None


@pytest.mark.skipif(not GAME_HISTORY.is_file(), reason="GameHistory.dat fixture missing")
def test_every_hand_of_the_database_is_unpacked() -> None:
    text = unpack_sqlite_hand_history(str(GAME_HISTORY), GAME_HISTORY.read_bytes())

    assert text is not None
    assert text.count("----PRIMA.DAT----") == 29
    assert text.lstrip().startswith("----PRIMA.DAT----")


@pytest.mark.skipif(not GAME_HISTORY.is_file(), reason="GameHistory.dat fixture missing")
def test_the_parser_reads_the_unpacked_hands() -> None:
    parser = Microgaming(config=Config(), in_path=str(GAME_HISTORY), autostart=True)

    hands = parser.getProcessedHands()

    assert len(hands) == 29
    assert {hand.gametype["category"] for hand in hands} == {"holdem"}
    assert all(hand.players for hand in hands)
