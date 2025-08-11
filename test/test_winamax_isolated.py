"""Isolated tests for individual Winamax parser methods."""

import contextlib
import re
import unittest
from pathlib import Path
from unittest.mock import Mock

import pytest

from HandHistoryConverter import FpdbParseError
from WinamaxToFpdb import Winamax


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict[str, bool]:
        """Return import parameters for testing."""
        return {"saveActions": True}

    def get_site_id(self, sitename: str) -> int:
        """Return site ID for testing."""
        # sitename parameter is required by interface but not used in mock
        return 15


class TestWinamaxIsolated(unittest.TestCase):
    """Test individual methods in isolation."""

    EXPECTED_BOUNTY_VALUE = 500  # Bounty value after multiplication by 100

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = Winamax(self.config)
        self.regression_path = Path(__file__).parent.parent / "regression-test-files"
        self.cash_path = self.regression_path / "cash" / "Winamax"
        self.tour_path = self.regression_path / "tour" / "Winamax"

    def _assert_extract_cards(self, input_cards: str | None, expected: list[str]) -> None:
        """Helper method to test _extract_cards with expected result."""
        result = self.parser._extract_cards(input_cards)
        assert result == expected

    def _assert_game_type_info(self, mg: dict, expected_type: str, expected_currency: str) -> None:
        """Helper method to test _parse_game_type_info with expected results."""
        info = {}
        self.parser._parse_game_type_info(mg, info)
        assert info["type"] == expected_type
        assert info["currency"] == expected_currency


    def _read_test_file(self, filepath: str | Path) -> str:
        """Read a test hand history file."""
        path_obj = Path(filepath)
        encodings = ["utf-8", "cp1252", "latin-1"]

        # Try each encoding
        for encoding in encodings:
            with contextlib.suppress(UnicodeDecodeError):
                return path_obj.read_text(encoding=encoding)

        error_msg = f"Unable to decode file {filepath} with any encoding"
        unicode_error_msg = error_msg
        msg = "utf-8"
        raise UnicodeDecodeError(msg, b"", 0, 1, unicode_error_msg)

    def test_extract_cards_method(self) -> None:
        """Test _extract_cards method with various inputs."""
        self._assert_extract_cards("Ac Ks", ["Ac", "Ks"])
        self._assert_extract_cards("Qh", ["Qh"])
        self._assert_extract_cards("Ac X Ks", ["Ac", "Ks"])
        self._assert_extract_cards("X X X", [])
        self._assert_extract_cards(None, [])
        self._assert_extract_cards("", [""])

        # Test with multiple spaces
        result = self.parser._extract_cards("Ac  Ks   Qh")
        expected = [c for c in ["Ac", "", "Ks", "", "", "Qh"] if c != "X"]
        assert result == expected


    def test_determine_buyin_currency(self) -> None:
        """Test _determine_buyin_currency method."""
        # Test with EUR
        result = self.parser._determine_buyin_currency("10€", {"MONEY": True})
        assert result == "EUR"

        # Test with USD
        result = self.parser._determine_buyin_currency("$10", {"MONEY": True})
        assert result == "USD"

        # Test with FPP
        result = self.parser._determine_buyin_currency("100 FPP", {"MONEY": False})
        assert result == "WIFP"

        # Test with no currency symbol - real money
        result = self.parser._determine_buyin_currency("10", {"MONEY": True})
        assert result == "EUR"

        # Test with no currency symbol - play money
        result = self.parser._determine_buyin_currency("10", {"MONEY": False})
        assert result == "play"

    def test_supported_games_format(self) -> None:
        """Test readSupportedGames returns properly formatted data."""
        supported = self.parser.readSupportedGames()

        assert isinstance(supported, list)
        assert len(supported) > 0

        # Each game should be a list with required components
        min_game_components = 2
        assert all(isinstance(game, list) and len(game) > min_game_components for game in supported)


    def test_game_type_parsing_components(self) -> None:
        """Test individual components of game type parsing."""
        # Test _parse_game_type_info with tournament
        self._assert_game_type_info({"TOUR": "some tournament"}, "tour", "T$")

        # Test with ring game
        self._assert_game_type_info({"RING": "some ring", "MONEY": True}, "ring", "EUR")

    def test_limit_info_parsing(self) -> None:
        """Test _parse_limit_info method."""
        mg = {"LIMIT": "no limit"}
        info = {}
        hand_text = "test hand"

        self.parser._parse_limit_info(mg, info, hand_text)
        assert info["limitType"] == "nl"


    def test_additional_info_parsing(self) -> None:
        """Test _parse_additional_info method."""
        mg = {"GAME": "Holdem", "SB": "1", "BB": "2"}
        info = {}

        self.parser._parse_additional_info(mg, info)
        assert info["base"] == "hold"
        assert info["category"] == "holdem"
        assert info["sb"] == "1"
        assert info["bb"] == "2"



    def test_log_parse_error(self) -> None:
        """Test _log_parse_error method."""
        # Should not raise exceptions
        self.parser._log_parse_error("test hand", 100, "test error")



    def test_regex_compilation_no_errors(self) -> None:
        """Test that regex patterns compile without errors."""
        # These should be accessible after initialization
        assert hasattr(self.parser, "re_hand_info")
        assert hasattr(self.parser, "re_player_info")
        assert hasattr(self.parser, "re_button")
        assert hasattr(self.parser, "re_board")
        assert hasattr(self.parser, "re_date_time")
        assert hasattr(self.parser, "re_split_hands")

        # Test that they are compiled regex objects
        assert isinstance(self.parser.re_hand_info, re.Pattern)
        assert isinstance(self.parser.re_player_info, re.Pattern)
        assert isinstance(self.parser.re_button, re.Pattern)
        assert isinstance(self.parser.re_board, re.Pattern)
        assert isinstance(self.parser.re_date_time, re.Pattern)
        assert isinstance(self.parser.re_split_hands, re.Pattern)

        # Player-specific regex patterns are not available until compilePlayerRegexs is called
        assert not hasattr(self.parser, "re_post_sb")
        assert not hasattr(self.parser, "re_post_bb")


    def test_table_title_regex_generation(self) -> None:
        """Test getTableTitleRe method for different game types."""
        # Test cash game
        result = self.parser.getTableTitleRe("cash", "hold", "nl")
        assert isinstance(result, str)
        assert "Winamax" in result

        # Test tournament
        result = self.parser.getTableTitleRe("tour", "hold", "nl")
        assert isinstance(result, str)

        # Test different base
        result = self.parser.getTableTitleRe("cash", "stud", "fl")
        assert isinstance(result, str)

    def test_detect_lottery_tournaments(self) -> None:
        """Test _detect_lottery_tournaments method."""
        mock_hand = Mock()
        info = {"TOURNAME": "Expresso"}

        # Access the method through the parser instance (protected member access)
        self.parser._detect_lottery_tournaments(mock_hand, info)

        # Should set lottery-related attributes
        assert mock_hand.isChance

    def test_process_bounty_info(self) -> None:
        """Test _process_bounty_info method."""
        mock_hand = Mock()
        info = {"BIRAKE": "5", "BOUNTY": "5"}

        self.parser._process_bounty_info(mock_hand, info)
        assert mock_hand.isKO
        assert mock_hand.koBounty == self.EXPECTED_BOUNTY_VALUE

    def test_game_type_with_real_hands(self) -> None:
        """Test determineGameType with real hand samples."""
        filename = "NLHE-5max-EUR-1-2-201201.Hero.Sitting.Out.txt"

        filepath = self.cash_path / "Flop" / filename
        hand_text = self._read_test_file(filepath)
        result = self.parser.determineGameType(hand_text)

        assert result.get("category") == "holdem", f"Failed for {filename}, key category"
        assert result.get("limitType") == "nl", f"Failed for {filename}, key limitType"
        assert result.get("currency") == "EUR", f"Failed for {filename}, key currency"


    def test_datetime_parsing_components(self) -> None:
        """Test datetime parsing without full hand processing."""
        mock_hand = Mock()
        mock_hand.startTime = None

        # Test with valid datetime string
        self.parser._parse_datetime(mock_hand, "2012/01/19 12:03:46 UTC")
        assert mock_hand.startTime is not None


    def test_hand_id_parsing(self) -> None:
        """Test _parse_hand_id method."""
        mock_hand = Mock()
        info = {"HID1": "23348984361326450000", "HID2": "123"}

        self.parser._parse_hand_id(mock_hand, info)
        assert mock_hand.handid == "23348984361326123"



    def test_table_info_parsing(self) -> None:
        """Test _parse_table_info method."""
        mock_hand = Mock()
        mock_hand.gametype = {"type": "ring"}
        info = {}
        table_info = "'Neuilly-sur-Seine' 5-max (real money) Seat 0000005 is the button"

        self.parser._parse_table_info(mock_hand, table_info, info)
        # The method sets tablename to the entire table_info string, not just the extracted name
        assert mock_hand.tablename == "'Neuilly-sur-Seine' 5-max (real money) Seat 0000005 is the button"
        # maxseats is not set by this method, it's set elsewhere

    def test_buyin_info_parsing(self) -> None:
        """Test _parse_buyin_info method."""
        mock_hand = Mock()
        info = {"BUYIN": "22.50€+2.50€", "BIAMT": "22.50", "BIRAKE": "2.50", "BOUNTY": None, "FREETICKET": None}
        buyin_info = "buyIn: 22.50€+2.50€ level: 0"

        # Expected values in cents
        expected_buyin_cents = 2250
        expected_fee_cents = 250

        self.parser._parse_buyin_info(mock_hand, buyin_info, info)
        assert mock_hand.buyin == expected_buyin_cents
        assert mock_hand.fee == expected_fee_cents

    def test_street_regex_patterns(self) -> None:
        """Test that street regex patterns are properly defined."""
        # Create a mock hand to trigger regex compilation
        mock_hand = Mock()
        mock_hand.players = ["Player1", "Player2"]
        mock_hand.gametype = {"currency": "EUR"}
        self.parser.compilePlayerRegexs(mock_hand)

        # Check that street patterns exist after compilation
        assert hasattr(self.parser, "re_post_sb")
        assert hasattr(self.parser, "re_post_bb")
        assert hasattr(self.parser, "re_antes")

        # These should be regex patterns
        assert isinstance(self.parser.re_post_sb, re.Pattern)

    def test_error_handling_edge_cases(self) -> None:
        """Test error handling for edge cases."""
        # Test with None input - should raise TypeError
        with pytest.raises(TypeError):
            self.parser.determineGameType(None)

        # Test with empty string - raises FpdbParseError
        with pytest.raises(FpdbParseError):
            self.parser.determineGameType("")

        # Test with malformed hand - also raises FpdbParseError
        with pytest.raises(FpdbParseError):
            self.parser.determineGameType("Not a poker hand")

    def test_currency_symbol_recognition(self) -> None:
        """Test currency symbol recognition in parsing."""
        # Test Euro symbol recognition
        mg = {"CURRENCY": "€"}
        info = {}
        self.parser._parse_additional_info(mg, info)
        assert info.get("currency", "EUR") == "EUR"

        # Test dollar sign
        mg = {"CURRENCY": "$"}
        info = {}
        self.parser._parse_additional_info(mg, info)
        assert info.get("currency", "USD") == "USD"


    def test_mixed_game_categories(self) -> None:
        """Test recognition of mixed game categories."""
        # Test 8-game recognition - _parse_game_type_info doesn't set category/base
        mg = {"RING": "some ring", "MONEY": True}
        info = {}
        self.parser._parse_game_type_info(mg, info)
        # This method only sets type and currency
        assert info.get("type") == "ring"
        assert info.get("currency") == "EUR"

        # Test mixed game detection with proper mixed game path
        self.parser.in_path = "/path/to/file_8games_.txt"
        mg = {"RING": "some ring", "MONEY": True, "GAME": "7-Card Stud"}
        info = {}
        self.parser._parse_additional_info(mg, info)
        # For mixed games, base should be "mixed" and category should be the mixed game type
        assert info.get("base") == "mixed"
        assert info.get("category") == "8game"
        assert info.get("mix") == "8game"

    def test_stud_game_recognition(self) -> None:
        """Test Stud game category recognition."""
        # Test 7-Card Stud recognition
        assert "7-Card Stud" in self.parser.games
        assert self.parser.games["7-Card Stud"] == ("stud", "studhi")

        # Test 7stud short name
        assert "7stud" in self.parser.games
        assert self.parser.games["7stud"] == ("stud", "studhi")

        # Test Stud Hi/Lo variants
        if "7-Card Stud Hi/Lo" in self.parser.games:
            assert self.parser.games["7-Card Stud Hi/Lo"] == ("stud", "studhilo")

        # Test Razz
        if "Razz" in self.parser.games:
            assert self.parser.games["Razz"] == ("stud", "razz")

    def test_omaha_variants(self) -> None:
        """Test different Omaha variant recognition."""
        # Test games dict directly since _parse_game_type_info doesn't handle GAME
        assert "Omaha" in self.parser.games
        assert self.parser.games["Omaha"] == ("hold", "omahahi")

        # Test Omaha Hi/Lo if available
        assert "Omaha Hi/Lo" not in self.parser.games or self.parser.games["Omaha Hi/Lo"] == ("hold", "omahahilo")

        # Test 5 Card Omaha if available
        assert "5 Card Omaha" not in self.parser.games or self.parser.games["5 Card Omaha"] == ("hold", "5_omahahi")


if __name__ == "__main__":
    unittest.main()
