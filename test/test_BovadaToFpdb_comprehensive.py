"""Comprehensive tests for BovadaToFpdb - Exhaustive parser validation.

This module tests the Bovada parser exhaustively with all archive formats,
verifying that all important data is correctly extracted.
"""

import contextlib
import logging
import os
import unittest
from pathlib import Path

try:
    from BovadaToFpdb import Bovada, FpdbHandPartial, FpdbParseError
    from Configuration import Config
    from Hand import DrawHand, Hand, HoldemOmahaHand, StudHand
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
    from BovadaToFpdb import Bovada, FpdbHandPartial, FpdbParseError
    from Configuration import Config
    from Hand import DrawHand, Hand, HoldemOmahaHand, StudHand

# Logging configuration for debugging
logging.basicConfig(level=logging.WARNING)


class MockHand:
    """Mock hand object for testing purposes."""

    def __init__(self, hand_text: str, gametype: dict, in_path: str = "") -> None:
        """Initialize mock hand with basic attributes."""
        self.handText = hand_text
        self.gametype = gametype
        self.in_path = in_path
        self.players = []
        self.buttonpos = None
        self.maxseats = 0
        self.handid = None
        self.startTime = None
        self.tourNo = None
        self.tourneyId = None
        self.tourneyName = None
        self.tourneyTypeId = None
        self.buyin = None
        self.buyinCurrency = None
        self.fee = None
        self.level = None
        self.mixed = None
        self.isSng = False
        self.isRebuy = False
        self.isAddOn = False
        self.isKO = False
        self.isProgressive = False
        self.isMatrix = False
        self.isShootout = False
        self.tablename = ""
        self.hero = ""
        self.maxseats = 0
        self.counted_seats = 0
        self.runItTimes = 0
        self.version = "LEGACY"
        self.cancelled = False
        self.streets = {}
        self.actions = []
        self.actionStreets = ["PREFLOP", "FLOP", "TURN", "RIVER"]
        self.communityStreets = ["FLOP", "TURN", "RIVER"]
        self.holeStreets = ["PREFLOP"]
        self.allStreets = ["PREFLOP", "FLOP", "TURN", "RIVER"]
        self.stacks = {}

    def addPlayer(self, seat: int, name: str, chips: str) -> None:
        """Add a player to the hand."""
        self.players.append((seat, name, chips))
        self.stacks[name] = float(chips)

    def setUncalledBets(self, _value: str) -> None:
        """Set uncalled bets."""

    def addBlind(self, _player: str, _blindtype: str, _amount: str) -> None:
        """Add a blind."""

    def addCall(self, street: str, player: str, amount: str) -> None:
        """Add a call action."""
        self.actions.append((street, player, "call", amount))

    def addRaise(self, street: str, player: str, amount: str) -> None:
        """Add a raise action."""
        self.actions.append((street, player, "raise", amount))

    def addBet(self, street: str, player: str, amount: str) -> None:
        """Add a bet action."""
        self.actions.append((street, player, "bet", amount))

    def addFold(self, street: str, player: str) -> None:
        """Add a fold action."""
        self.actions.append((street, player, "fold", None))

    def addCheck(self, street: str, player: str) -> None:
        """Add a check action."""
        self.actions.append((street, player, "check", None))

    def addRaiseTo(self, street: str, player: str, amount: str) -> None:
        """Add a raise to action."""
        self.actions.append((street, player, "raise", amount))

    def addAllIn(self, street: str, player: str, amount: str) -> None:
        """Add an all-in action."""
        self.actions.append((street, player, "allin", amount))

    def addComplete(self, street: str, player: str, amount: str) -> None:
        """Add a complete action."""
        self.actions.append((street, player, "complete", amount))

    def addBringIn(self, street: str, player: str, amount: str) -> None:
        """Add a bring-in action."""
        self.actions.append((street, player, "bringin", amount))

    def addAnte(self, _player: str, _amount: str) -> None:
        """Add an ante."""

    def addCards(self, _street: str, _player: str, _cards: list[str]) -> None:
        """Add cards for a player."""

    def addCollectPot(self, player: str, pot: str) -> None:
        """Add collected pot."""



