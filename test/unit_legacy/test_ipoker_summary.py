"""Unit tests for the legacy iPokerSummary tournament-summary parser.

Exercises iPokerSummary.parseSummary() against hand-built iPoker-style
summary XML. TourneySummary.__init__ is patched out and its defaults are
seeded so the parser behaves as in the real pipeline (same pattern as
test_pacificpoker_summary_legacy.py / test_winamax_summary.py).
"""

from __future__ import annotations

import copy
import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.iPokerSummary import iPokerSummary

UTC = datetime.UTC

_INIT_DEFAULTS = {
    "tourneyName": None, "tourneyTypeId": None, "tourneyId": None,
    "startTime": None, "endTime": None, "tourNo": None, "currency": None,
    "buyinCurrency": None, "buyin": 0, "fee": 0, "hero": None, "maxseats": 0,
    "entries": 0, "speed": "Normal", "prizepool": 0, "buyInChips": 0, "mixed": None,
    "isRebuy": False, "isAddOn": False, "isKO": False, "isProgressive": False,
    "isMatrix": False, "isShootout": False, "isFast": False, "rebuyChips": None,
    "addOnChips": None, "rebuyCost": 0, "addOnCost": 0, "totalRebuyCount": None,
    "totalAddOnCount": None, "koBounty": 0, "isSng": False, "isStep": False,
    "stepNo": 0, "isChance": False, "chanceCount": 0, "isMultiEntry": False,
    "isReEntry": False, "isNewToGame": False, "isHomeGame": False, "isSplit": False,
    "isTime": False, "timeAmt": 0, "isSatellite": False, "isDoubleOrNothing": False,
    "isCashOut": False, "isOnDemand": False, "isFlighted": False, "isGuarantee": False,
    "guaranteeAmt": 0, "added": None, "addedCurrency": None, "isLottery": False,
    "tourneyMultiplier": 1, "comment": None,
}

_COLLECTIONS: dict[str, dict] = {
    "players": {},
    "playerIds": {},
    "tourneysPlayersIds": {},
    "ranks": {},
    "winnings": {},
    "winningsCurrency": {},
    "rebuyCounts": {},
    "addOnCounts": {},
    "koCounts": {},
}


