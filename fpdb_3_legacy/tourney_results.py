"""Per-tournament results behind the Tourney Stats tab.

One :class:`TourneyResult` per (tournament, player) row the filters select,
and the plain-Python aggregations the tab draws from them: the overview, the
cumulative curves and the "by description / buy-in / date" groups. Kept free of
Qt so every figure the tab shows can be checked without a display.

Amounts follow ``tourneyPlayerDetailedStats``: prizes and bounties are stored in
cents, and so is the buy-in, except for play-money tournaments whose buy-in is
stored in chips.

A tournament imported from its hands alone has no prize recorded: its result is
unknown, not a loss. It counts as a tournament played, but stays out of every
money figure, ROI and ITM, which would otherwise read it as a lost buy-in.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

# Group-by modes of the results table.
BY_DESCRIPTION = "description"
BY_BUYIN = "buyin"
BY_DATE = "date"
BY_TOURNAMENT = "tournament"
GROUP_MODES = (BY_DESCRIPTION, BY_BUYIN, BY_DATE, BY_TOURNAMENT)

_LIMIT_NAMES = {"nl": "NL", "pl": "PL", "fl": "FL", "cn": "CAP", "cp": "CAP", "hp": "HP"}
_GAME_NAMES = {
    "holdem": "Hold'em",
    "omahahi": "Omaha",
    "omahahilo": "Omaha Hi/Lo",
    "fusion": "Fusion",
    "5_omahahi": "5-Card Omaha",
    "6_omahahi": "6-Card Omaha",
    "razz": "Razz",
    "studhi": "Stud",
    "studhilo": "Stud Hi/Lo",
    "27_3draw": "2-7 Triple Draw",
    "badugi": "Badugi",
}

# Per-tournament query. It reuses the placeholders GuiTourneyPlayerStats.refineQuery
# fills in for tourneyPlayerDetailedStats, so both see the same tournaments. Every
# backend accepts it as written: no backend-specific function is used.
TOURNEY_RESULTS_QUERY = """
    SELECT t.id                 AS tourneyId
          ,t.siteTourneyNo      AS tourneyNo
          ,t.tourneyTypeId      AS tourneyTypeId
          ,tp.playerId          AS playerId
          ,p.name               AS playerName
          ,s.name               AS siteName
          ,tt.currency          AS currency
          ,tt.buyIn             AS buyIn
          ,tt.fee               AS fee
          ,tt.category          AS category
          ,tt.limitType         AS limitType
          ,tt.speed             AS speed
          ,tt.maxSeats          AS maxSeats
          ,tt.knockout          AS knockout
          ,tt.reEntry           AS reEntry
          ,tt.sng               AS sng
          ,t.tourneyName        AS tourneyName
          ,t.entries            AS entries
          ,t.startTime          AS startTime
          ,t.endTime            AS endTime
          ,tp.rank              AS finish
          ,tp.winnings          AS winnings
          ,COALESCE(tp.koWinnings, tp.koCount * tt.koBounty, 0) AS bounties
          ,(SELECT COUNT(*) FROM Hands h WHERE h.tourneyId = t.id) AS handCount
    FROM TourneysPlayers tp
         INNER JOIN Tourneys t       ON (t.id = tp.tourneyId)
         INNER JOIN TourneyTypes tt  ON (tt.id = t.tourneyTypeId)
         INNER JOIN Sites s          ON (s.id = tt.siteId)
         INNER JOIN Players p        ON (p.id = tp.playerId)
    WHERE tp.playerId in <nametest> <sitetest>
    AND   (tt.maxSeats <seats_test> OR COALESCE(tt.maxSeats, 0) = 0)
    AND   ((t.startTime > '<startdate_test>' AND t.startTime < '<enddate_test>')
           OR t.startTime is NULL)
    ORDER BY t.startTime, t.id"""


@dataclass(frozen=True)
class TourneyResult:  # pylint: disable=too-many-instance-attributes  # one column per field
    """One player's result in one tournament, in display units."""

    tourney_id: int
    tourney_no: Any
    tourney_type_id: int
    player_id: int
    player_name: str
    site: str
    currency: str
    buy_in: float
    fee: float
    prize: float | None
    bounties: float
    finish: int | None = None
    entries: int | None = None
    start: datetime | None = None
    end: datetime | None = None
    hands: int = 0
    name: str = ""
    category: str = ""
    limit_type: str = ""
    speed: str = ""
    max_seats: int | None = None
    knockout: bool = False
    re_entry: bool = False
    sng: bool = False

    @property
    def known(self) -> bool:
        """Whether the result was recorded (a summary was imported)."""
        return self.prize is not None

    @property
    def cost(self) -> float:
        return self.buy_in + self.fee

    @property
    def won(self) -> float:
        """Everything received: prize plus bounties."""
        return (self.prize or 0.0) + self.bounties

    @property
    def net(self) -> float:
        return self.won - self.cost

    @property
    def cashed(self) -> bool:
        """In the money, as the ITM% of the stats query counts it: a prize, bounties aside."""
        return bool(self.prize and self.prize > 0)

    @property
    def description(self) -> str:
        return describe(self)

    @property
    def local_day(self) -> date | None:
        """The day the tournament started, on this computer's clock (times are stored in UTC)."""
        if self.start is None:
            return None
        try:
            return self.start.replace(tzinfo=UTC).astimezone().date()
        except (OverflowError, OSError, ValueError):
            return self.start.date()


