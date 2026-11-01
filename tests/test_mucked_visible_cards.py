from fpdb_3_legacy.Mucked import valid_cards, visible_cards


def test_visible_cards_supports_show_one_and_fold() -> None:
    assert visible_cards((17, 0)) == [17]
    assert valid_cards((17, 0)) == 1


def test_visible_cards_ignores_unknown_gaps_without_dropping_later_cards() -> None:
    cards = (17, None, 0, 42)

    assert visible_cards(cards) == [17, 42]
    assert valid_cards(cards) == 2