def _template(
    *,
    game: str = "Holdem NL",
    table: str = "My SNG, 825200070",
    date: str = "07-Apr-2014 00:57:23",
    currency: str = "USD",
    hero: str = "Hero",
    tourno: str | None = "825200070",
    name: str = "My SNG",
    place: str = "3",
    buyin: str = "<buyin>$100+$5</buyin>",
    totalbuyin: str = "<totalbuyin>$100+$5</totalbuyin>",
    win: str = "<win>$13.92</win>",
    reward: str = "",
) -> str:
    tcode = f"<tournamentcode>{tourno}</tournamentcode>" if tourno is not None else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
    <session sessioncode="6231386447">
            <general>
        <mode>real</mode>
            <gametype>{game}</gametype>
            <tablename>{table}</tablename>
            <duration>00:01</duration>
            <gamecount>4</gamecount>
            <startdate>{date}</startdate>
            <currency>{currency}</currency>
            <nickname>{hero}</nickname>
            {tcode}
            <tournamentname>{name}</tournamentname><place>{place}</place>{buyin} {totalbuyin} {win} {reward}
        </general>
    </session>"""


def _make_summary(summary_text: str) -> iPokerSummary:
    config, db = MagicMock(), MagicMock()
    with patch("fpdb_3_legacy.TourneySummary.TourneySummary.__init__", return_value=None):
        summary = iPokerSummary(
            config=config, db=db, summaryText=summary_text, builtFrom="file"
        )
    summary.config = config
    summary.db = db
    summary.summaryText = summary_text
    summary.siteName = "iPoker"
    summary.siteId = 18
    summary.in_path = "none"
    summary.gametype = {"category": None, "limitType": None, "mix": "none"}
    for attr, value in _INIT_DEFAULTS.items():
        setattr(summary, attr, value)
    for attr, coll in copy.deepcopy(_COLLECTIONS).items():
        setattr(summary, attr, coll)
    return summary


def _parse(**kw) -> iPokerSummary:
    summary = _make_summary(_template(**kw))
    summary.parseSummary()
    return summary


class TestGameTypeDetection:
    def test_holdem_nl(self) -> None:
        s = _parse()
        assert s.gametype == {"category": "holdem", "limitType": "nl", "mix": "none", "base": "hold"}

    def test_stud_limit(self) -> None:
        s = _parse(game="7 Card Stud L", table="$5 Limit 7 Card Stud, 699476041", name="$5 Limit 7 Card Stud")
        assert s.gametype == {"category": "studhi", "limitType": "fl", "mix": "none", "base": "stud"}

    def test_stud_hi_lo_pot_limit(self) -> None:
        s = _parse(game="7 Card Stud Hi-Lo PL", name="7CS Hi-Lo")
        assert s.gametype == {"category": "studhilo", "limitType": "pl", "mix": "none", "base": "stud"}

    def test_omaha_hi_lo(self) -> None:
        s = _parse(game="Omaha Hi-Lo PL", name="Omaha HL")
        assert s.gametype == {"category": "omahahilo", "limitType": "pl", "mix": "none", "base": "hold"}

    def test_omaha_pot_limit(self) -> None:
        s = _parse(game="Omaha PL", name="Omaha")
        assert s.gametype == {"category": "omahahi", "limitType": "pl", "mix": "none", "base": "hold"}

    def test_six_plus_holdem(self) -> None:
        s = _parse(game="Six Plus Holdem NL", name="6+")
        assert s.gametype == {"category": "6_holdem", "limitType": "nl", "mix": "none", "base": "hold"}

    def test_no_category_defaults_to_5_omahahi(self) -> None:
        s = _parse(game="NL", name="X")
        assert s.gametype == {"category": "5_omahahi", "limitType": "nl", "mix": "none", "base": "hold"}


class TestDates:
    def test_abbreviated_month_format(self) -> None:
        s = _parse()
        assert s.startTime == datetime.datetime(2014, 4, 7, 0, 57, 23, tzinfo=UTC)

    def test_iso_default_format(self) -> None:
        s = _parse(date="2011-12-01 16:00:36")
        assert s.startTime == datetime.datetime(2011, 12, 1, 16, 0, 36, tzinfo=UTC)

    def test_slash_dotted_dmy_format(self) -> None:
        s = _parse(date="01/12/2011 16:00:36")
        assert s.startTime == datetime.datetime(2011, 12, 1, 16, 0, 36, tzinfo=UTC)

    def test_dot_separated_dmy_with_seconds(self) -> None:
        s = _parse(date="01.12.2011 16:00:36")
        assert s.startTime == datetime.datetime(2011, 12, 1, 16, 0, 36, tzinfo=UTC)

    def test_ymd_no_seconds(self) -> None:
        s = _parse(date="2011/12/01 16:00")
        assert s.startTime == datetime.datetime(2011, 12, 1, 16, 0, 0, tzinfo=UTC)

    def test_dmy_slash_no_seconds(self) -> None:
        s = _parse(date="01/12/2011 16:00")
        assert s.startTime == datetime.datetime(2011, 12, 1, 16, 0, 0, tzinfo=UTC)

    def test_ymd_with_seconds(self) -> None:
        s = _parse(date="2011/12/01 16:00:36")
        assert s.startTime == datetime.datetime(2011, 12, 1, 16, 0, 36, tzinfo=UTC)

    def test_unparseable_date_raises(self) -> None:
        with pytest.raises(FpdbParseError):
            _parse(date="bogus")


class TestCurrency:
    def test_real_money(self) -> None:
        s = _parse()
        assert s.currency == "USD"
        assert s.buyinCurrency == "USD"

    def test_fun_currency_is_play(self) -> None:
        s = _parse(currency="fun")
        assert s.buyinCurrency == "play"
        assert s.currency == "play"

    def test_play_currency_is_play(self) -> None:
        s = _parse(currency="play")
        assert s.buyinCurrency == "play"


class TestBuyinRake:
    def test_split_buyin_rake(self) -> None:
        s = _parse(buyin="<buyin>$100</buyin>", totalbuyin="<totalbuyin>$100 + $5</totalbuyin>")
        assert s.buyin == 10000
        assert s.fee == 500

    def test_fee_zeroed_when_only_buyin(self) -> None:
        s = _parse(buyin="<buyin>$100+$5</buyin>", totalbuyin="<totalbuyin>$100+$5</totalbuyin>")
        assert s.buyin == 10500
        assert s.fee == 0

    def test_freeroll_zero_buyin(self) -> None:
        s = _parse(
            buyin="<buyin>Einladung</buyin>",
            totalbuyin="<totalbuyin>$0</totalbuyin>",
            win="<win>$0</win>",
            reward="<rewarddrawn>$0</rewarddrawn>",
        )
        assert s.buyin == 0
        assert s.fee == 0
        assert s.buyinCurrency == "FREE"

    def test_token_buyin_uses_totalbuyin(self) -> None:
        s = _parse(buyin="<buyin>Token</buyin>", totalbuyin="<totalbuyin>$550</totalbuyin>", win="<win>0</win>")
        assert s.buyin == 55000
        assert s.fee == 0

    def test_token_buyin_without_totalbuyin(self) -> None:
        s = _parse(
            buyin="<buyin>Token</buyin>",
            totalbuyin="",
            win="<win>0</win>",
            reward="<rewarddrawn>$0</rewarddrawn>",
        )
        assert s.buyin == 0
        assert s.fee == 0

    def test_token_buyin_non_numeric_totalbuyin(self) -> None:
        s = _parse(
            buyin="<buyin>Token</buyin>",
            totalbuyin="<totalbuyin>abc</totalbuyin>",
            win="<win>0</win>",
            reward="<rewarddrawn>$0</rewarddrawn>",
        )
        assert s.buyin == 0
        assert s.fee == 0

    def test_token_buyin_symbol_only_totalbuyin(self) -> None:
        s = _parse(
            buyin="<buyin>Token</buyin>",
            totalbuyin="<totalbuyin>$</totalbuyin>",
            win="<win>0</win>",
            reward="<rewarddrawn>$0</rewarddrawn>",
        )
        assert s.buyin == 0
        assert s.fee == 0

    def test_fpp_buyin_currency(self, monkeypatch) -> None:
        monkeypatch.setattr(iPokerSummary, "re_fpp", pytest.importorskip("re").compile(r"^\$"))
        s = _parse()
        assert s.buyinCurrency == "FPP"


class TestTourneyInfo:
    def test_hero_added_with_rank_and_winnings(self) -> None:
        s = _parse()
        assert s.hero is None
        assert s.players == {"Hero": [1]}
        assert s.ranks["Hero"] == [3]
        assert s.winnings["Hero"] == [1392]

    def test_tour_no_from_table(self) -> None:
        s = _parse(tourno=None, table="My SNG, 825200070", reward="<rewarddrawn>$0</rewarddrawn>")
        assert s.tourNo == "825200070"

    def test_tour_no_from_table_split_fallback(self) -> None:
        s = _parse(
            tourno=None,
            table="Tournament 123, 456 abc",
            reward="<rewarddrawn>$0</rewarddrawn>",
        )
        assert s.tourNo == "456"

    def test_tour_no_from_tournament_code(self) -> None:
        s = _parse()
        assert s.tourNo == "825200070"

    def test_tourney_name_strips_tour_no_suffix(self) -> None:
        s = _parse(name="My SNG 825200070")
        assert s.tourneyName == "My SNG"

    def test_na_place_leaves_rank_none(self) -> None:
        s = _parse(place="N/A", win="<win>N/A</win>")
        assert s.ranks["Hero"] == [None]
        assert s.winnings["Hero"] == [None]

    def test_place_without_win_leaves_winnings_none(self) -> None:
        s = _parse(win="<win>N/A</win>")
        assert s.ranks["Hero"] == [3]
        assert s.winnings["Hero"] == [None]


class TestTwisterDetection:
    def test_twister_multiplier_over_one_is_lottery(self) -> None:
        s = _make_summary("x")
        s._detect_twister_tournament({"NAME": "Twister $1 SNG", "REWARDDRAWN": "$300", "TOTBUYIN": "$100"})
        assert s.isLottery is True
        assert s.tourneyMultiplier == 3

    def test_twister_multiplier_equal_one_not_lottery(self) -> None:
        s = _make_summary("x")
        s._detect_twister_tournament({"NAME": "Twister $1 SNG", "REWARDDRAWN": "$100", "TOTBUYIN": "$100"})
        assert s.isLottery is False
        assert s.tourneyMultiplier == 1

    def test_twister_zero_buyin_not_lottery(self) -> None:
        s = _make_summary("x")
        s._detect_twister_tournament({"NAME": "Twister $1 SNG", "REWARDDRAWN": "$0", "TOTBUYIN": "$0"})
        assert s.isLottery is False

    def test_twister_missing_reward(self) -> None:
        s = _make_summary("x")
        s._detect_twister_tournament({"NAME": "Twister $1 SNG", "TOTBUYIN": "$100"})
        assert s.isLottery is False

    def test_non_twister_ignored(self) -> None:
        s = _make_summary("x")
        s._detect_twister_tournament({"NAME": "Regular SNG", "REWARDDRAWN": "$300", "TOTBUYIN": "$100"})
        assert s.isLottery is False

    def test_twister_invalid_amounts_ignored(self) -> None:
        s = _make_summary("x")
        s._detect_twister_tournament({"NAME": "Twister $1 SNG", "REWARDDRAWN": "abc", "TOTBUYIN": "$100"})
        assert s.isLottery is False


class TestErrors:
    def test_unparseable_text_raises(self) -> None:
        with pytest.raises(FpdbParseError):
            _parse(game="this is not a tournament")

    def test_cash_game_text_raises(self) -> None:
        text = _template(game="Holdem NL 0.50/1.00")
        with pytest.raises(FpdbParseError):
            _make_summary(text).parseSummary()

    def test_missing_tournament_info_raises(self) -> None:
        text = _template().replace(
            "<tournamentname>My SNG</tournamentname><place>3</place>"
            "<buyin>$100+$5</buyin> <totalbuyin>$100+$5</totalbuyin> <win>$13.92</win> ",
            "",
        )
        with pytest.raises(FpdbParseError):
            _make_summary(text).parseSummary()

    def test_missing_tour_no_raises(self) -> None:
        text = _template(tourno=None, table="abc", reward="<rewarddrawn>$0</rewarddrawn>")
        with pytest.raises(FpdbParseError):
            _make_summary(text).parseSummary()


class TestSplitRe:
    def test_matches_session_tag(self) -> None:
        summary = _make_summary("x")
        split_re = summary.getSplitRe("")
        assert split_re.search("<session sessioncode=123>")
        assert not split_re.search("<game gamecode=123>")


class TestConvertToDecimal:
    def test_empty_string(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("") == Decimal(0)

    def test_complex_multi_part_amount(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("0€ + 0,02€ + 0,23€") == Decimal("0.25")

    def test_simple_amount(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("$13.92") == Decimal("13.92")

    def test_amount_with_thousands_spaces(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("1 200") == Decimal("1200")

    def test_no_numeric_match_returns_zero(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("no numbers here") == Decimal(0)

    def test_empty_after_clean_returns_zero(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("€$") == Decimal(0)

    def test_non_numeric_part_is_skipped(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("0€ + abc + 0,23€") == Decimal("0.23")

    def test_letters_without_numbers_returns_zero(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("abc") == Decimal(0)

    def test_double_dot_returns_zero(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("1..2") == Decimal(0)

    def test_symbol_only_part_is_skipped(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("0€ + $ + 0,23€") == Decimal("0.23")

    def test_trailing_plus_is_tolerated(self) -> None:
        s = _make_summary("x")
        assert s.convert_to_decimal("5 + ") == Decimal(5)