def describe(result: TourneyResult) -> str:
    """A PokerTracker-like description: "SNG (3-max) Hyper NL Hold'em KO"."""
    if result.sng:
        kind = "SNG"
    elif result.entries and result.max_seats and result.entries > result.max_seats:
        kind = "MTT"
    else:
        kind = "Tourney"
    parts = [kind]
    if result.max_seats:
        parts.append(f"({result.max_seats}-max)")
    if result.speed and result.speed != "Normal":
        parts.append(result.speed)
    limit = _LIMIT_NAMES.get((result.limit_type or "").lower(), (result.limit_type or "").upper())
    game = _GAME_NAMES.get(result.category or "", result.category or "")
    if limit or game:
        parts.append(" ".join(p for p in (limit, game) if p))
    if result.knockout:
        parts.append("KO")
    if result.re_entry:
        parts.append("R/E")
    return " ".join(parts)


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", ""))
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def result_from_row(row: dict[str, Any]) -> TourneyResult:
    """Build a result from one row of :data:`TOURNEY_RESULTS_QUERY`, whatever the column case."""
    r = {str(key).casefold(): value for key, value in row.items()}
    currency = str(r.get("currency") or "USD")
    play = currency == "play"
    buy_in_raw = float(r.get("buyin") or 0)
    fee_raw = float(r.get("fee") or 0)
    finish = _as_int(r.get("finish"))
    return TourneyResult(
        tourney_id=int(r["tourneyid"]),
        tourney_no=r.get("tourneyno"),
        tourney_type_id=int(r["tourneytypeid"]),
        player_id=int(r["playerid"]),
        player_name=str(r.get("playername") or ""),
        site=str(r.get("sitename") or ""),
        currency=currency,
        # Play money keeps its buy-in in chips and has no fee, as in the stats query.
        buy_in=buy_in_raw if play else buy_in_raw / 100.0,
        fee=0.0 if play else fee_raw / 100.0,
        prize=None if r.get("winnings") is None else float(r["winnings"]) / 100.0,
        bounties=float(r.get("bounties") or 0) / 100.0,
        finish=finish if finish and finish > 0 else None,
        entries=_as_int(r.get("entries")),
        start=_as_datetime(r.get("starttime")),
        end=_as_datetime(r.get("endtime")),
        hands=_as_int(r.get("handcount")) or 0,
        name=str(r.get("tourneyname") or "").strip(),
        category=str(r.get("category") or ""),
        limit_type=str(r.get("limittype") or ""),
        speed=str(r.get("speed") or ""),
        max_seats=_as_int(r.get("maxseats")),
        knockout=bool(r.get("knockout")),
        re_entry=bool(r.get("reentry")),
        sng=bool(r.get("sng")),
    )


