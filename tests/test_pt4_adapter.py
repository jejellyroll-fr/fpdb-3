"""Test suite for PT4 adapter module."""

import re
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

from fpdb_3_legacy.database_migrations import HANDS_PLAYERS_KEYS
from fpdb_3_legacy.pt4_adapter import (
    PT4_STATS_PER_HAND,
    Pt4Config,
    Pt4PlayerStat,
    StatComparison,
    compare_hand,
    connect_pt4,
)
from fpdb_3_legacy.pt4_adapter.comparator import FPDB_STATS_PER_HAND, _compare_bool, _compare_ratio

PT4_COLUMNS_FILE = Path(__file__).parent / "fixtures" / "pt4_schema_columns.txt"
PT4_ALIASES = {"s": "cash_hand_player_statistics", "h": "cash_hand_summary", "p": "player"}


def _pt4_conn(rows: list[dict]) -> SimpleNamespace:
    """A psycopg-shaped connection that answers one query with these rows."""
    names = list(rows[0]) if rows else ["player_name"]

    class Cursor:
        description = [SimpleNamespace(name=name) for name in names]

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, _query, _params):
            return None

        def fetchall(self):
            return [tuple(row[name] for name in names) for row in rows]

    return SimpleNamespace(cursor=Cursor)


def _fpdb_db(players: list[tuple]) -> SimpleNamespace:
    """A Database-shaped object on a real SQLite file, so FPDB_STATS_PER_HAND really runs."""
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE Players (id INTEGER PRIMARY KEY, name TEXT)")
    connection.execute(
        "CREATE TABLE HandsPlayers (handId INT, playerId INT, street0VPI INT, street0Aggr INT, "
        "street0_3BDone INT, street1Seen INT)",
    )
    for player_id, (name, *flags) in enumerate(players, start=1):
        connection.execute("INSERT INTO Players VALUES (?, ?)", (player_id, name))
        connection.execute("INSERT INTO HandsPlayers VALUES (7, ?, ?, ?, ?, ?)", (player_id, *flags))
    return SimpleNamespace(connection=connection, sql=SimpleNamespace(query={"placeholder": "?"}))


def _pt4_row(name: str, *, vpip=True, pfr=True, three_bet=False, saw_flop=True) -> dict:
    return {"player_name": name, "flg_vpip": vpip, "pfr": pfr, "three_bet": three_bet, "flg_f_saw": saw_flop}


class TestPt4Schema:
    """The adapter's SQL must name columns that exist: CI has no PT4 database to reject it."""

    def test_query_reads_only_columns_pt4_has(self) -> None:
        known = {
            line.strip() for line in PT4_COLUMNS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        used = {f"{PT4_ALIASES[alias]}.{column}" for alias, column in re.findall(r"\b([shp])\.(\w+)", PT4_STATS_PER_HAND)}
        assert len(used) > 15
        assert used <= known, sorted(used - known)

    def test_fpdb_query_reads_columns_fpdb_stores(self) -> None:
        for column in re.findall(r"\bhp\.(street\w+)", FPDB_STATS_PER_HAND):
            assert column in HANDS_PLAYERS_KEYS


class TestPt4Connection:
    def test_connection_is_read_only_on_the_server(self, monkeypatch) -> None:
        seen = {}
        monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda **kwargs: seen.update(kwargs)))
        connect_pt4(Pt4Config())
        assert "default_transaction_read_only=on" in seen["options"]


class TestCompareHand:
    def test_compares_each_stat_of_each_player(self) -> None:
        results = compare_hand(_pt4_conn([_pt4_row("alice")]), _fpdb_db([("alice", 1, 1, 0, 1)]), 1, 7)
        assert [(r.player, r.name, r.matched) for r in results] == [
            ("alice", "vpip", True),
            ("alice", "pfr", True),
            ("alice", "three_bet", True),
            ("alice", "saw_flop", True),
        ]

    def test_reports_a_stat_the_trackers_disagree_on(self) -> None:
        results = compare_hand(_pt4_conn([_pt4_row("alice", three_bet=True)]), _fpdb_db([("alice", 1, 1, 0, 1)]), 1, 7)
        assert [r.name for r in results if not r.matched] == ["three_bet"]

    def test_a_player_on_one_side_only_fails_instead_of_vanishing(self) -> None:
        results = compare_hand(_pt4_conn([_pt4_row("alice")]), _fpdb_db([("bob", 1, 1, 0, 1)]), 1, 7)
        assert [(r.player, r.name, r.pt4_value, r.fpdb_value, r.matched) for r in results] == [
            ("alice", "seated", True, False, False),
            ("bob", "seated", False, True, False),
        ]


