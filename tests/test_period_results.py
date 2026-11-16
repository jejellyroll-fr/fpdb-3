"""Cash results per day, week and month for the Results calendar (#827).

Days follow HudCache (#600): the hand's own UTC offset, then ``day_start``. The
zone is pinned to New York with pytz, as in test_hud_day, so these run the same
on every platform.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytz

from fpdb_3_legacy import hud_day
from fpdb_3_legacy import period_results as pr

ROOT = Path(__file__).resolve().parent.parent
NEW_YORK = pytz.timezone("America/New_York")
STARS_FILE = ROOT / "regression-test-files" / "cash" / "Stars" / "Flop" / "NLHE-6max-USD-0.05-0.10-200911.txt"


def _new_york(utc: datetime) -> timedelta:
    return pytz.utc.localize(utc).astimezone(NEW_YORK).utcoffset()


@pytest.fixture(name="new_york")
def fixture_new_york(monkeypatch) -> None:
    monkeypatch.setattr(hud_day, "local_offset", _new_york)


def _row(hand_id, start, profit, **fields):
    """A periodResultsHands row: id, start (UTC), profit, all-in EV, showdown, big blind, currency.

    ``fields`` overrides ``ev`` (the profit by default), ``showdown``, ``bb`` (10) and ``currency`` (USD).
    """
    row = {"ev": profit, "showdown": False, "bb": 10, "currency": "USD", **fields}
    return (hand_id, start, profit, row["ev"], row["showdown"], row["bb"], row["currency"])


# -- days, weeks, months ------------------------------------------------------


@pytest.mark.usefixtures("new_york")
@pytest.mark.parametrize(
    ("start", "day"),
    [
        (datetime(2026, 1, 15, 4, 30), date(2026, 1, 14)),  # 23:30 EST the day before
        (datetime(2026, 7, 15, 4, 30), date(2026, 7, 15)),  # 00:30 EDT
    ],
    ids=["winter", "summer"],
)
def test_a_hand_takes_the_offset_of_its_own_date(start, day) -> None:
    assert pr.local_day(start) == day


@pytest.mark.usefixtures("new_york")
def test_the_day_agrees_with_hudcache() -> None:
    for start in (datetime(2026, 3, 8, 6, 59, 59), datetime(2026, 3, 8, 7, 0), datetime(2026, 11, 1, 5, 30)):
        for day_start in (0.0, 4.0):
            assert pr.local_day(start, day_start).strftime(hud_day.STYLE_KEY_FORMAT) == hud_day.style_key(
                start,
                day_start,
            )


@pytest.mark.usefixtures("new_york")
def test_day_start_keeps_a_late_session_in_one_day() -> None:
    # 01:30 EST on the 15th, with days starting at 04:00, is still the 14th.
    assert pr.local_day(datetime(2026, 1, 15, 6, 30), 4.0) == date(2026, 1, 14)
    assert pr.local_day(datetime(2026, 1, 15, 6, 30), 0.0) == date(2026, 1, 15)


@pytest.mark.usefixtures("new_york")
def test_a_text_start_time_from_sqlite_is_read() -> None:
    hands = pr.parse_hands([_row(1, "2026-01-15 04:30:00", 100)])

    assert hands[0].start_time == datetime(2026, 1, 15, 4, 30)


def test_weeks_start_on_monday_and_months_on_the_first() -> None:
    sunday = date(2026, 11, 15)

    assert pr.period_start(sunday, pr.WEEK) == date(2026, 11, 9)
    assert pr.period_end(date(2026, 11, 9), pr.WEEK) == sunday
    assert pr.period_start(sunday, pr.MONTH) == date(2026, 11, 1)
    assert pr.period_end(date(2026, 2, 1), pr.MONTH) == date(2026, 2, 28)
    assert pr.period_end(sunday, pr.DAY) == sunday
    with pytest.raises(ValueError, match="granularity"):
        pr.period_start(sunday, "year")


@pytest.mark.usefixtures("new_york")
def test_hands_are_summed_per_period() -> None:
    results = pr.build_results(
        [
            _row(3, datetime(2026, 11, 10, 20, 0), -50),  # Tuesday the 10th
            _row(1, datetime(2026, 11, 9, 20, 0), 100),  # Monday the 9th
            _row(2, datetime(2026, 11, 9, 21, 0), 30),
            _row(4, datetime(2026, 12, 1, 20, 0), 10),  # next month
        ],
    )

    days = results.periods[pr.DAY]
    assert [(day.start, day.hands, day.money("USD")) for day in days] == [
        (date(2026, 11, 9), 2, 130),
        (date(2026, 11, 10), 1, -50),
        (date(2026, 12, 1), 1, 10),
    ]
    assert days[0].hand_ids == [1, 2]
    weeks = results.periods[pr.WEEK]
    assert [(week.start, week.hands) for week in weeks] == [(date(2026, 11, 9), 3), (date(2026, 11, 30), 1)]
    months = results.periods[pr.MONTH]
    assert [(month.start, month.money("USD")) for month in months] == [(date(2026, 11, 1), 80), (date(2026, 12, 1), 10)]
    assert [hand.hand_id for hand in results.hands_between(date(2026, 11, 9), date(2026, 11, 9))] == [1, 2]
    assert results.last_day() == date(2026, 12, 1)


@pytest.mark.usefixtures("new_york")
def test_a_hand_near_midnight_is_filed_under_its_local_day() -> None:
    # 03:00 UTC on the 1st of December is 22:00 on the 30th of November in New York.
    results = pr.build_results([_row(1, datetime(2026, 12, 1, 3, 0), 100)])

    assert results.periods[pr.DAY][0].start == date(2026, 11, 30)
    assert results.periods[pr.MONTH][0].start == date(2026, 11, 1)


# -- currencies and big blinds ------------------------------------------------


@pytest.mark.usefixtures("new_york")
def test_money_is_kept_per_currency_and_big_blinds_are_summed() -> None:
    results = pr.build_results(
        [
            _row(1, datetime(2026, 11, 9, 20, 0), 100, bb=10, currency="USD"),
            _row(2, datetime(2026, 11, 9, 21, 0), -40, bb=20, currency="eur"),
        ],
    )
    day = results.periods[pr.DAY][0]

    assert day.profit_minor == {"USD": 100, "EUR": -40}
    assert day.currencies == ["EUR", "USD"]
    assert day.profit_bb == 10 - 2
    assert pr.period_value(day, "USD") == 1.0
    assert pr.period_value(day, "EUR") == -0.4
    assert pr.period_value(day, "GBP") is None
    assert pr.period_value(day, pr.UNIT_BB) == 8
    assert pr.display_units(list(results.hands)) == [pr.UNIT_BB]


@pytest.mark.usefixtures("new_york")
def test_bb_per_100_uses_the_hands_with_a_blind_for_profit_and_ev() -> None:
    results = pr.build_results(
        [
            _row(1, datetime(2026, 11, 9, 20, 0), 200, ev=100, bb=100),
            _row(2, datetime(2026, 11, 9, 20, 1), -100, ev=-100, bb=100),
            _row(3, datetime(2026, 11, 9, 20, 2), 500, ev=500, bb=-1),  # fixed-limit sentinel: no BB
        ],
    )
    day = results.periods[pr.DAY][0]

    assert day.hands == 3
    assert day.bb_hands == 2
    assert day.profit_bb == 1.0
    assert day.all_in_ev_bb == 0.0
    assert day.bb_per_100 == 50.0
    assert day.ev_bb_per_100 == 0.0
    assert day.money("USD") == 600
    assert day.all_in_ev_minor == {"USD": 500}


def test_no_blind_means_no_bb_rate() -> None:
    period = pr.PeriodResult(start=date(2026, 11, 9), granularity=pr.DAY)
    period.add(pr.parse_hands([_row(1, datetime(2026, 11, 9, 20, 0), 50, bb=0)])[0])

    assert period.bb_per_100 is None
    assert period.ev_bb_per_100 is None
    assert pr.period_value(period, pr.UNIT_BB) is None


def test_a_hand_without_an_all_in_ev_counts_its_result() -> None:
    hand = pr.parse_hands([(1, datetime(2026, 11, 9, 20, 0), 75, None, False, 10, "USD")])[0]

    assert hand.all_in_ev_minor == 75


def test_display_units_offer_the_currency_when_there_is_only_one() -> None:
    hands = pr.parse_hands([_row(1, datetime(2026, 11, 9, 20, 0), 75, currency="EUR")])

    assert pr.display_units(hands) == [pr.UNIT_BB, "EUR"]
    assert pr.display_units(pr.parse_hands([_row(1, datetime(2026, 11, 9), 5, bb=-1)])) == ["USD"]


@pytest.mark.usefixtures("new_york")
def test_total_sums_every_period() -> None:
    results = pr.build_results(
        [
            _row(1, datetime(2026, 11, 9, 20, 0), 100, ev=60),
            _row(2, datetime(2026, 11, 10, 20, 0), -30, currency="EUR"),
        ],
    )
    overall = pr.total(results.periods[pr.DAY])

    assert overall.hands == 2
    assert overall.profit_minor == {"USD": 100, "EUR": -30}
    assert overall.all_in_ev_minor == {"USD": 60, "EUR": -30}
    assert overall.profit_bb == 10 - 3
    assert overall.hand_ids == [1, 2]
    assert pr.total([]) is None


# -- curves ---------------------------------------------------------------------


def test_the_four_curves_split_showdown_and_follow_the_ev() -> None:
    hands = pr.parse_hands(
        [
            _row(1, datetime(2026, 11, 9, 20, 0), 100, ev=40, showdown=True),
            _row(2, datetime(2026, 11, 9, 20, 1), -20, showdown=False),
            _row(3, datetime(2026, 11, 9, 20, 2), 50, showdown=True),
        ],
    )
    curves = pr.build_curves(hands, pr.UNIT_BB)

    assert curves.hands == 3
    assert curves.hand_ids == (1, 2, 3)
    assert curves.net == (0.0, 10.0, 8.0, 13.0)
    assert curves.ev == (0.0, 4.0, 2.0, 7.0)
    assert curves.showdown == (0.0, 10.0, 10.0, 15.0)
    assert curves.nonshowdown == (0.0, 0.0, -2.0, -2.0)
    assert curves.final("net") == curves.final("showdown") + curves.final("nonshowdown")

    money = pr.build_curves(hands, "USD")
    assert money.net == (0.0, 1.0, 0.8, 1.3)


def test_a_curve_skips_hands_it_cannot_show() -> None:
    hands = pr.parse_hands(
        [
            _row(1, datetime(2026, 11, 9, 20, 0), 100, currency="EUR"),
            _row(2, datetime(2026, 11, 9, 20, 1), 100, bb=-1),
        ],
    )

    assert pr.build_curves(hands, "USD").hand_ids == (2,)
    assert pr.build_curves(hands, pr.UNIT_BB).hand_ids == (1,)
    assert pr.build_curves([], pr.UNIT_BB).net == (0.0,)


# -- calendar -------------------------------------------------------------------


def test_month_weeks_start_on_monday_and_cover_the_month() -> None:
    weeks = pr.month_weeks(2026, 11)

    assert weeks[0][0] == date(2026, 10, 26)
    assert all(week[0].weekday() == 0 for week in weeks)
    assert date(2026, 11, 30) in weeks[-1]


@pytest.mark.parametrize(
    ("year", "month", "step", "expected"),
    [(2026, 11, 1, (2026, 12)), (2026, 12, 1, (2027, 1)), (2026, 1, -1, (2025, 12)), (2026, 5, -14, (2025, 3))],
)
def test_shift_month(year, month, step, expected) -> None:
    assert pr.shift_month(year, month, step) == expected


# -- the query on a real database -----------------------------------------------


def _filters(games=("holdem",), currencies=("USD",), seats=None):
    """What GuiResultsViewer.build_query reads of the filters: every date and limit, games shown."""
    return SimpleNamespace(
        getDates=lambda: ("1970-01-02 00:00:00", "2100-01-01 00:00:00"),
        getLimits=lambda: [],
        get_limits_where_clause=lambda _limits: "",
        getGames=lambda: list(games),
        getCurrencies=lambda: list(currencies),
        getSeats=lambda: seats,
        display={"Games": True},
    )


@pytest.fixture(name="imported")
def fixture_imported(tmp_path):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / "results.sqlite3"),
            "db-path": "",
        },
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    importer.addImportFile(str(STARS_FILE), "auto")
    stored, _duplicates, _partial, _skipped, errors, _time = importer.runImport()
    assert stored > 0
    assert errors == 0
    yield importer.database
    importer.close()


def test_the_query_reads_every_cash_hand_of_the_hero(imported) -> None:
    from fpdb_3_legacy.GuiResultsViewer import GuiResultsViewer

    cursor = imported.get_cursor()
    cursor.execute(
        "SELECT playerId, COUNT(*), SUM(totalProfit), SUM(COALESCE(allInEV, totalProfit)) FROM HandsPlayers "
        "GROUP BY playerId ORDER BY COUNT(*) DESC, playerId",
    )
    hero, hands, profit, ev = cursor.fetchone()

    viewer = GuiResultsViewer.__new__(GuiResultsViewer)  # pylint: disable=no-value-for-parameter
    viewer.sql = imported.sql
    viewer.filters = _filters(seats={"from": 2, "to": 10})
    query = viewer.build_query([hero])
    cursor.execute(query)
    results = pr.build_results(cursor.fetchall())

    assert len(results.hands) == hands
    overall = pr.total(results.periods[pr.MONTH])
    assert overall.hands == hands
    assert overall.profit_minor == {"USD": pytest.approx(float(profit))}
    assert overall.all_in_ev_minor == {"USD": pytest.approx(float(ev))}
    assert sum(day.hands for day in results.periods[pr.DAY]) == hands
    assert overall.bb_hands == hands  # every hand has its 10-cent big blind
    assert overall.profit_bb == pytest.approx(float(profit) / 10)
    curves = pr.build_curves(results.hands, pr.UNIT_BB)
    assert curves.final("net") == pytest.approx(overall.profit_bb)

    viewer.filters = _filters(currencies=())
    cursor.execute(viewer.build_query([hero]))
    assert cursor.fetchall() == []  # no currency selected: no hand, and valid SQL
    viewer.filters = _filters(games=("omahahi",))
    cursor.execute(viewer.build_query([hero]))
    assert cursor.fetchall() == []


# -- the Hand Viewer takes the hero the calendar sends --------------------------


def test_the_hand_viewer_takes_the_hero_names_it_is_sent() -> None:
    from fpdb_3_legacy.GuiHandViewer import GuiHandViewer

    viewer = GuiHandViewer.__new__(GuiHandViewer)  # pylint: disable=no-value-for-parameter
    hand = SimpleNamespace(players=[[1, "villain", 100], [2, "ProfileAlias", 100]])

    viewer.hero_names = frozenset()
    assert viewer._sent_hero(hand) is None  # pylint: disable=protected-access
    viewer.hero_names = frozenset({"ProfileAlias", "OtherSite"})
    assert viewer._sent_hero(hand) == "ProfileAlias"  # pylint: disable=protected-access
