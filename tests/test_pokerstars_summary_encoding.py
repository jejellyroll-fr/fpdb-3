"""A PokerStars summary is read as UTF-8 first, cp1252 only when it is not UTF-8 (#625).

cp1252 decodes almost any bytes, so trying it first turned a UTF-8 summary's
"€9.04" into "â‚¬9.04": the import stored buy-in 400, fee 9600, USD and a
prize pool of 0 for a €9.04 + €0.96 sit-and-go with an €81.36 pool.
"""

from __future__ import annotations

import pytest

SAMPLE = "regression-test-files/summaries/Stars/NLHE-EUR-SnG-10-201101.Sample.txt"


def stored_tourney(path, fresh_db, legacy_config):
    from fpdb_3_legacy.Importer import Importer

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.addImportFile(str(path), "auto")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute(
        "SELECT tt.buyIn, tt.fee, tt.currency, t.prizepool, t.entries, s.name FROM Tourneys t "
        "JOIN TourneyTypes tt ON tt.id = t.tourneyTypeId JOIN Sites s ON s.id = tt.siteId"
    )
    rows = cursor.fetchall()
    del importer
    return rows


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
def test_a_euro_sit_and_go_summary_keeps_its_buy_in_currency_and_prize_pool(
    tmp_path, fresh_db, legacy_config, encoding
) -> None:
    text = open(SAMPLE, encoding="utf-8").read()  # noqa: PTH123 - a fixture read
    path = tmp_path / "summary.txt"
    path.write_bytes(text.encode(encoding))

    rows = stored_tourney(path, fresh_db, legacy_config)

    assert rows == [(904, 96, "EUR", 8136, 9, "PokerStars.EU")]


def test_utf8_is_tried_before_cp1252() -> None:
    from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary

    codepage = list(PokerStarsSummary.codepage)
    assert codepage.index("utf8") < codepage.index("cp1252")
