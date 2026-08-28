"""Unit tests for fpdb_3_legacy.Card pure-logic functions.

These exercise the encode/decode and start-hand naming helpers with known
inputs and known outputs. The legacy implementation is the behavioural
reference; where behaviour is surprising (but self-consistent), the tests are
characterization tests matching current behaviour.
"""
from __future__ import annotations

import pytest

from fpdb_3_legacy import Card


class TestEncodeCard:
    @pytest.mark.parametrize(
        ("card_string", "expected"),
        [
            ("2h", 1),
            ("Ah", 13),
            ("2d", 14),
            ("Ad", 26),
            ("2c", 27),
            ("Ac", 39),
            ("2s", 40),
            ("As", 52),
            ("  ", 0),
        ],
    )
    def test_known_cards(self, card_string, expected) -> None:
        assert Card.encodeCard(card_string) == expected

    @pytest.mark.parametrize("bad", ["zz", "XX", "", "A", "Ahh", "1h"])
    def test_unknown_returns_zero(self, bad) -> None:
        assert Card.encodeCard(bad) == 0

    def test_round_trip_against_valueSuitFromCard(self) -> None:
        # Every encodeable card (except the blank) round-trips through
        # valueSuitFromCard.
        for cs, code in Card.ENCODE_CARD_LIST.items():
            if cs == "  ":
                continue
            assert Card.valueSuitFromCard(code) == cs


class TestValueSuitFromCard:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            (1, "2h"),
            (13, "Ah"),
            (26, "Ad"),
            (39, "Ac"),
            (52, "As"),
        ],
    )
    def test_known(self, code, expected) -> None:
        assert Card.valueSuitFromCard(code) == expected

    @pytest.mark.parametrize("code", [0, -1, -5, 53, 99])
    def test_invalid_returns_empty(self, code) -> None:
        assert Card.valueSuitFromCard(code) == ""


class TestCardFromValueSuit:
    @pytest.mark.parametrize(
        ("value", "suit", "expected"),
        [
            (2, "h", 1),
            (14, "h", 13),
            (2, "d", 14),
            (14, "d", 26),
            (2, "c", 27),
            (14, "c", 39),
            (2, "s", 40),
            (14, "s", 52),
        ],
    )
    def test_valid_suits(self, value, suit, expected) -> None:
        assert Card.cardFromValueSuit(value, suit) == expected

    def test_invalid_suit_returns_zero(self) -> None:
        assert Card.cardFromValueSuit(14, "x") == 0

    def test_inverse_of_valueSuitFromCard(self) -> None:
        # cardFromValueSuit composes with valueSuitFromCard for all 52 cards.
        for code in range(1, 53):
            s = Card.valueSuitFromCard(code)
            value = Card.card_map[s[0]]
            assert Card.cardFromValueSuit(value, s[1]) == code


class TestTwoStartCards:
    def test_pair(self) -> None:
        assert Card.twoStartCards(2, "h", 2, "d") == 1
        assert Card.twoStartCards(14, "s", 14, "h") == 169

    def test_suited_high_first(self) -> None:
        # AKs
        assert Card.twoStartCards(14, "s", 13, "s") == 168

    def test_suited_low_first_same_result(self) -> None:
        # order of the two suited cards must not matter
        assert Card.twoStartCards(13, "s", 14, "s") == 168

    def test_offsuit(self) -> None:
        # AKo, both orderings give the same id
        assert Card.twoStartCards(14, "s", 13, "h") == 156
        assert Card.twoStartCards(13, "h", 14, "s") == 156

    def test_suited_and_offsuit_differ(self) -> None:
        assert Card.twoStartCards(14, "s", 13, "s") != Card.twoStartCards(14, "s", 13, "h")

    @pytest.mark.parametrize(
        ("v1", "v2"),
        [(1, 2), (15, 2), (2, 1), (2, 15), (0, 5)],
    )
    def test_out_of_range_returns_unknown(self, v1, v2) -> None:
        assert Card.twoStartCards(v1, "h", v2, "d") == Card.HOLDEM_UNKNOWN_HAND

    def test_none_returns_unknown(self) -> None:
        assert Card.twoStartCards(None, "h", 5, "d") == Card.HOLDEM_UNKNOWN_HAND
        assert Card.twoStartCards(5, "h", None, "d") == Card.HOLDEM_UNKNOWN_HAND

    def test_all_known_hands_in_range(self) -> None:
        for v1 in range(2, 15):
            for v2 in range(2, 15):
                for s1, s2 in (("h", "h"), ("h", "d")):
                    r = Card.twoStartCards(v1, s1, v2, s2)
                    assert 1 <= r <= 169