class TestPt4Config:
    """Test suite for Pt4Config dataclass."""

    def test_config_defaults(self) -> None:
        """Test Pt4Config default values."""
        config = Pt4Config()
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.user == "postgres"
        assert config.password == "dbpass"
        assert config.database == "PT4 DB"

    def test_from_env(self, monkeypatch) -> None:
        """Test Pt4Config.from_env() with environment variables."""
        monkeypatch.setenv("PT4_HOST", "pt4server")
        monkeypatch.setenv("PT4_PORT", "5433")
        monkeypatch.setenv("PT4_USER", "pt4user")
        monkeypatch.setenv("PT4_PASSWORD", "pt4pass")
        monkeypatch.setenv("PT4_DATABASE", "PT4Production")

        config = Pt4Config.from_env()
        assert config.host == "pt4server"
        assert config.port == 5433
        assert config.user == "pt4user"
        assert config.password == "pt4pass"
        assert config.database == "PT4Production"


class TestPt4PlayerStat:
    """Test suite for Pt4PlayerStat dataclass."""

    def test_from_dict_basic(self) -> None:
        """Test Pt4PlayerStat.from_dict() with basic data."""
        data = {
            "player_name": "Player1",
            "flg_vpip": True,
            "pfr": True,
            "three_bet": False,
            "three_bet_opp": True,
            "flg_f_saw": True,
            "flg_showdown": True,
            "hand_id": 12345,
            "hand_no": "RC58843003",
        }

        stat = Pt4PlayerStat.from_dict(data)
        assert stat.player_name == "Player1"
        assert stat.vpip is True
        assert stat.pfr is True
        assert stat.three_bet is False
        assert stat.three_bet_opp is True
        assert stat.saw_flop is True
        assert stat.saw_showdown is True
        assert stat.hand_id == 12345
        assert stat.hand_no == "RC58843003"

    def test_from_dict_defaults(self) -> None:
        """Test Pt4PlayerStat.from_dict() with missing fields."""
        data = {"player_name": "Player1"}

        stat = Pt4PlayerStat.from_dict(data)
        assert stat.player_name == "Player1"
        assert stat.vpip is False
        assert stat.pfr is False
        assert stat.three_bet_opp is False

    def test_from_dict_null_values(self) -> None:
        """Test Pt4PlayerStat.from_dict() handles null values."""
        data = {
            "player_name": "Player1",
            "flg_vpip": None,
            "three_bet_opp": None,
            "amt_won": None,
        }

        stat = Pt4PlayerStat.from_dict(data)
        assert stat.vpip is False
        assert stat.three_bet_opp is False
        assert stat.won == 0


class TestComparator:
    """Test suite for comparison functions."""

    def test_compare_bool_match(self) -> None:
        """Test _compare_bool returns matched=True when values equal."""
        result = _compare_bool("test_stat", True, True)
        assert result.matched is True
        assert result.pt4_value is True
        assert result.fpdb_value is True

    def test_compare_bool_no_match(self) -> None:
        """Test _compare_bool returns matched=False when values differ."""
        result = _compare_bool("test_stat", True, False)
        assert result.matched is False

    def test_compare_bool_null_handling(self) -> None:
        """Test _compare_bool handles null values."""
        result = _compare_bool("test_stat", None, True)
        assert result.pt4_value is False
        assert result.fpdb_value is True

    def test_compare_ratio_match(self) -> None:
        """Test _compare_ratio with matching values."""
        result = _compare_ratio("test_ratio", 10, 20, 0.5)
        assert result.matched is True
        assert result.pt4_value == 0.5
        assert result.fpdb_value == 0.5

    def test_compare_ratio_within_tolerance(self) -> None:
        """Test _compare_ratio within tolerance."""
        result = _compare_ratio("test_ratio", 10, 20, 0.49, tolerance=0.02)
        assert result.matched is True

    def test_compare_ratio_outside_tolerance(self) -> None:
        """Test _compare_ratio outside tolerance."""
        result = _compare_ratio("test_ratio", 10, 20, 0.3, tolerance=0.05)
        assert result.matched is False

    def test_compare_ratio_zero_denominator(self) -> None:
        """Test _compare_ratio handles zero denominator."""
        result = _compare_ratio("test_ratio", 10, 0, 0.5)
        assert result.pt4_value == 0.0

    def test_compare_ratio_null_values(self) -> None:
        """Test _compare_ratio handles null/invalid values."""
        result = _compare_ratio("test_ratio", None, None, "invalid")
        assert result.matched is False


class TestStatComparison:
    """Test suite for StatComparison dataclass."""

    def test_stat_comparison_creation(self) -> None:
        """Test StatComparison can be created with all fields."""
        result = StatComparison(
            name="test_stat",
            pt4_value=0.5,
            fpdb_value=0.48,
            matched=True,
            delta=0.02,
        )
        assert result.name == "test_stat"
        assert result.pt4_value == 0.5
        assert result.fpdb_value == 0.48
        assert result.delta == 0.02
