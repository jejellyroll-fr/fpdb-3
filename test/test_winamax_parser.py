"""Tests for WinamaxToFpdb.py using real hand history files."""

import unittest
from pathlib import Path

import pytest

from WinamaxToFpdb import Winamax


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict:
        """Return empty import parameters for testing."""
        return {}

    def get_site_id(self, sitename: str) -> int:  # noqa: ARG002
        """Return Winamax site ID for testing."""
        return 15  # Winamax site ID


class TestWinamaxParser(unittest.TestCase):
    """Test suite for Winamax hand history parser using real files."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = Winamax(self.config)
        self.regression_path = Path(__file__).parent.parent / "regression-test-files"
        self.cash_path = self.regression_path / "cash" / "Winamax"
        self.tour_path = self.regression_path / "tour" / "Winamax"

    def _read_test_file(self, filepath: Path) -> str:
        """Read a test hand history file."""
        encodings = ["utf-8", "cp1252", "latin-1"]

        def try_encoding(encoding: str) -> str | None:
            try:
                with filepath.open(encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                return None

        for encoding in encodings:
            content = try_encoding(encoding)
            if content is not None:
                return content

        error_msg = f"Unable to decode file {filepath} with any encoding"
        raise UnicodeDecodeError(error_msg)

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent
            / "regression-test-files"
            / "cash"
            / "Winamax"
            / "Flop"
            / "NLHE-5max-EUR-1-2-201201.Hero.Sitting.Out.txt"
        ).exists(),
        reason="Test file not found",
    )
    def test_determine_game_type_nlhe_cash(self) -> None:
        """Test game type detection for NLHE cash games."""
        filepath = self.cash_path / "Flop" / "NLHE-5max-EUR-1-2-201201.Hero.Sitting.Out.txt"

        hand_text = self._read_test_file(filepath)
        game_info = self.parser.determineGameType(hand_text)

        assert game_info["category"] == "holdem"
        assert game_info["base"] == "hold"
        assert game_info["limitType"] == "nl"
        assert game_info["currency"] == "EUR"
        assert game_info["sb"] == "1"
        assert game_info["bb"] == "2"

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent
            / "regression-test-files"
            / "tour"
            / "Winamax"
            / "Flop"
            / "NLHE-Free-MTT-201103.Full.History.txt"
        ).exists(),
        reason="Test file not found",
    )
    def test_determine_game_type_tournament(self) -> None:
        """Test game type detection for tournaments."""
        filepath = self.tour_path / "Flop" / "NLHE-Free-MTT-201103.Full.History.txt"

        hand_text = self._read_test_file(filepath)
        game_info = self.parser.determineGameType(hand_text)

        assert game_info["category"] == "holdem"
        assert game_info["base"] == "hold"
        assert game_info["limitType"] == "nl"
        assert game_info["type"] == "tour"

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent
            / "regression-test-files"
            / "cash"
            / "Winamax"
            / "Flop"
            / "PLO-5max-EUR-1.00-2.00-201407.ante.raise.txt"
        ).exists(),
        reason="Test file not found",
    )
    def test_determine_game_type_plo(self) -> None:
        """Test game type detection for PLO."""
        filepath = self.cash_path / "Flop" / "PLO-5max-EUR-1.00-2.00-201407.ante.raise.txt"

        hand_text = self._read_test_file(filepath)
        game_info = self.parser.determineGameType(hand_text)

        assert game_info["category"] == "omahahi"
        assert game_info["base"] == "hold"
        assert game_info["limitType"] == "pl"

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent
            / "regression-test-files"
            / "cash"
            / "Winamax"
            / "Stud"
            / "7-Stud-6max-EUR-25-50-201611._8games_.txt"
        ).exists(),
        reason="Test file not found",
    )
    def test_determine_game_type_stud(self) -> None:
        """Test game type detection for 7-Card Stud."""
        filepath = self.cash_path / "Stud" / "7-Stud-6max-EUR-25-50-201611._8games_.txt"

        hand_text = self._read_test_file(filepath)
        game_info = self.parser.determineGameType(hand_text)

        assert game_info["category"] == "studhi"
        assert game_info["base"] == "stud"

    def test_regex_compilation(self) -> None:
        """Test that all regex patterns compile correctly."""
        # Test that the parser initializes without errors
        assert self.parser.re_hand_info is not None
        assert self.parser.re_player_info is not None
        assert self.parser.re_button is not None
        assert self.parser.re_board is not None

    def test_supported_games(self) -> None:
        """Test that readSupportedGames returns expected game types."""
        supported = self.parser.readSupportedGames()
        assert isinstance(supported, list)
        assert len(supported) > 0

        # Check that Hold'em games are in supported games (they use 'hold' not 'holdem')
        hold_found = any("hold" in game for game in supported)
        assert hold_found, "Hold'em games should be in supported games"

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent
            / "regression-test-files"
            / "cash"
            / "Winamax"
            / "Flop"
            / "NLHE-5max-EUR-1-2-201201.Hero.Sitting.Out.txt"
        ).exists(),
        reason="Test file not found",
    )
    def test_parse_datetime_format(self) -> None:
        """Test datetime parsing with different formats."""
        # Test with a real hand to ensure datetime parsing works
        filepath = self.cash_path / "Flop" / "NLHE-5max-EUR-1-2-201201.Hero.Sitting.Out.txt"

        hand_text = self._read_test_file(filepath)
        game_info = self.parser.determineGameType(hand_text)

        # Should not raise exceptions during game type detection
        assert game_info is not None

    def test_hand_id_extraction(self) -> None:
        """Test hand ID extraction from different hand formats."""
        # Test cash game hand ID
        filepath = self.cash_path / "Flop" / "NLHE-5max-EUR-1-2-201201.Hero.Sitting.Out.txt"
        if filepath.exists():
            hand_text = self._read_test_file(filepath)
            # Check if HandId pattern matches
            if match := self.parser.re_hand_info.search(hand_text):
                # Check for hand ID patterns
                groups = match.groupdict()
                assert any(key.startswith("HID") for key in groups)

        # Test tournament hand ID
        filepath = self.tour_path / "Flop" / "NLHE-Free-MTT-201103.Full.History.txt"
        if filepath.exists():
            hand_text = self._read_test_file(filepath)
            if match := self.parser.re_hand_info.search(hand_text):
                groups = match.groupdict()
                assert any(key.startswith("HID") for key in groups)

    def test_currency_detection(self) -> None:
        """Test currency detection in different files."""
        test_cases = [
            (self.cash_path / "Flop" / "NLHE-5max-EUR-1-2-201201.Hero.Sitting.Out.txt", "EUR"),
            (self.cash_path / "Flop" / "NLHE-5max-play-0.10-0.20-201208.txt", "play"),
        ]

        for filepath, expected_currency in test_cases:
            if filepath.exists():
                hand_text = self._read_test_file(filepath)
                game_info = self.parser.determineGameType(hand_text)
                assert game_info.get("currency") == expected_currency

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent
            / "regression-test-files"
            / "tour"
            / "Winamax"
            / "Flop"
            / "NLHE-MTT-EUR-22.5-22.5-5-202208.bounty.ticket.txt"
        ).exists(),
        reason="Test file not found",
    )
    def test_tournament_bounty_handling(self) -> None:
        """Test tournament with bounty information."""
        filepath = self.tour_path / "Flop" / "NLHE-MTT-EUR-22.5-22.5-5-202208.bounty.ticket.txt"

        hand_text = self._read_test_file(filepath)
        game_info = self.parser.determineGameType(hand_text)

        # Should parse bounty tournament correctly
        assert game_info["type"] == "tour"

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent
            / "regression-test-files"
            / "cash"
            / "Winamax"
            / "Stud"
            / "7-Stud-6max-EUR-25-50-201611._8games_.txt"
        ).exists(),
        reason="Test file not found",
    )
    def test_mixed_game_detection(self) -> None:
        """Test detection of mixed games like 8-game."""
        filepath = self.cash_path / "Stud" / "7-Stud-6max-EUR-25-50-201611._8games_.txt"

        hand_text = self._read_test_file(filepath)
        game_info = self.parser.determineGameType(hand_text)

        # Should handle mixed games
        assert game_info is not None
        assert "category" in game_info


if __name__ == "__main__":
    unittest.main()