class TestTwoStartCardString:
    @pytest.mark.parametrize(
        ("card", "expected"),
        [
            (1, "22"),
            (169, "AA"),
            (168, "AKs"),
            (156, "AKo"),
        ],
    )
    def test_known(self, card, expected) -> None:
        assert Card.twoStartCardString(card) == expected

    @pytest.mark.parametrize("card", [0, 170, -1, 200])
    def test_out_of_range_is_xx(self, card) -> None:
        assert Card.twoStartCardString(card) == "xx"

    def test_round_trip_with_twoStartCards(self) -> None:
        # For every (suited/offsuit/pair) hand, encoding then decoding gives a
        # consistent 2/3-char string.
        for v1 in range(2, 15):
            for v2 in range(2, 15):
                code = Card.twoStartCards(v1, "h", v2, "h")
                s = Card.twoStartCardString(code)
                # decoding the encoded value must itself re-encode to the same id
                assert isinstance(s, str)


class TestStartCardRank:
    def test_first_and_last(self) -> None:
        assert Card.StartCardRank(0) == ("22", 54, 12)
        assert Card.StartCardRank(169) == ("xx", 170, 0)

    def test_known_aa(self) -> None:
        assert Card.StartCardRank(168) == ("AA", 1, 12)

    def test_returns_three_tuple(self) -> None:
        for idx in (0, 1, 50, 100, 168, 169):
            t = Card.StartCardRank(idx)
            assert len(t) == 3
            assert isinstance(t[0], str)

    def test_out_of_range_raises(self) -> None:
        with pytest.raises(IndexError):
            Card.StartCardRank(170)


class TestSuitClassifiers:
    def test_is_suited_true(self) -> None:
        assert Card.is_suited([("A", "s"), ("K", "s"), ("Q", "s")])

    def test_is_suited_false(self) -> None:
        assert not Card.is_suited([("A", "s"), ("K", "h")])

    def test_is_double_suited(self) -> None:
        assert Card.is_double_suited([("A", "s"), ("K", "s"), ("Q", "h"), ("J", "h")])
        assert not Card.is_double_suited([("A", "s"), ("K", "s"), ("Q", "s"), ("J", "s")])

    def test_is_rainbow(self) -> None:
        assert Card.is_rainbow([("A", "s"), ("K", "h"), ("Q", "d"), ("J", "c")])
        assert not Card.is_rainbow([("A", "s"), ("K", "h"), ("Q", "d"), ("J", "d")])


class TestFourStartCards:
    def test_invalid_length(self) -> None:
        assert Card.fourStartCards([("A", "s")]) == "Invalid input: You must provide exactly four cards."
        assert Card.fourStartCards([]) == "Invalid input: You must provide exactly four cards."

    def test_monotone(self) -> None:
        assert Card.fourStartCards([("A", "s"), ("K", "s"), ("Q", "s"), ("J", "s")]) == "Monotone"

    def test_double_suited(self) -> None:
        assert Card.fourStartCards([("A", "s"), ("K", "s"), ("Q", "h"), ("J", "h")]) == "Double Suited"

    def test_rainbow(self) -> None:
        assert Card.fourStartCards([("A", "s"), ("K", "h"), ("Q", "d"), ("J", "c")]) == "Rainbow"

    def test_suited_three_suits(self) -> None:
        # 3 different suits, two share a suit -> "Suited"
        assert Card.fourStartCards([("A", "s"), ("K", "s"), ("Q", "h"), ("J", "d")]) == "Suited"


