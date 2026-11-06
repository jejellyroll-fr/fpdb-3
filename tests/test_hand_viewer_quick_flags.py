"""The Hand Viewer's All-in and Showdown check boxes narrow the hands (#656).

Two cash hands are imported: in the first the hero shoves and is called to a
showdown; in the second the villain shoves and the hero folds. The flags read
the selected player's row, so the second hand is not an all-in hand for Hero.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.GuiHandViewer import QUICK_FLAG_CONDITIONS, GuiHandViewer

HERO_SHOVES_TO_SHOWDOWN = """PokerStars Hand #262100000001:  Hold'em No Limit (€0.01/€0.02 EUR) - 2026/06/07 18:00:00 CET
Table 'Flags' 6-max Seat #1 is the button
Seat 1: Hero (€2.00 in chips)
Seat 2: Villain (€2.00 in chips)
Hero: posts small blind €0.01
Villain: posts big blind €0.02
*** HOLE CARDS ***
Dealt to Hero [As Ad]
Hero: raises €1.98 to €2.00 and is all-in
Villain: calls €1.98 and is all-in
*** FLOP *** [2c 7d 9h]
*** TURN *** [2c 7d 9h] [Jc]
*** RIVER *** [2c 7d 9h Jc] [3s]
*** SHOW DOWN ***
Hero: shows [As Ad] (a pair of Aces)
Villain: shows [Kc Kd] (a pair of Kings)
Hero collected €3.90 from pot
*** SUMMARY ***
Total pot €4 | Rake €0.10
Board [2c 7d 9h Jc 3s]
Seat 1: Hero (button) (small blind) showed [As Ad] and won (€3.90) with a pair of Aces
Seat 2: Villain (big blind) showed [Kc Kd] and lost with a pair of Kings
"""

VILLAIN_SHOVES_HERO_FOLDS = """PokerStars Hand #262100000002:  Hold'em No Limit (€0.01/€0.02 EUR) - 2026/06/07 18:05:00 CET
Table 'Flags' 6-max Seat #2 is the button
Seat 1: Hero (€2.00 in chips)
Seat 2: Villain (€2.00 in chips)
Villain: posts small blind €0.01
Hero: posts big blind €0.02
*** HOLE CARDS ***
Dealt to Hero [7c 2d]
Villain: raises €1.98 to €2.00 and is all-in
Hero: folds
Uncalled bet (€1.98) returned to Villain
Villain collected €0.04 from pot
Villain: doesn't show hand
*** SUMMARY ***
Total pot €0.04 | Rake €0
Seat 1: Hero (big blind) folded before Flop
Seat 2: Villain (button) (small blind) collected (€0.04)
"""


class _Check:
    def __init__(self, checked: bool) -> None:
        self.checked = checked

    def isChecked(self) -> bool:
        return self.checked


@pytest.fixture
def two_cash_hands(tmp_path, fresh_db, legacy_config):
    from fpdb_3_legacy.Importer import Importer

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    for name, text in (("shove", HERO_SHOVES_TO_SHOWDOWN), ("fold", VILLAIN_SHOVES_HERO_FOLDS)):
        path = tmp_path / f"{name}.txt"
        path.write_text(text, encoding="utf-8")
        importer.addImportFile(str(path), "PokerStars")
        importer.runImport()
    yield fresh_db
    del importer  # kept alive until the test is done: dropping it closes the database


_PLAYER_TESTS = {
    "Hero": "AND hp.playerId IN (SELECT id FROM Players WHERE name = 'Hero')",
    "Villain": "AND hp.playerId IN (SELECT id FROM Players WHERE name = 'Villain')",
}


def _site_hand_numbers(db, *, player: str, **checked) -> list[str]:
    cursor = db.get_cursor()

    def other_filters(query):
        query = query.replace("<player_test>", _PLAYER_TESTS[player])
        for placeholder in ("<game_test>", "<limit_test>", "<position_test>"):
            query = query.replace(placeholder, "")
        return query

    viewer = SimpleNamespace(
        db=db,
        filters=SimpleNamespace(replace_placeholders_with_filter_values=other_filters),
        _splash_filter_condition=lambda: None,
        _analytics_filter_warning=lambda _filters: "",
        **{flag: _Check(checked.get(flag, False)) for flag, _condition in QUICK_FLAG_CONDITIONS},
    )
    hand_ids = GuiHandViewer.get_hand_ids_from_date_range(viewer, "2026-01-01 00:00:00", "2026-12-31 23:59:59")
    numbers = []
    for hand_id in hand_ids:
        cursor.execute("SELECT siteHandNo FROM Hands WHERE id = ?", (hand_id,))
        numbers.append(str(cursor.fetchone()[0]))
    return sorted(numbers)


def test_without_a_flag_both_hands_are_listed(two_cash_hands) -> None:
    assert _site_hand_numbers(two_cash_hands, player="Hero") == ["262100000001", "262100000002"]


def test_all_in_keeps_the_hands_the_selected_player_went_all_in(two_cash_hands) -> None:
    assert _site_hand_numbers(two_cash_hands, player="Hero", flagAllIn=True) == ["262100000001"]
    assert _site_hand_numbers(two_cash_hands, player="Villain", flagAllIn=True) == ["262100000001", "262100000002"]


def test_showdown_keeps_the_hands_the_selected_player_saw_showdown(two_cash_hands) -> None:
    assert _site_hand_numbers(two_cash_hands, player="Hero", flagShowdown=True) == ["262100000001"]
    assert _site_hand_numbers(two_cash_hands, player="Villain", flagShowdown=True) == ["262100000001"]


def test_flags_combine(two_cash_hands) -> None:
    assert _site_hand_numbers(two_cash_hands, player="Hero", flagAllIn=True, flagShowdown=True) == ["262100000001"]


def test_boolean_flags_are_not_compared_with_an_integer() -> None:
    """PostgreSQL rejects ``boolean = 1``; the live-database test runs these there."""
    conditions = dict(QUICK_FLAG_CONDITIONS)
    for flag, column in (("flagAllIn", "wentAllIn"), ("flagShowdown", "sawShowdown"), ("flagRunItTwice", "runItTwice")):
        assert column + " IS TRUE" in conditions[flag]
