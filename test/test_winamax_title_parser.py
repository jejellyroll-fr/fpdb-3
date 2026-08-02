from __future__ import annotations

import unittest

from fpdb.infrastructure.platform.winamax_title_parser import (
    WinamaxTableType,
    WinamaxTitleParser,
    is_winamax_window,
    parse_winamax_title,
)


class TestWinamaxTitleParser(unittest.TestCase):
    def test_is_winamax_window(self) -> None:
        assert is_winamax_window("Winamax Poker - CashGame - Table1 - 0.01€/0.02€")
        assert is_winamax_window("WINAMAX Expresso 5€")
        assert is_winamax_window("Winamax TableName")
        assert not is_winamax_window("PokerStars - Table 1")
        assert not is_winamax_window("")
        assert not is_winamax_window(None)

    def test_parse_cash_game(self) -> None:
        title = "Winamax Poker - CashGame - Seattle 01 - 0.01€/0.02€ - EUR"
        info = parse_winamax_title(title)
        assert info is not None
        assert info.table_name == "Seattle 01"
        assert info.table_type == WinamaxTableType.CASH_GAME
        assert info.blinds == "0.01€/0.02€"
        assert info.currency == "EUR"
        assert info.display_name == "Seattle 01"
        assert not info.is_fast_fold

        # Variant NL Hold'em
        title_nl = "Winamax Poker - NL Hold'em - Paris 02 - 0.05 € / 0.10 €"
        info_nl = parse_winamax_title(title_nl)
        assert info_nl is not None
        assert info_nl.table_name == "Paris 02"
        assert info_nl.table_type == WinamaxTableType.CASH_GAME
        assert info_nl.blinds == "0.05€/0.10€"

    def test_parse_go_fast_and_holdup(self) -> None:
        # Go Fast
        title = 'Winamax Poker - Go Fast "SpeedPool" - 0.05€/0.10€'
        info = parse_winamax_title(title)
        assert info is not None
        assert info.table_name == "SpeedPool"
        assert info.table_type == WinamaxTableType.GO_FAST
        assert info.is_fast_fold
        assert info.blinds == "0.05€/0.10€"

        # HOLD-UP
        title_hu = 'Winamax Poker - HOLD-UP "ActionPool" - 0.10€/0.20€'
        info_hu = parse_winamax_title(title_hu)
        assert info_hu is not None
        assert info_hu.table_name == "ActionPool"
        assert info_hu.table_type == WinamaxTableType.GO_FAST
        assert info_hu.is_fast_fold

    def test_parse_tournament(self) -> None:
        title = 'Winamax Poker - Tournament(123456789) "Main Event" - Table 5'
        info = parse_winamax_title(title)
        assert info is not None
        assert info.table_name == "Main Event"
        assert info.tournament_name == "Main Event"
        assert info.table_type == WinamaxTableType.TOURNAMENT
        assert info.table_number == 5
        assert info.display_name == "Main Event - Table 5"

    def test_parse_expresso(self) -> None:
        title = "Winamax Poker - Expresso 5€ - 987654321"
        info = parse_winamax_title(title)
        assert info is not None
        assert info.table_name == "Expresso 5€"
        assert info.table_type == WinamaxTableType.EXPRESSO
        assert info.buyin == "5€"
        assert info.table_number == 987654321
        assert not info.is_fast_fold

    def test_parse_sit_and_go(self) -> None:
        title = 'Winamax Poker - Sit&Go "SNG Turbo" - Table 2'
        info = parse_winamax_title(title)
        assert info is not None
        assert info.table_name == "SNG Turbo"
        assert info.table_type == WinamaxTableType.SIT_AND_GO
        assert info.table_number == 2

    def test_parse_linux_cash_and_fallbacks(self) -> None:
        # Linux cash
        title_linux = "Winamax Aalen 14"
        info_linux = parse_winamax_title(title_linux)
        assert info_linux is not None
        assert info_linux.table_name == "Aalen 14"
        assert info_linux.table_type == WinamaxTableType.CASH_GAME

        # Generic fallback
        title_gen = "Winamax Poker - Something Else"
        info_gen = parse_winamax_title(title_gen)
        assert info_gen is not None
        assert info_gen.table_name == "Something Else"
        assert info_gen.table_type == WinamaxTableType.UNKNOWN

        # Linux generic fallback
        title_lgen = "Winamax Custom Window Title"
        info_lgen = parse_winamax_title(title_lgen)
        assert info_lgen is not None
        assert info_lgen.table_name == "Custom Window Title"
        assert info_lgen.table_type == WinamaxTableType.UNKNOWN

        # Non winamax or empty
        assert parse_winamax_title("888poker - Table 1") is None
        assert parse_winamax_title("") is None

    def test_parse_none_when_winamax_matches_no_pattern(self) -> None:
        # Contains "winamax" so it passes is_winamax_window, but matches none
        # of the structured patterns nor the fallbacks (no "Poker -", and
        # "winamaxx" has no separator for the linux fallbacks).
        assert parse_winamax_title("winamaxx") is None
        assert parse_winamax_title("winamax") is None

    def test_matches_hand_history(self) -> None:
        # Cash Game match
        info_cash = parse_winamax_title("Winamax Poker - CashGame - Seattle 01 - 0.01€/0.02€")
        assert info_cash is not None
        assert WinamaxTitleParser.matches_hand_history(info_cash, "Seattle 01")
        assert WinamaxTitleParser.matches_hand_history(info_cash, "seattle 01")
        assert not WinamaxTitleParser.matches_hand_history(info_cash, "Chicago 02")

        # Tournament match
        info_tourney = parse_winamax_title('Winamax Poker - Tournament "Main Event" - Table 5')
        assert info_tourney is not None
        assert WinamaxTitleParser.matches_hand_history(info_tourney, "Main Event #5")
        assert WinamaxTitleParser.matches_hand_history(info_tourney, "main event table 5")

        # Expresso match
        info_expresso = parse_winamax_title("Winamax Poker - Expresso 5€ - 12345678")
        assert info_expresso is not None
        assert WinamaxTitleParser.matches_hand_history(info_expresso, "Expresso(12345678)")

        # None checks
        assert not WinamaxTitleParser.matches_hand_history(None, "Table")
        assert not WinamaxTitleParser.matches_hand_history(info_cash, "")

    def test_matches_hand_history_partial_name(self) -> None:
        info_cash = parse_winamax_title("Winamax Poker - CashGame - Seattle 01 - 0.01€/0.02€")
        assert info_cash is not None
        # Partial containment either direction counts.
        assert WinamaxTitleParser.matches_hand_history(info_cash, "Seattle")
        assert WinamaxTitleParser.matches_hand_history(info_cash, "Seattle 01 Cash Game")

    def test_matches_hand_history_tournament_table_number(self) -> None:
        # Name differs but the table number in the HH name resolves it.
        info_tourney = parse_winamax_title('Winamax Poker - Tournament "Main Event" - Table 5')
        assert info_tourney is not None
        assert WinamaxTitleParser.matches_hand_history(info_tourney, "SomeTourney table 5")
        assert WinamaxTitleParser.matches_hand_history(info_tourney, "SomeTourney table5")
        assert not WinamaxTitleParser.matches_hand_history(info_tourney, "SomeTourney table 6")

    def test_matches_hand_history_expresso_by_id(self) -> None:
        info_expresso = parse_winamax_title("Winamax Poker - Expresso 5€ - 12345678")
        assert info_expresso is not None
        assert WinamaxTitleParser.matches_hand_history(info_expresso, "Expresso(12345678)")
        assert not WinamaxTitleParser.matches_hand_history(info_expresso, "Expresso(99999999)")

    def test_matches_hand_history_normalizes_punctuation(self) -> None:
        info_cash = parse_winamax_title("Winamax Poker - CashGame - Seattle 01 - 0.01€/0.02€")
        assert info_cash is not None
        assert WinamaxTitleParser.matches_hand_history(info_cash, "Seattle 01!!!")

    def test_helpers(self) -> None:
        assert WinamaxTitleParser._normalize_blinds(" 0.01 € / 0.02 € ") == "0.01€/0.02€"
        assert WinamaxTitleParser._normalize_blinds(None) is None
        assert WinamaxTitleParser._normalize_name("  Seattle #01 ! ") == "seattle 01 "

    def test_create_info_defensive_fallback(self) -> None:
        # Unknown table types fall through to a minimal UNKNOWN info.
        match = WinamaxTitleParser.PATTERNS["generic"].search("Winamax Poker - Whatever")
        assert match is not None
        info = WinamaxTitleParser._create_info("made_up", match, "Winamax Poker - Whatever")
        assert info.table_name == "Unknown"
        assert info.table_type == WinamaxTableType.UNKNOWN
        assert WinamaxTitleParser._normalize_name("") == ""
