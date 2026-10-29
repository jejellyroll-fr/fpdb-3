"""A PokerStars knockout summary's bounty money, kept apart from its prize money (#447).

The rank lines' winnings are prize money only; the bounties a player collected
are on one line of their own, which the summary parser used to ignore.
"""

from __future__ import annotations

import shutil

REENTRY_KO = "regression-test-files/summaries/Stars/NLHE-MTT-USD-250-250-30-202005.reentry.ko.txt"
NO_BOUNTY_LINE = "regression-test-files/summaries/Stars/5-Card-PLO-6max-MTT-USD-12.30-12.25-2.45-201611.progressive.txt"


def importer_of(samples, tmp_path, fresh_db, legacy_config):
    """Import ``samples``; the importer is returned because dropping it closes the database."""
    from fpdb_3_legacy.Importer import Importer

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    for index, sample in enumerate(samples):
        path = tmp_path / f"summary{index}.txt"
        shutil.copy(sample, path)
        importer.addImportFile(str(path), "auto")
        importer.runImport()
    return importer


def bounty_rows(db) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT p.name, tp.rank, tp.entryId, tp.winnings, tp.koCount, tp.koWinnings FROM TourneysPlayers tp "
        "JOIN Players p ON p.id = tp.playerId WHERE tp.koCount IS NOT NULL OR tp.koWinnings IS NOT NULL"
    )
    return cursor.fetchall()


def test_the_hero_s_bounties_are_stored_next_to_their_prize(tmp_path, fresh_db, legacy_config) -> None:
    # "You finished in 72nd place" on a re-entry, "You collected 5 bounties for a total of USD 875.00."
    _importer = importer_of([REENTRY_KO], tmp_path, fresh_db, legacy_config)

    assert bounty_rows(fresh_db) == [("joiso", 72, 2, 82717, None, 87500)]


def test_a_summary_without_the_bounty_line_stores_no_bounty_money(tmp_path, fresh_db, legacy_config) -> None:
    _importer = importer_of([NO_BOUNTY_LINE], tmp_path, fresh_db, legacy_config)

    assert bounty_rows(fresh_db) == []


def test_importing_the_summary_again_keeps_one_bounty_total(tmp_path, fresh_db, legacy_config) -> None:
    _importer = importer_of([REENTRY_KO, REENTRY_KO], tmp_path, fresh_db, legacy_config)

    assert bounty_rows(fresh_db) == [("joiso", 72, 2, 82717, None, 87500)]


def test_the_tournament_results_count_the_bounties_in_the_profit(tmp_path, fresh_db, legacy_config) -> None:
    _importer = importer_of([REENTRY_KO], tmp_path, fresh_db, legacy_config)
    query = (
        fresh_db.sql.query["tourneyResults"]
        .replace("<player_test>", "(SELECT id FROM Players WHERE name = 'joiso')")
        .replace("<site_test>", "(SELECT id FROM Sites)")
        .replace("<startdate_test>", "1970-01-01")
        .replace("<enddate_test>", "2100-01-01")
    )
    cursor = fresh_db.get_cursor()
    cursor.execute(query)

    profits = sorted(row[1] for row in cursor.fetchall())
    # One row per entry, each paying the $500 buy-in (bounty included) and the $30 fee. The
    # re-entry that finished 72nd won $827.17 of prize and the hero's $875.00 of bounties.
    assert profits == [-50000 - 3000, 82717 + 87500 - 50000 - 3000]


def test_the_player_report_shows_the_bounties_apart_and_inside_won(tmp_path, fresh_db, legacy_config) -> None:
    _importer = importer_of([REENTRY_KO], tmp_path, fresh_db, legacy_config)
    query = (
        fresh_db.sql.query["tourneyPlayerDetailedStats"]
        .replace("<nametest>", "(SELECT id FROM Players WHERE name = 'joiso')")
        .replace("<sitetest>", "")
        .replace("<startdate_test>", "1970-01-01")
        .replace("<enddate_test>", "2100-01-01")
    )
    cursor = fresh_db.get_cursor()
    cursor.execute(query)
    columns = [description[0].lower() for description in cursor.description]

    (row,) = (dict(zip(columns, values, strict=True)) for values in cursor.fetchall())
    assert row["bounties"] == 875.0
    assert row["won"] == 827.17 + 875.0