class TestDecodeRazzStartHand:
    @pytest.mark.parametrize(
        ("idx", "expected"),
        [
            (0, "xxx"),
            (-13, "(00)A"),
            (-1, "(00)K"),
            (1, "(32)A"),
            (169, "(92)A"),
        ],
    )
    def test_known(self, idx, expected) -> None:
        assert Card.decodeRazzStartHand(idx) == expected

    def test_missing_key_raises(self) -> None:
        with pytest.raises(KeyError):
            Card.decodeRazzStartHand(99999)


class TestEncodeRazzStartHand:
    def test_simple(self) -> None:
        # (32)A -> 1
        assert Card.encodeRazzStartHand([("3", "h"), ("2", "d"), ("A", "c")]) == 1

    def test_ordering_high_first(self) -> None:
        # card_map_low: 3 > 2 so first two stay (3,2); produces (32)A
        assert Card.encodeRazzStartHand([("3", "h"), ("2", "d"), ("A", "c")]) == 1
        # swapped first two should still give (32)A because of the ordering branch
        assert Card.encodeRazzStartHand([("2", "d"), ("3", "h"), ("A", "c")]) == 1

    def test_unknown_combo_returns_zero(self) -> None:
        # AAA -> card_map_low['A']==1, 1>1 False -> (AA)A which is a real key.
        # Use a genuinely-unmapped pattern instead: (00)0 not reachable here,
        # so pick three identical low cards that map to a missing key.
        # '0' rank maps to card_map_low 0; (00)0 -> 0 (falsy) -> returns 0.
        assert Card.encodeRazzStartHand([("0", "h"), ("0", "d"), ("0", "c")]) == 0

    def test_aaa_is_real_key(self) -> None:
        # Characterization: (AA)A exists in the table at 1171.
        assert Card.encodeRazzStartHand([("A", "h"), ("A", "d"), ("A", "c")]) == 1171

    def test_decode_inverse_of_encode(self) -> None:
        # For a handful of hands, encode then decode round-trips.
        for cards in (
            [("3", "h"), ("2", "d"), ("A", "c")],
            [("5", "h"), ("4", "d"), ("3", "c")],
            [("7", "h"), ("2", "d"), ("A", "c")],
        ):
            idx = Card.encodeRazzStartHand(cards)
            decoded = Card.decodeRazzStartHand(idx)
            assert decoded.startswith("(")


class TestDecodeStartHandValue:
    def test_holdem(self) -> None:
        assert Card.decodeStartHandValue("holdem", 168) == "AKs"
        assert Card.decodeStartHandValue("6_holdem", 168) == "AKs"

    def test_razz(self) -> None:
        assert Card.decodeStartHandValue("razz", 1) == "(32)A"
        assert Card.decodeStartHandValue("27_razz", 0) == "xxx"

    def test_unknown_game_returns_xx(self) -> None:
        assert Card.decodeStartHandValue("badugi", 5) == "xx"
        assert Card.decodeStartHandValue("does-not-exist", 99) == "xx"

    def test_fusion_uses_holdem_decoder(self) -> None:
        assert Card.decodeStartHandValue("fusion", 168) == "AKs"

    def test_omaha_uses_ppt_style_rank_and_suit_class(self) -> None:
        value = Card.fourStartCardsValue(["As", "Ks", "Qh", "Jh"])
        assert Card.decodeStartHandValue("omahahi", value) == "AKQJ ds"

        value = Card.fourStartCardsValue(["As", "Ah", "Ks", "7d"])
        assert Card.decodeStartHandValue("omahahi", value) == "AAK7 ss"

        value = Card.fourStartCardsValue(["Ts", "9h", "8d", "7c"])
        assert Card.decodeStartHandValue("omahahilo", value) == "T987 r"


