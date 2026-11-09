"""A hand that states the bounty money it won persists it as koWinnings (#754).

koCounts is a knockout *count* and lands in TourneysPlayers.koCount; the amount
in hundredths belongs in koWinnings, which the profit queries read first via
COALESCE(koWinnings, koCount * koBounty). Storing cents in koCounts would turn
a €0.23 bounty into 23 knockouts. Unibet 2026 KO hands are where the money is
known ("jejesat wins bounty, €0.23"); their summaries carry no bounty totals.
"""

from __future__ import annotations

from types import SimpleNamespace


def _add_tourney_player(db, name="hero", site_id=2, tourney_no="99042656") -> tuple[int, int, int]:
    """One tournament with one player entry; returns (tourneyId, playerId, tourneysPlayersId)."""
    cursor = db.get_cursor()
    cursor.execute(
        "INSERT INTO TourneyTypes (siteId, currency, buyIn, fee, category, limitType, knockout, koBounty)"
        " VALUES (?, 'EUR', 90, 10, 'holdem', 'nl', 1, NULL)",
        (site_id,),
    )
    cursor.execute(
        "INSERT INTO Tourneys (tourneyTypeId, siteTourneyNo, entries, prizepool) VALUES (?, ?, 21, 0)",
        (cursor.lastrowid, tourney_no),
    )
    tourney_id = cursor.lastrowid
    cursor.execute("INSERT INTO Players (name, siteId) VALUES (?, ?)", (name, site_id))
    player_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO TourneysPlayers (tourneyId, playerId, entryId) VALUES (?, ?, 1)",
        (tourney_id, player_id),
    )
    db.commit()
    return tourney_id, player_id, cursor.lastrowid


def _ko_row(db, player_id) -> tuple:
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT koCount, koWinnings FROM TourneysPlayers WHERE playerId = ?",
        (player_id,),
    )
    return cursor.fetchone()


def test_a_hand_ko_adds_one_count_and_the_bounty_money(fresh_db) -> None:
    tourney_id, player_id, tp_id = _add_tourney_player(fresh_db)
    hand = SimpleNamespace(
        tourneysPlayersIds={"hero": tp_id},
        koCounts={"hero": 1},
        koWinnings={"hero": 23},
        tourneyId=tourney_id,
        playerIds={"hero": player_id},
    )

    fresh_db.updateTourneyPlayerBounties(hand)

    assert _ko_row(fresh_db, player_id) == (1, 23)


def test_bounty_money_accumulates_over_hands_while_the_count_stays_a_count(fresh_db) -> None:
    tourney_id, player_id, tp_id = _add_tourney_player(fresh_db)
    for amount in (23, 45):
        hand = SimpleNamespace(
            tourneysPlayersIds={"hero": tp_id},
            koCounts={"hero": 1},
            koWinnings={"hero": amount},
            tourneyId=tourney_id,
            playerIds={"hero": player_id},
        )
        fresh_db.updateTourneyPlayerBounties(hand)

    assert _ko_row(fresh_db, player_id) == (2, 68)


def test_a_hand_without_ko_winnings_leaves_the_money_column_alone(fresh_db) -> None:
    # Older callers' hand stand-ins carry no koWinnings attribute at all.
    tourney_id, player_id, tp_id = _add_tourney_player(fresh_db)
    hand = SimpleNamespace(
        tourneysPlayersIds={"hero": tp_id},
        koCounts={"hero": 1},
        tourneyId=tourney_id,
        playerIds={"hero": player_id},
    )

    fresh_db.updateTourneyPlayerBounties(hand)

    assert _ko_row(fresh_db, player_id) == (1, None)