class ComprehensiveBovadaTest(unittest.TestCase):
    """Exhaustive tests of the Bovada parser with all archive files."""

    @classmethod
    def setUpClass(cls) -> None:
        """General test configuration."""
        cls.config = Config()
        # Setup site IDs for testing
        cls.config.site_ids = {"Bovada": 1, "PokerStars": 2}  # Mock site IDs
        cls.parser = Bovada(config=cls.config)

        # Paths to test files
        cls.test_files_dir = Path(__file__).parent / ".." / "regression-test-files"

        # Collect all Bovada files
        cls.bovada_files = []
        for root, _, files in os.walk(cls.test_files_dir):
            if "Bovada" in root:
                for file in files:
                    if file.endswith(".txt"):
                        cls.bovada_files.append(Path(root) / file)


    def setUp(self) -> None:
        """Configuration for each test."""
        self.config.site_ids = {"Bovada": 1, "PokerStars": 2}  # Mock site IDs
        self.parser = Bovada(config=self.config)
        self.validation_errors = []

    def read_hand_file(self, file_path: str) -> str:
        """Reads a hand file and returns the content."""
        try:
            with Path(file_path).open(encoding="utf-8-sig") as f:
                return f.read()
        except (OSError, UnicodeDecodeError) as e:
            self.fail(f"Cannot read the file {file_path}: {e}")

    def validate_hand_data(self, hand: Hand, file_path: str) -> list[str]:
        """Validates that a hand contains all essential data."""
        filename = Path(file_path).name
        errors = []

        # 1. Required basic data
        errors.extend(self._validate_basic_data(hand))

        # 2. Players
        errors.extend(self._validate_players(hand))

        # 3. Game type specific data
        errors.extend(self._validate_tournament_data(hand))

        # 4. Actions (if not a partial hand)
        errors.extend(self._validate_actions(hand, filename))

        # 5. Pot and rake (if available)
        errors.extend(self._validate_pot(hand))

        # 6. Street-specific validation
        errors.extend(self._validate_streets(hand, filename))

        return errors

    def _validate_basic_data(self, hand: Hand) -> list[str]:
        """Validates required basic data."""
        errors = []
        if not hand.handid:
            errors.append("missing handid")
        if not hand.startTime:
            errors.append("missing startTime")
        if not hand.gametype:
            errors.append("missing gametype")
        return errors

    def _validate_players(self, hand: Hand) -> list[str]:
        """Validates player data."""
        errors = []
        if not hand.players:
            errors.append("No players found")
        else:
            required_keys = ["name", "stack", "seat"]
            errors.extend(
                f"Incomplete player data: {player}"
                for player in hand.players
                if any(key not in player for key in required_keys)
            )
        return errors

    def _validate_tournament_data(self, hand: Hand) -> list[str]:
        """Validates tournament-specific data."""
        errors = []
        if hand.gametype and hand.gametype.get("type") == "tour":
            if hand.buyin is None:
                errors.append("missing buyin for tournament")
            if hand.fee is None:
                errors.append("missing fee for tournament")
        return errors

    def _validate_actions(self, hand: Hand, filename: str) -> list[str]:
        """Validates hand actions."""
        errors = []
        if not filename.endswith(".partial.txt"):
            total_actions = sum(
                len([a for a in hand.actions if a[0] == street])
                for street in hand.actionStreets
            )
            if total_actions == 0:
                errors.append("No actions found")
        return errors

    def _validate_pot(self, hand: Hand) -> list[str]:
        """Validates pot data."""
        errors = []
        if hand.totalpot is not None and hand.totalpot <= 0:
            errors.append(f"invalid totalpot: {hand.totalpot}")
        return errors

    def _validate_streets(self, hand: Hand, filename: str) -> list[str]:
        """Validates street-specific data."""
        errors = []
        if (hand.gametype and
            hand.gametype.get("base") == "hold" and
            any(hand.streets.get(street) for street in ["FLOP", "TURN", "RIVER"])):
            post_flop_actions = [a for a in hand.actions if a[0] in ["FLOP", "TURN", "RIVER"]]
            if not post_flop_actions and not filename.endswith(".partial.txt"):
                errors.append("Post-flop streets present but no post-flop actions")
        return errors

    def _create_hand_object(self, gametype: dict, hand_text: str) -> Hand | None:
        """Create appropriate Hand object based on game type."""
        if gametype["base"] == "hold":
            return HoldemOmahaHand(self.config, self.parser, "Bovada", gametype, hand_text)
        if gametype["base"] == "stud":
            return StudHand(self.config, self.parser, "Bovada", gametype, hand_text)
        if gametype["base"] == "draw":
            return DrawHand(self.config, self.parser, "Bovada", gametype, hand_text)
        return None

    def _parse_single_hand(self, hand_text: str, hand_index: int, filename: Path) -> list[str]:
        """Parse a single hand and return any validation errors."""
        gametype = self.parser.determineGameType(hand_text.split("\n\n")[0])

        hand = self._create_hand_object(gametype, hand_text)
        if hand is None:
            return []

        # Parse with Bovada parser
        self.parser.readHandInfo(hand)
        self.parser.readPlayerStacks(hand)
        if hand.gametype["base"] != "stud":
            self.parser.readBlinds(hand)
        self.parser.compilePlayerRegexs(hand)
        self.parser.markStreets(hand)

        # Read actions for each street
        for street in hand.actionStreets:
            if hand.streets.get(street):
                self.parser.readAction(hand, street)

        self.parser.readCollectPot(hand)
        self.parser.readOther(hand)

        # Validate and return errors
        if validation_errors := self.validate_hand_data(hand, filename):
            return [f"{filename.name} hand {hand_index+1}: {', '.join(validation_errors)}"]
        return []

    def _process_file_hands(self, file_path: Path, failed_files: list[str]) -> None:
        """Process all hands in a single file."""
        filename = file_path.name
        try:
            content = self.read_hand_file(str(file_path))
            self.parser.in_path = str(file_path)

            hands = content.split("\n\n\n")
            for i, hand_text in enumerate(hands):
                if not hand_text.strip():
                    continue

                try:
                    errors = self._parse_single_hand(hand_text, i, file_path)
                    failed_files.extend(errors)
                except (FpdbParseError, FpdbHandPartial):
                    # These exceptions are expected for certain files
                    pass
                except (ValueError, KeyError, AttributeError) as e:
                    failed_files.append(f"{filename} hand {i+1}: Parsing error - {e}")

        except (OSError, UnicodeDecodeError) as e:
            failed_files.append(f"{filename}: Read error - {e}")

    def test_parse_all_cash_games(self) -> None:
        """Test all cash game files."""
        cash_files = [f for f in self.bovada_files if "/cash/" in str(f)]
        failed_files = []

        for file_path in cash_files:
            with self.subTest(file=file_path.name):
                self._process_file_hands(file_path, failed_files)

        if failed_files:
            self.fail(f"Parsing failures in {len(failed_files)} cases:\n" + "\n".join(failed_files[:10]))

    def _validate_tournament_hand(self, hand: Hand, file_path: Path) -> list[str]:
        """Validate tournament-specific hand data."""
        validation_errors = self.validate_hand_data(hand, file_path)
        if hand.gametype.get("type") == "tour":
            if not hand.tourNo:
                validation_errors.append("missing tourNo")
            if not hand.tablename:
                validation_errors.append("missing tablename")
        return validation_errors

    def _parse_tournament_hand(self, hand_text: str, hand_index: int, file_path: Path) -> list[str]:
        """Parse a single tournament hand and return validation errors."""
        try:
            gametype = self.parser.determineGameType(hand_text.split("\n\n")[0])
            hand = self._create_hand_object(gametype, hand_text)
            if hand is None:
                return []

            # Parse hand data
            self.parser.readHandInfo(hand)
            self.parser.readPlayerStacks(hand)
            if hand.gametype["base"] != "stud":
                self.parser.readBlinds(hand)
            self.parser.compilePlayerRegexs(hand)
            self.parser.markStreets(hand)

            # Read actions for each street
            for street in hand.actionStreets:
                if hand.streets.get(street):
                    self.parser.readAction(hand, street)

            self.parser.readCollectPot(hand)
            self.parser.readOther(hand)

            # Validate tournament-specific data
            if validation_errors := self._validate_tournament_hand(hand, file_path):
                filename = file_path.name
                return [f"{filename} hand {hand_index+1}: {', '.join(validation_errors)}"]
        except (FpdbParseError, FpdbHandPartial):
            # These exceptions are expected for some files
            pass
        except (ValueError, KeyError, AttributeError) as e:
            filename = file_path.name
            return [f"{filename} hand {hand_index+1}: Parsing error - {e}"]
        return []

    def test_parse_all_tournaments(self) -> None:
        """Test all tournament files."""
        tour_files = [f for f in self.bovada_files if "/tour/" in str(f)]
        failed_files = []

        for file_path in tour_files:
            with self.subTest(file=file_path.name):
                try:
                    content = self.read_hand_file(str(file_path))
                    self.parser.in_path = str(file_path)

                    hands = content.split("\n\n\n")
                    for i, hand_text in enumerate(hands):
                        if hand_text.strip():
                            errors = self._parse_tournament_hand(hand_text, i, file_path)
                            failed_files.extend(errors)

                except (OSError, UnicodeDecodeError) as e:
                    failed_files.append(f"{file_path.name}: Read error - {e}")

        if failed_files:
            self.fail(f"Parsing failures in {len(failed_files)} cases:\n" + "\n".join(failed_files[:10]))

    def test_specific_edge_cases(self) -> None:
        """Test specific problematic edge cases identified."""
        edge_case_files = [
            "NLHE-USD-5-10-201511.concatenated.partial.txt",  # Partial hands
            "PLO8-9max-USD-0.02-0.05-201408.corrupted.lines.txt",  # Corrupted
            "NLHE-USD - $0.25-$0.50 - 202103.MVS.version.txt",  # MVS version
            "NLHE-USD - $0.05-$0.10 - 201308.ZonePoker.txt",  # Zone Poker
        ]

        for filename in edge_case_files:
            matching_files = [f for f in self.bovada_files if filename in str(f)]
            if not matching_files:
                self.skipTest(f"File {filename} not found")
                continue

            file_path = matching_files[0]
            with self.subTest(file=filename):
                self._test_edge_case_file(file_path, filename)

    def _test_edge_case_file(self, file_path: Path, filename: str) -> None:
        """Test a single edge case file."""
        content = self.read_hand_file(str(file_path))
        self.parser.in_path = str(file_path)

        try:
            hands = content.split("\n\n\n")
            sum(self._parse_edge_case_hand(hand_text) for hand_text in hands if hand_text.strip())
        except (FpdbParseError, FpdbHandPartial, ValueError, IndexError) as e:
            if "corrupted" not in filename and "partial" not in filename:
                self.fail(f"Unexpected error for {filename}: {e}")

    def _parse_edge_case_hand(self, hand_text: str) -> int:
        """Parse a single hand text for edge cases and return 1 if successful, 0 otherwise."""
        with contextlib.suppress(FpdbParseError, FpdbHandPartial):
            gametype = self.parser.determineGameType(hand_text.split("\n\n")[0])

            if gametype["base"] == "hold":
                hand = HoldemOmahaHand(self.config, self.parser, "Bovada", gametype, hand_text)
            elif gametype["base"] == "stud":
                hand = StudHand(self.config, self.parser, "Bovada", gametype, hand_text)
            elif gametype["base"] == "draw":
                hand = DrawHand(self.config, self.parser, "Bovada", gametype, hand_text)
            else:
                return 0

            self.parser.readHandInfo(hand)
            return 1
        return 0

    def test_data_consistency(self) -> None:
        """Test the consistency of extracted data."""
        test_file = next(
            (f for f in self.bovada_files
                if "NLHE-6max-USD - $0.25-$0.50 - 201804.bodog.eu.txt" in str(f)),
            None,
        )

        if not test_file:
            self.skipTest("Specific test file not found")

        content = self.read_hand_file(str(test_file))
        self.parser.in_path = str(test_file)

        # Take only the first hand from the file
        hands = content.split("\n\n\n")
        first_hand_text = hands[0] if hands else content
        gametype = self.parser.determineGameType(first_hand_text.split("\n\n")[0])

        # Use MockHand to allow explicit parsing
        hand = MockHand(first_hand_text, gametype)

        # Parse completely with explicit methods
        self.parser.readHandInfo(hand)
        self.parser.readPlayerStacks(hand)
        self.parser.readBlinds(hand)
        self.parser.compilePlayerRegexs(hand)
        self.parser.markStreets(hand)

        for street in hand.actionStreets:
            if hand.streets.get(street):
                self.parser.readAction(hand, street)

        self.parser.readCollectPot(hand)
        self.parser.readOther(hand)

        # Consistency checks
        assert hand.handid == "3598529418"
        assert len(hand.players) == 6
        assert hand.gametype["limitType"] == "nl"
        assert hand.gametype["base"] == "hold"

        # Check actions
        preflop_actions = [a for a in hand.actions if a[0] == "PREFLOP"]
        assert preflop_actions

        # Check that we have the expected raise
        raise_actions = [a for a in hand.actions if a[2] == "raise"]
        assert raise_actions



if __name__ == "__main__":
    unittest.main(verbosity=2)