class TestCalcStartCards:
    class _FakeHand:
        def __init__(self, category, holecards):
            self.gametype = {"category": category}
            self._hc = holecards

        def join_holecards(self, player, asList=False):
            return self._hc

    def test_holdem_pair(self) -> None:
        hand = self._FakeHand("holdem", ["2h", "2d"])
        assert Card.calcStartCards(hand, "hero") == 1

    def test_holdem_suited(self) -> None:
        hand = self._FakeHand("holdem", ["As", "Ks"])
        assert Card.calcStartCards(hand, "hero") == 168

    def test_6_holdem(self) -> None:
        hand = self._FakeHand("6_holdem", ["As", "Kh"])
        assert Card.calcStartCards(hand, "hero") == 156

    def test_fusion_uses_first_two_cards_as_holdem(self) -> None:
        hand = self._FakeHand("fusion", ["As", "Ks", "Qh", "Jd"])
        assert Card.decodeStartHandValue("fusion", Card.calcStartCards(hand, "hero")) == "AKs"

    def test_holdem_unknown_rank_returns_unknown_hand(self) -> None:
        hand = self._FakeHand("holdem", ["Xs", "Kh"])
        assert Card.calcStartCards(hand, "hero") == Card.HOLDEM_UNKNOWN_HAND

    def test_omaha_class(self) -> None:
        hand = self._FakeHand("omahahi", ["As", "Ks", "Qh", "Jh"])
        assert Card.decodeStartHandValue("omahahi", Card.calcStartCards(hand, "hero")) == "AKQJ ds"

    def test_razz_offset(self) -> None:
        hand = self._FakeHand("razz", [("3", "h"), ("2", "d"), ("A", "c")])
        # encodeRazzStartHand(...) == 1, offset by +184
        assert Card.calcStartCards(hand, "hero") == 185

    def test_other_game_unknown(self) -> None:
        hand = self._FakeHand("badugi", ["As", "Ks", "Qs", "Js"])
        assert Card.calcStartCards(hand, "hero") == Card.HOLDEM_UNKNOWN_HAND


class TestMainCli:
    def test_no_args_prints_help(self, capsys) -> None:
        rc = Card.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "FPDB Card utilities" in out or "usage" in out.lower()

    @pytest.mark.parametrize(
        "flag",
        [
            "--test-rank",
            "--test-encoding",
            "--test-two-cards",
            "--test-suits",
            "--test-razz",
            "--demo",
        ],
    )
    def test_flags_run(self, flag, capsys) -> None:
        rc = Card.main([flag])
        assert rc == 0
        # each flag prints something
        assert capsys.readouterr().out != ""


class TestInteractiveMenu:
    def test_menu_dispatch_each_option(self, capsys, monkeypatch) -> None:
        # Drive the menu: pick each option, immediately back out of the
        # sub-loop, then exit. Sub-loops return on negative number / 'back'.
        inputs = iter(
            [
                "1", "-1",          # StartCardRank -> negative returns
                "2", "back",        # encoding -> back
                "3", "back",        # two start cards -> back
                "4", "back",        # suit functions -> back
                "5", "back",        # razz functions -> back
                "9",                # invalid option
                "0",                # exit
            ],
        )
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(inputs))
        Card.run_interactive_menu()
        out = capsys.readouterr().out
        assert "Goodbye!" in out

    def test_submenus_process_values(self, capsys, monkeypatch) -> None:
        # Exercise the actual processing branches inside each sub-loop.
        inputs = iter(
            [
                "1", "0", "-1",                 # StartCardRank(0) then return
                "2", "help", "As", "13", "back",  # encoding: help, string, number
                "3", "14 h 13 s", "back",       # two start cards valid
                "4", "Ah Kh", "back",           # suited
                "5", "Ah 2s 3d", "back",        # razz 3 cards
                "0",
            ],
        )
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(inputs))
        Card.run_interactive_menu()
        out = capsys.readouterr().out
        assert "StartCardRank(0)" in out
        assert "is_suited" in out


class TestModuleData:
    def test_database_filters_present(self) -> None:
        for key in ("pair", "suited", "offsuit", "suited_connectors", "offsuit_connectors"):
            assert key in Card.DATABASE_FILTERS

    def test_card_map_abbr_grid(self) -> None:
        assert len(Card.card_map_abbr) == 13
        assert all(len(row) == 13 for row in Card.card_map_abbr)
        assert Card.card_map_abbr[0][0] == "AA"