@dataclass
class Summary:  # pylint: disable=too-many-instance-attributes  # one running total per figure
    """Totals of a set of results, all in one currency.

    ``count`` is every tournament; the money figures, ITM and ROI cover the
    ``known`` ones only (see the module docstring).
    """

    currency: str = "USD"
    count: int = 0
    unknown: int = 0
    cost: float = 0.0
    won: float = 0.0
    bounties: float = 0.0
    cashes: int = 0
    first: int = 0
    second: int = 0
    third: int = 0
    ranked: int = 0
    finish_total: int = 0
    entries_total: int = 0
    entries_known: int = 0
    hands: int = 0

    def add(self, result: TourneyResult) -> None:
        self.count += 1
        self.hands += result.hands
        if result.known:
            self.cost += result.cost
            self.won += result.won
            self.bounties += result.bounties
            self.cashes += int(result.cashed)
        else:
            self.unknown += 1
        if result.finish:
            self.ranked += 1
            self.finish_total += result.finish
            self.first += int(result.finish == 1)
            self.second += int(result.finish == 2)
            self.third += int(result.finish == 3)
        if result.entries:
            self.entries_known += 1
            self.entries_total += result.entries

    @property
    def known(self) -> int:
        return self.count - self.unknown

    @property
    def net(self) -> float:
        return self.won - self.cost

    @property
    def roi(self) -> float | None:
        return 100.0 * self.net / self.cost if self.cost else None

    @property
    def itm(self) -> float | None:
        return 100.0 * self.cashes / self.known if self.known else None

    @property
    def avg_finish(self) -> float | None:
        return self.finish_total / self.ranked if self.ranked else None

    @property
    def avg_entries(self) -> float | None:
        return self.entries_total / self.entries_known if self.entries_known else None

    @property
    def avg_cost(self) -> float | None:
        return self.cost / self.known if self.known else None

    @property
    def per_tourney(self) -> float | None:
        return self.net / self.known if self.known else None


def summarize(results: Iterable[TourneyResult]) -> dict[str, Summary]:
    """Totals per currency: amounts in different currencies are never added together."""
    totals: dict[str, Summary] = {}
    for result in results:
        totals.setdefault(result.currency, Summary(currency=result.currency)).add(result)
    return totals


def main_currency(results: Sequence[TourneyResult]) -> str | None:
    """The currency most of the results were played in (first seen on a tie)."""
    if not results:
        return None
    counts = Counter(result.currency for result in results)
    best = max(counts.values())
    return next(result.currency for result in results if counts[result.currency] == best)


@dataclass
class Curves:
    """Running totals, one point per tournament in start order."""

    net: list[float] = field(default_factory=list)
    roi: list[float] = field(default_factory=list)
    itm: list[float] = field(default_factory=list)


def running_curves(results: Iterable[TourneyResult]) -> Curves:
    """Cumulative net, ROI% and ITM% after each tournament with a known result."""
    curves = Curves()
    net = cost = 0.0
    cashes = 0
    for index, result in enumerate((result for result in results if result.known), start=1):
        net += result.net
        cost += result.cost
        cashes += int(result.cashed)
        curves.net.append(net)
        curves.roi.append(100.0 * net / cost if cost else 0.0)
        curves.itm.append(100.0 * cashes / index)
    return curves


@dataclass
class Group:
    """One row of a grouped view."""

    key: tuple[Any, ...]
    label: str
    site: str
    summary: Summary
    results: list[TourneyResult] = field(default_factory=list)
    player_name: str = ""
    names: Counter[str] = field(default_factory=Counter)


def group_key(mode: str, result: TourneyResult) -> tuple[Any, ...]:
    """Which row of the ``mode`` view a result is counted in."""
    if mode == BY_DESCRIPTION:
        return (result.tourney_type_id, result.player_id)
    if mode == BY_BUYIN:
        return (result.currency, round(result.cost, 2))
    if mode == BY_DATE:
        day = result.local_day
        return (day.isoformat() if day else "", result.currency)
    if mode == BY_TOURNAMENT:
        return (result.tourney_id, result.player_id)
    raise ValueError(f"unknown group mode {mode!r}")


def group_results(mode: str, results: Iterable[TourneyResult]) -> list[Group]:
    """Group results for the ``mode`` view, groups in first-seen order."""
    groups: dict[tuple[Any, ...], Group] = {}
    for result in results:
        key = group_key(mode, result)
        group = groups.get(key)
        if group is None:
            group = Group(
                key=key,
                label=result.description if mode == BY_DESCRIPTION else "",
                site=result.site,
                summary=Summary(currency=result.currency),
                player_name=result.player_name,
            )
            groups[key] = group
        elif group.site != result.site:
            group.site = ""
        group.summary.add(result)
        group.results.append(result)
        if result.name:
            group.names[result.name] += 1
    return list(groups.values())


def filter_results(results: Iterable[TourneyResult], mode: str, key: tuple[Any, ...]) -> list[TourneyResult]:
    """The results counted in the ``key`` row of the ``mode`` view."""
    return [result for result in results if group_key(mode, result) == key]
