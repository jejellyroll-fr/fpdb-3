"""Test suite for PT4 adapter module."""


from fpdb_3_legacy.pt4_adapter import Pt4Config, Pt4PlayerStat, StatComparison
from fpdb_3_legacy.pt4_adapter.comparator import _compare_bool, _compare_ratio


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
            "three_bet_opp": 5,
            "hand_id": 12345,
        }

        stat = Pt4PlayerStat.from_dict(data)
        assert stat.player_name == "Player1"
        assert stat.vpip is True
        assert stat.pfr is True
        assert stat.three_bet is False
        assert stat.three_bet_opp == 5
        assert stat.hand_id == 12345

    def test_from_dict_defaults(self) -> None:
        """Test Pt4PlayerStat.from_dict() with missing fields."""
        data = {"player_name": "Player1"}

        stat = Pt4PlayerStat.from_dict(data)
        assert stat.player_name == "Player1"
        assert stat.vpip is False
        assert stat.pfr is False
        assert stat.three_bet_opp == 0

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
        assert stat.three_bet_opp == 0
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
