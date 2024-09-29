from Card import twoStartCards, decodeStartHandValue, StartCardRank


def test_twoStartCards():
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


def test_decodeStartHandValue():
    # Test holdem game
    assert decodeStartHandValue("holdem", 169) == "AA"
    assert decodeStartHandValue("6_holdem", 166) == "AJs"

    # Test razz game
    assert decodeStartHandValue("razz", 260) == "(T2)3"
    assert decodeStartHandValue("27_razz", 200) == "(9A)6"

    # Test unknown game
    assert decodeStartHandValue("unknown_game", 123) == "xx"


def test_StartCardRank():
    # Tests that the function returns the correct tuple for idx = 0
    def test_idx_0(self):
        assert StartCardRank(0) == ("22", 54, 12)

    # Tests that the function returns the correct tuple for idx = 5
    def test_idx_5(self):
        assert StartCardRank(5) == ("72o", 169, 24)

    # Tests that the function returns the correct tuple for idx = 14
    def test_idx_13(self):
        assert StartCardRank(13) == ("32s", 111, 8)

    # Tests that the function returns the correct tuple for idx = 15
    def test_idx_14(self):
        assert StartCardRank(14) == ("33", 53, 12)

    # Tests that the function returns the correct tuple for idx = 170
    def test_idx_169(self):
        assert StartCardRank(171) == ("xx", 170, 0)
