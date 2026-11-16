# Results Calendar

Cash results per day, week and month, with the profit curves of each period
([#827](https://github.com/jejellyroll-fr/fpdb-3/issues/827)).

The idea, the period aggregation and the four curves come from thecrawler1's
Results viewer (thecrawler1/fpdb-3, branch `personal`), rewritten on fpdb's own
filters, Hand Viewer and graph widgets.

## Using it

**Cash > Results Calendar** opens the tab. Choose the hero, sites, games,
currencies, limits, seats and dates in the sidebar, then **Refresh**. The
hands are read and summed in the background; the tab stays usable meanwhile.

- **Calendar**: the month of the last hand played, one cell per day with its
  result and hand count, tinted green or red. The last column is the week's
  result. ◀ and ▶ change month; a click on the month's name selects the whole
  month.
- **Period table**: every day, week or month of the filtered dates (the
  **Period** box), with the hands, the profit and the all-in EV in money (one
  amount per currency), the same in big blinds, BB/100 and EV BB/100, and the
  showdown and non-showdown results. Columns sort; the table exports like the
  other stat tables.
- **Curves**: net profit, all-in EV, showdown and non-showdown, hand by hand,
  for the period selected in the calendar or the table, or for all the hands
  when nothing is selected.
- **Review hands** (or a double-click on a cell or a row) opens the selected
  period's hands in the Hand Viewer.

**Unit** shows the calendar and the curves in big blinds, or in the currency
of the hands when they were all played in one.

## How the figures are worked out

- **Days** are the HudCache days of [#600](https://github.com/jejellyroll-fr/fpdb-3/issues/600):
  a hand's UTC start time is moved to the computer's local time with the offset
  in force at the hand's own date, then back by the **day start** set in the
  preferences, so a session that runs past midnight stays in one day and a hand
  near midnight does not change day with daylight saving time.
- **Weeks** start on Monday (ISO 8601); **months** on the 1st.
- **Money** is never added across currencies: a period played in two
  currencies shows both amounts.
- **Big blinds** divide each hand by its own big blind. Only hands with a known
  big blind count (fixed-limit games store none), and BB/100 and EV BB/100 use
  that same number of hands, as the Session Viewer does.
- **All-in EV**: a hand without one (older imports, other trackers) counts its
  result, which is what fpdb stores for a hand that had no all-in. The ring
  profit graph now does the same.

The aggregation lives in `fpdb_3_legacy/period_results.py`, which has no Qt and
can be reused by other views.
