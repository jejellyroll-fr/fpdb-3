from Card import StartCardRank, cardFromValueSuit, decodeStartHandValue, encodeCard, twoStartCards, valueSuitFromCard


def test_twoStartCards() -> None:
    # Test pair
    result = twoStartCards(4, "d", 4, "c")
    assert result == 29

    # Test suited
    result = twoStartCards(10, "h", 12, "h")
    assert result == 139

    # Test unsuited
    result = twoStartCards(6, "s", 9, "c")
    assert result == 60

    # Test invalid cards
    result = twoStartCards(1, "d", 15, "h")
    assert result == 170

    # Test invalid value
    result = twoStartCards(5, "d", 18, "s")
    assert result == 170


def test_decodeStartHandValue() -> None:
    # Test holdem game
    assert decodeStartHandValue("holdem", 169) == "AA"
    assert decodeStartHandValue("6_holdem", 166) == "AJs"

    # Test razz game
    assert decodeStartHandValue("razz", 260) == "(T2)3"
    assert decodeStartHandValue("27_razz", 200) == "(9A)6"

    # Test unknown game
    assert decodeStartHandValue("unknown_game", 123) == "xx"


def test_StartCardRank() -> None:
    # Tests that the function returns the correct tuple for idx = 0
    assert StartCardRank(0) == ("22", 54, 12)

    # Tests that the function returns the correct tuple for idx = 5
    assert StartCardRank(5) == ("72o", 169, 24)

    # Tests that the function returns the correct tuple for idx = 14
    assert StartCardRank(13) == ("32s", 111, 8)

    # Tests that the function returns the correct tuple for idx = 15
    assert StartCardRank(14) == ("33", 53, 12)

    # Tests that the function handles out of range indices
    try:
        result = StartCardRank(171)
        # If it doesn't raise an exception, it should return a safe value
        assert isinstance(result, tuple)
    except IndexError:
        # This is expected for out of range indices
        pass


def test_encodeCard() -> None:
    """Test card encoding functionality."""
    # Test hearts
    assert encodeCard("2h") == 1
    assert encodeCard("Ah") == 13

    # Test diamonds
    assert encodeCard("2d") == 14
    assert encodeCard("Ad") == 26

    # Test clubs
    assert encodeCard("2c") == 27
    assert encodeCard("Ac") == 39

    # Test spades
    assert encodeCard("2s") == 40
    assert encodeCard("As") == 52

    # Test invalid
    assert encodeCard("Xx") == 0
    assert encodeCard("  ") == 0


def test_valueSuitFromCard() -> None:
    """Test card decoding functionality."""
    # Test valid cards
    assert valueSuitFromCard(1) == "2h"
    assert valueSuitFromCard(13) == "Ah"
    assert valueSuitFromCard(26) == "Ad"
    assert valueSuitFromCard(52) == "As"

    # Test invalid cards
    assert valueSuitFromCard(0) == ""
    assert valueSuitFromCard(-1) == ""
    assert valueSuitFromCard(53) == ""


def test_cardFromValueSuit() -> None:
    """Test card creation from value and suit."""
    # Test all suits
    assert cardFromValueSuit(2, "h") == 1
    assert cardFromValueSuit(2, "d") == 14
    assert cardFromValueSuit(2, "c") == 27
    assert cardFromValueSuit(2, "s") == 40

    # Test invalid suit
    assert cardFromValueSuit(10, "x") == 0
