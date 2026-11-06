"""The payout dialog the replayer opens on a hand's tournament (#446)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from fpdb_3_legacy import tourney_payouts  # noqa: E402 - after the Qt availability probe
from fpdb_3_legacy.GuiReplayer import GuiReplayer  # noqa: E402
from fpdb_3_legacy.tourney_payouts_dialog import TourneyPayoutsDialog  # noqa: E402

INSERT_TYPE = (
    "INSERT INTO TourneyTypes (siteId, currency, buyIn, fee, category, limitType, knockout)"
    " VALUES (2, 'USD', 1000, 100, 'holdem', 'nl', 0)"
)
INSERT_TOURNEY = "INSERT INTO Tourneys (tourneyTypeId, siteTourneyNo, entries, prizepool) VALUES (?, 4242, 9, 8136)"


@pytest.fixture
def tourney(fresh_db) -> int:
    cursor = fresh_db.get_cursor()
    cursor.execute(INSERT_TYPE)
    cursor.execute(INSERT_TOURNEY, (cursor.lastrowid,))
    fresh_db.commit()
    return cursor.lastrowid


@pytest.fixture
def dialog(qtbot, fresh_db, tourney) -> TourneyPayoutsDialog:
    shown = TourneyPayoutsDialog(fresh_db, tourney)
    qtbot.addWidget(shown)
    return shown


@pytest.mark.qt
def test_a_tournament_without_a_structure_says_so(dialog) -> None:
    assert "#4242" in dialog.factsLabel.text() and "9" in dialog.factsLabel.text()
    assert dialog.currentLabel.text().startswith("No structure in use")
    assert not dialog.clearButton.isEnabled() and not dialog.changed


@pytest.mark.qt
def test_a_preset_is_applied_to_the_prize_pool_and_shown(dialog, fresh_db, tourney) -> None:
    dialog.presetCombo.setCurrentIndex(dialog.presetCombo.findData("sng_9max"))

    assert dialog.apply_preset()

    assert tourney_payouts.stored_payouts(fresh_db, tourney).amounts == (4068, 2441, 1627)
    assert dialog.currentLabel.text().startswith("In use") and "preset" in dialog.currentLabel.text()
    assert dialog.clearButton.isEnabled() and dialog.changed


@pytest.mark.qt
def test_pasted_payouts_are_saved_and_a_bad_paste_says_why(dialog, fresh_db, tourney) -> None:
    dialog.entry.setPlainText("60% 30%")
    assert not dialog.save_entry()
    assert "90" in dialog.errorLabel.text() and not dialog.changed
    assert tourney_payouts.stored_payouts(fresh_db, tourney) is None

    dialog.entry.setPlainText("1st  $45.00\n2nd  $27.00\n3rd  $18.00")
    assert dialog.save_entry()

    assert tourney_payouts.stored_payouts(fresh_db, tourney).amounts == (4500, 2700, 1800)
    assert dialog.errorLabel.text() == "" and dialog.entry.toPlainText() == "" and dialog.changed


@pytest.mark.qt
def test_forgetting_the_structure_goes_back_to_none(dialog, fresh_db, tourney) -> None:
    tourney_payouts.store_payouts(fresh_db, tourney, [5000, 3000])
    dialog.refresh()

    dialog.clear()

    assert tourney_payouts.stored_payouts(fresh_db, tourney) is None
    assert not dialog.clearButton.isEnabled() and dialog.changed


@pytest.mark.qt
def test_the_replayer_prices_the_hand_again_only_when_the_structure_changed(qtbot) -> None:
    priced = []
    replayer = SimpleNamespace(
        shared_hand="hand",
        hand_icm=None,
        _price_hand_icm=lambda hand: priced.append(hand) or "priced",
        update=lambda: None,
    )

    GuiReplayer.payouts_changed(replayer, False)
    assert priced == [] and replayer.hand_icm is None

    GuiReplayer.payouts_changed(replayer, True)
    assert priced == ["hand"] and replayer.hand_icm == "priced"


@pytest.mark.qt
def test_only_a_stored_tournament_hand_offers_the_dialog(qtbot) -> None:
    tour = SimpleNamespace(gametype={"type": "tour"})
    cash = SimpleNamespace(gametype={"type": "ring"})

    assert GuiReplayer._hand_tourney_id(SimpleNamespace(shared_hand_id=None), tour) is None
    assert GuiReplayer._hand_tourney_id(SimpleNamespace(shared_hand_id=7), cash) is None


@pytest.mark.qt
def test_a_new_structure_refreshes_the_tournament_s_bubble_factors(dialog, tourney, monkeypatch) -> None:
    from fpdb_3_legacy import bubble_factors

    refreshed = []
    monkeypatch.setattr(bubble_factors, "refresh_tourneys", lambda _db, ids: refreshed.append(list(ids)) or 0)

    dialog.presetCombo.setCurrentIndex(dialog.presetCombo.findData("sng_9max"))
    assert dialog.apply_preset()
    dialog.entry.setPlainText("60% 30%")
    assert not dialog.save_entry()  # refused: nothing changed, nothing to refresh
    dialog.clear()

    assert refreshed == [[tourney], [tourney]]
