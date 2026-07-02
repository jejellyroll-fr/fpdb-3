#!/usr/bin/env python
"""Opponents Report (head-to-head vs hero).

Lists the most relevant opponents to study, restricted to players actually
faced by the hero. All statistics (VPIP/PFR/3B, result, sample) are computed
over the hands the hero and the opponent shared at the same table.

Inspired by the DriveHUD "Opponents Report".

"Result vs hero" semantics
--------------------------
The result columns ("Result vs hero" in bb and "bb/100 vs hero") report the
*hero's* net result over the hands shared with the opponent. This is a
table-presence proxy: it measures how the hero fares when this opponent is at
the table, not a strict heads-up money transfer between the two players (which
is generally undefined in multiway pots). This matches the DriveHUD approach.

Exploit calibration
-------------------
Exploit detection is calibrated against the studied opponent population (see
:func:`calibrate_thresholds`): a leak is flagged when a player sits in the tail
of the pool for that stat. Calibration never relaxes a threshold past the
static floors in :data:`DEFAULT_THRESHOLDS`, and falls back to those floors on
small populations.

Performance note: the underlying ``opponentsReport`` query joins ``HandsPlayers``
to itself on ``handId`` (hero x each opponent in the hand), so the number of
scanned rows grows with opponents-per-hand before aggregation. The query is
driven from the hero's hands (indexed ``playerId``) and capped with a "Top N
opponents" limit, but on large databases (multi-million hands) and wide date
ranges the first load can still take a while. Narrow the date range and/or
limits in the filter sidebar to speed it up.
"""
# Copyright 2008-2011 Steffen Schaumburg
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.
from __future__ import annotations

from time import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Database, Filters, LeakDetector
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_opponents_report")


# ---------------------------------------------------------------------------
# Heuristic tuning constants (kept here for easy calibration)
# ---------------------------------------------------------------------------

# Minimum number of opportunities before a frequency-based leak is trusted.
MIN_OPP_FOR_LEAK = 10
# Sample size at which the danger score reaches full confidence.
DANGER_FULL_SAMPLE = 200

# Static fallback exploit thresholds (percentages). These are used as
# *floors*: the live thresholds are calibrated against the actual population
# of opponents (see ``calibrate_thresholds``) but never become looser than
# these values, so a soft player pool does not flag everyone.
FOLD_TO_3BET_HIGH = 65.0
FOLD_TO_CBET_HIGH = 55.0
OVERFOLD_WTSD_LOW = 22.0
OVERFOLD_AGGR_HIGH = 45.0
STATION_GAP = 15.0
STATION_VPIP = 30.0
WTSD_HIGH = 32.0

DEFAULT_THRESHOLDS = {
    "fold_to_3bet": FOLD_TO_3BET_HIGH,
    "fold_to_cbet": FOLD_TO_CBET_HIGH,
    "overfold_wtsd": OVERFOLD_WTSD_LOW,
    "overfold_aggr": OVERFOLD_AGGR_HIGH,
    "station_gap": STATION_GAP,
    "station_vpip": STATION_VPIP,
    "wtsd_high": WTSD_HIGH,
}

# Minimum population size before we trust data-driven calibration.
MIN_POPULATION_FOR_CALIBRATION = 8


def pct(done, chance) -> float:
    """Return 100 * done / chance, guarding against division by zero."""
    done = done or 0
    chance = chance or 0
    if chance <= 0:
        return 0.0
    return 100.0 * float(done) / float(chance)


def percentile(values: list[float], q: float) -> float | None:
    """Return the ``q``-th percentile (0..100) using linear interpolation.

    Returns ``None`` for an empty input.
    """
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return float(data[0])
    rank = (q / 100.0) * (len(data) - 1)
    low = int(rank)
    high = min(low + 1, len(data) - 1)
    frac = rank - low
    return float(data[low] + (data[high] - data[low]) * frac)


def calibrate_thresholds(rows: list[dict], base: dict | None = None) -> dict:
    """Derive exploit thresholds from the studied opponent population.

    A leak is "marked" when an opponent sits in the tail of the population for
    that stat (e.g. top quartile of fold-to-3bet). Calibration only kicks in
    with a large enough population and never relaxes a threshold past its
    static floor in :data:`DEFAULT_THRESHOLDS`, so the report stays meaningful
    on small or unusually soft samples.
    """
    base = dict(base if base is not None else DEFAULT_THRESHOLDS)
    if len(rows) < MIN_POPULATION_FOR_CALIBRATION:
        return base

    def col(key, opp_key=None, min_opp=MIN_OPP_FOR_LEAK):
        out = []
        for r in rows:
            if opp_key is not None and (r.get(opp_key, 0) or 0) < min_opp:
                continue
            value = r.get(key)
            if value is not None:
                out.append(value)
        return out

    calibrated = dict(base)

    # "High" thresholds: flag the top quartile, but never below the floor.
    p75_f3b = percentile(col("fold_to_3bet", "f3b_opp"), 75)
    if p75_f3b is not None:
        calibrated["fold_to_3bet"] = max(base["fold_to_3bet"], p75_f3b)

    p75_fcb = percentile(col("fold_to_cbet", "f_cb_opp"), 75)
    if p75_fcb is not None:
        calibrated["fold_to_cbet"] = max(base["fold_to_cbet"], p75_fcb)

    gaps = [r["vpip"] - r["pfr"] for r in rows if r.get("vpip") is not None and r.get("pfr") is not None]
    p75_gap = percentile(gaps, 75)
    if p75_gap is not None:
        calibrated["station_gap"] = max(base["station_gap"], p75_gap)

    p75_wtsd = percentile(col("wtsd"), 75)
    if p75_wtsd is not None:
        calibrated["wtsd_high"] = max(base["wtsd_high"], p75_wtsd)

    # "Low" threshold: flag the bottom quartile of WtSD (over-folders), but
    # never above the floor.
    p25_wtsd = percentile(col("wtsd"), 25)
    if p25_wtsd is not None:
        calibrated["overfold_wtsd"] = min(base["overfold_wtsd"], p25_wtsd)

    return calibrated


def classify_player_type(vpip: float, pfr: float) -> str:
    """Classify a player's style from VPIP/PFR percentages."""
    if vpip >= 40:
        return "LAG" if pfr >= 25 else "Loose Passive"
    if vpip >= 25:
        return "TAG" if pfr >= 18 else "Calling Station"
    if vpip >= 15:
        return "TAG (Tight)" if pfr >= 12 else "Weak Tight"
    return "NIT" if pfr >= 10 else "Rock"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_metrics(raw: dict, thresholds: dict | None = None) -> dict:
    """Turn the raw SQL sums for one opponent into displayable metrics.

    ``raw`` keys are the lowercase column aliases returned by the
    ``opponentsReport`` query. ``thresholds`` lets the caller pass
    population-calibrated exploit cutoffs (see :func:`calibrate_thresholds`);
    when omitted the static :data:`DEFAULT_THRESHOLDS` are used.
    """
    hds = int(raw.get("hds", 0) or 0)
    hero_net_bb = float(raw.get("hero_net_bb", 0) or 0.0)
    opp_net_bb = float(raw.get("opp_net_bb", 0) or 0.0)

    vpip = pct(raw.get("vpip"), raw.get("vpip_opp"))
    pfr = pct(raw.get("pfr"), raw.get("pfr_opp"))
    three_bet = pct(raw.get("tb"), raw.get("tb_opp"))
    fold_to_3bet = pct(raw.get("f3b"), raw.get("f3b_opp"))
    fold_to_cbet = pct(raw.get("f_cb"), raw.get("f_cb_opp"))

    saw_f = int(raw.get("saw_f", 0) or 0)
    sd = int(raw.get("sd", 0) or 0)
    wtsd = pct(sd, saw_f)

    postflop_aggr_freq = pct(raw.get("postflop_aggr"), raw.get("postflop_seen"))

    # Per-100-hand rates over the hands shared with the hero. These are the
    # sample-normalised, comparable figures; the raw bb totals are kept too.
    # NB: this is the hero's (resp. opponent's) result over the *shared* hands,
    # i.e. a table-presence proxy, NOT a strict heads-up money transfer.
    opp_bb_per_100 = (100.0 * opp_net_bb / hds) if hds > 0 else 0.0
    hero_bb_per_100 = (100.0 * hero_net_bb / hds) if hds > 0 else 0.0

    metrics = {
        "opp_id": raw.get("opp_id"),
        "pname": raw.get("pname", ""),
        "hds": hds,
        "hero_net_bb": hero_net_bb,
        "opp_net_bb": opp_net_bb,
        "opp_bb_per_100": opp_bb_per_100,
        "hero_bb_per_100": hero_bb_per_100,
        "vpip": vpip,
        "pfr": pfr,
        "three_bet": three_bet,
        "fold_to_3bet": fold_to_3bet,
        "fold_to_cbet": fold_to_cbet,
        "wtsd": wtsd,
        "postflop_aggr_freq": postflop_aggr_freq,
        "f3b_opp": int(raw.get("f3b_opp", 0) or 0),
        "f_cb_opp": int(raw.get("f_cb_opp", 0) or 0),
        "saw_f": saw_f,
        "last_seen": raw.get("last_seen"),
        "profile": classify_player_type(vpip, pfr),
    }
    metrics["danger"] = compute_danger(metrics)

    # Leak Buster: normalise the (head-to-head vs hero) raw sums into the leak
    # metrics contract and run the rule engine. The static thresholds are the
    # floors; ``thresholds`` is accepted for forward-compatibility.
    metrics["leak_metrics"] = build_leak_metrics(raw)
    apply_leak_detection(metrics)
    return metrics


def build_leak_metrics(raw: dict) -> dict:
    """Map the ``opponentsReport`` raw sums to the LeakDetector metrics contract.

    Percentages reuse :func:`pct`; the sample keys mirror
    :func:`LeakDetector.compute_leak_metrics`. ``pct`` returns ``0.0`` (not
    ``None``) on a zero sample, but the per-rule ``min_sample`` gating keeps
    those rows from firing.
    """
    saw_f = int(raw.get("saw_f", 0) or 0)
    sd = int(raw.get("sd", 0) or 0)
    return {
        "fold_bb_vs_steal": pct(raw.get("bbsteal_fold"), raw.get("bbsteal_opp")),
        "fold_bb_vs_steal_opp": int(raw.get("bbsteal_opp", 0) or 0),
        "fold_to_3bet": pct(raw.get("f3b"), raw.get("f3b_opp")),
        "f3b_opp": int(raw.get("f3b_opp", 0) or 0),
        "cbet_flop": pct(raw.get("cb"), raw.get("cb_opp")),
        "cb_opp": int(raw.get("cb_opp", 0) or 0),
        "cbet_turn": pct(raw.get("cb2"), raw.get("cb2_opp")),
        "cb2_opp": int(raw.get("cb2_opp", 0) or 0),
        "fold_to_turn_cbet": pct(raw.get("f_cb2"), raw.get("f_cb2_opp")),
        "f_cb2_opp": int(raw.get("f_cb2_opp", 0) or 0),
        "wtsd": pct(sd, saw_f),
        "saw_f": saw_f,
        "wsd": pct(raw.get("wmsd"), sd),
        "sd": sd,
        "river_aggr_freq": pct(raw.get("river_aggr"), raw.get("river_seen")),
        "saw_4": int(raw.get("river_seen", 0) or 0),
        "river_bet_freq": pct(raw.get("cb3"), raw.get("cb3_opp")),
        "cb3_opp": int(raw.get("cb3_opp", 0) or 0),
    }


def apply_leak_detection(metrics: dict, thresholds: dict | None = None) -> None:
    """Run the LeakDetector engine and fill leak-related fields on ``metrics``.

    Sets ``leaks`` (list of detected leak dicts), ``exploit`` (primary leak
    title or ``"—"``) and ``exploit_score`` (used to rank opponents).
    """
    detected = LeakDetector.detect_leaks(metrics.get("leak_metrics", {}), thresholds)
    metrics["leaks"] = [
        {
            "key": d.key,
            "title": d.title,
            "advice": d.exploit_advice,
            "value": d.value,
            "score": d.score,
        }
        for d in detected
    ]
    if detected:
        metrics["exploit"] = detected[0].title
        metrics["exploit_score"] = detected[0].score
    else:
        metrics["exploit"] = "—"
        metrics["exploit_score"] = 0.0


def compute_danger(m: dict) -> float:
    """Danger score in [0, 10].

    Combines how much the opponent wins from the hero, a "tough regular"
    bonus, a post-flop aggression bonus, weighted by sample confidence.
    """
    base = 2.0
    winrate_term = 0.05 * m["opp_bb_per_100"]

    vpip = m["vpip"]
    pfr = m["pfr"]
    reg_bonus = 0.0
    if 18.0 <= vpip <= 32.0 and (vpip - pfr) <= 8.0:
        reg_bonus = 2.5

    aggr = m["postflop_aggr_freq"]
    aggr_bonus = clamp((aggr - 40.0) / 20.0, 0.0, 2.0) if aggr > 40.0 else 0.0

    raw = base + winrate_term + reg_bonus + aggr_bonus
    sample_weight = min(1.0, m["hds"] / float(DANGER_FULL_SAMPLE))
    return round(clamp(raw, 0.0, 10.0) * sample_weight, 1)


def pick_exploit(m: dict, thresholds: dict | None = None) -> tuple[str, float]:
    """Pick the most marked leak and return ``(label, severity)``.

    ``thresholds`` is a dict of population-calibrated cutoffs (see
    :func:`calibrate_thresholds`); when omitted the static
    :data:`DEFAULT_THRESHOLDS` are used. Severity (0..1+) is used to rank
    opponents by exploitability.
    """
    t = thresholds if thresholds is not None else DEFAULT_THRESHOLDS

    # Folds too much to 3-bets preflop
    if m["f3b_opp"] >= MIN_OPP_FOR_LEAK and m["fold_to_3bet"] > t["fold_to_3bet"]:
        return "3-bet light", (m["fold_to_3bet"] - t["fold_to_3bet"]) / 35.0 + 1.0

    # Folds too much to flop continuation bets
    if m["f_cb_opp"] >= MIN_OPP_FOR_LEAK and m["fold_to_cbet"] > t["fold_to_cbet"]:
        return "Barrel flop", (m["fold_to_cbet"] - t["fold_to_cbet"]) / 45.0 + 0.9

    # Sees flops, rarely reaches showdown, aggressive -> over-folds rivers
    if m["saw_f"] >= 20 and m["wtsd"] < t["overfold_wtsd"] and m["postflop_aggr_freq"] > t["overfold_aggr"]:
        return "Overfold river", (t["overfold_wtsd"] - m["wtsd"]) / 22.0 + 0.8

    # Calling station: wide VPIP, big VPIP/PFR gap
    if (m["vpip"] - m["pfr"]) > t["station_gap"] and m["vpip"] > t["station_vpip"]:
        return "Value thin", (m["vpip"] - m["pfr"]) / 50.0 + 0.7

    # Reaches showdown a lot -> value bet larger
    if m["wtsd"] > t["wtsd_high"]:
        return "Value bet large", (m["wtsd"] - t["wtsd_high"]) / 30.0 + 0.5

    return "—", 0.0


# Sort modes for the combo box: label -> (metric key, descending)
SORT_MODES = [
    ("Most played", ("hds", True)),
    ("Most dangerous", ("danger", True)),
    ("Most exploitable", ("exploit_score", True)),
    ("Most recent", ("last_seen", True)),
]


class GuiOpponentsReport(QSplitter):
    def __init__(self, config, querylist, mainwin, debug=True) -> None:
        QSplitter.__init__(self, None)
        self.debug = debug
        self.conf = config
        self.main_window = mainwin
        self.sql = querylist

        self.MYSQL_INNODB = 2
        self.PGSQL = 3
        self.SQLITE = 4

        # Own DB connection to avoid clashing with other threads.
        self.db = Database.Database(self.conf, sql=self.sql)
        self.cursor = self.db.cursor

        self.opp_rows: list[dict] = []

        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Games": True,
            "Currencies": True,
            "Limits": True,
            "LimitSep": True,
            "LimitType": True,
            "Type": True,
            "UseType": "ring",
            "Dates": True,
            "Button1": False,
            "Button2": True,
        }

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton2Name("Refresh")
        self.filters.registerButton2Callback(self.refreshStats)

        # Minimum head-to-head hands selector.
        minhands_box = QWidget()
        minhands_layout = QHBoxLayout(minhands_box)
        minhands_layout.setContentsMargins(0, 0, 0, 0)
        minhands_layout.addWidget(QLabel("Min hands vs hero:"))
        self.minhands_spin = QSpinBox()
        self.minhands_spin.setRange(1, 100000)
        self.minhands_spin.setValue(20)
        minhands_layout.addWidget(self.minhands_spin)
        self.filters.layout().addWidget(minhands_box)

        # Top-N opponents selector (caps the result set, like DriveHUD's top 50).
        topn_box = QWidget()
        topn_layout = QHBoxLayout(topn_box)
        topn_layout.setContentsMargins(0, 0, 0, 0)
        topn_layout.addWidget(QLabel("Top N opponents:"))
        self.maxopponents_spin = QSpinBox()
        self.maxopponents_spin.setRange(1, 100000)
        self.maxopponents_spin.setValue(50)
        topn_layout.addWidget(self.maxopponents_spin)
        self.filters.layout().addWidget(topn_box)

        # Sort mode selector.
        sort_box = QWidget()
        sort_layout = QHBoxLayout(sort_box)
        sort_layout.setContentsMargins(0, 0, 0, 0)
        sort_layout.addWidget(QLabel("Sort by:"))
        self.sort_combo = QComboBox()
        for label, _ in SORT_MODES:
            self.sort_combo.addItem(label)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sort_layout.addWidget(self.sort_combo)
        self.filters.layout().addWidget(sort_box)

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setWidget(self.filters)

        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("statsSurface")
        self.stats_frame.setLayout(QVBoxLayout())

        self.view = QTableView()
        self.view.verticalHeader().hide()
        self.model = QStandardItemModel(0, 9, self.view)
        self.model.setSortRole(Qt.ItemDataRole.UserRole)
        self.view.setModel(self.model)
        self.stats_frame.layout().addWidget(self.view)

        self.addWidget(scroll)
        self.addWidget(self.stats_frame)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def refreshStats(self, checkState=None) -> None:
        try:
            self.fillStatsFrame()
        except ValueError as e:
            if str(e) == "No data found":
                self.db.rollback()
                return
            raise

    def fillStatsFrame(self) -> None:
        startTime = time()
        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        limits = self.filters.getLimits()
        dates = self.filters.getDates()
        games = self.filters.getGames()
        currencies = self.filters.getCurrencies()

        sitenos = []
        playerids = []

        for site in sites:
            hname = heroes.get(site, "")
            if not hname:
                log.info(f"fillStatsFrame: site '{site}' has no selected hero, skipping")
                continue
            # Plot the hero the user selected, resolved variant-aware:
            # get_player_id maps a "PokerStars" selection to the hero's
            # "PokerStars.FR" account, so data imported under a site skin still
            # shows. Fall back to the site's hero-flagged players if unresolved.
            result = self.db.get_player_id(self.conf, site, hname)
            pids = [int(result)] if result is not None else self.db.get_hero_player_ids(site)
            for pid in pids:
                if pid not in playerids:
                    playerids.append(pid)
                    actual_site_id = self.db.get_player_site_id(pid)
                    if actual_site_id is not None:
                        sitenos.append(actual_site_id)
                    else:
                        sitenos.append(siteids[site])

        if not sitenos:
            log.warning("fillStatsFrame: No sites selected")
            sitenos = [2]
        if not playerids:
            log.warning("fillStatsFrame: No hero player ids found")
            return
        if not limits:
            log.warning("fillStatsFrame: No limits found")
            return

        query = self.refineQuery(
            self.sql.query["opponentsReport"],
            playerids,
            sitenos,
            limits,
            dates,
            games,
            currencies,
        )
        log.info(f"OpponentsReport refined SQL:\n{query}")
        self.cursor.execute(query)
        result = self.cursor.fetchall()
        colnames = [desc[0].lower() for desc in self.cursor.description]
        log.info(f"OpponentsReport: fetched {len(result)} opponents")

        if len(result) == 0:
            from PySide6.QtWidgets import QMessageBox

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("FPDB 3 info")
            msg.setText("No data found for the selected filters.")
            msg.exec()
            raise ValueError("No data found")

        # Build per-opponent metrics + run the Leak Buster rule engine (static
        # thresholds). ``compute_metrics`` already populates ``leaks``,
        # ``exploit`` and ``exploit_score`` from LeakDetector.
        self.opp_rows = []
        for sqlrow in result:
            raw = {colnames[i]: sqlrow[i] for i in range(len(colnames))}
            self.opp_rows.append(compute_metrics(raw))

        self.populate_table()
        self.db.rollback()
        log.debug(f"Opponents report displayed in {time() - startTime:.2f} seconds")

    # ------------------------------------------------------------------
    # Table population / sorting
    # ------------------------------------------------------------------
    def _on_sort_changed(self, _index) -> None:
        if self.opp_rows:
            self.populate_table()

    def _sorted_rows(self) -> list[dict]:
        idx = max(0, self.sort_combo.currentIndex())
        key, desc = SORT_MODES[idx][1]

        def sort_key(row):
            value = row.get(key)
            if value is None:
                return ""
            return value

        return sorted(self.opp_rows, key=sort_key, reverse=desc)

    def populate_table(self) -> None:
        # (header, tooltip)
        columns = [
            ("Opponent", "Opponent screen name"),
            ("Hands vs hero", "Number of hands shared at the same table as the hero"),
            (
                "Result vs hero (bb)",
                "Hero's total result (in big blinds) over the hands shared with this opponent.\n"
                "This is a table-presence proxy, NOT a strict heads-up money transfer.",
            ),
            (
                "bb/100 vs hero",
                "Hero's win rate (bb per 100 hands) over the hands shared with this opponent.\n"
                "Sample-normalised version of the result column; same table-presence proxy.",
            ),
            ("VPIP/PFR/3B", "Opponent's preflop style over the shared hands"),
            ("Profile", "Opponent style classification from VPIP/PFR"),
            ("Danger", "How tough this opponent is (0-10), weighted by sample size"),
            ("Main exploit", "Most marked leak detected for this opponent"),
            ("Leaks", "All leaks detected (Leak Buster). Hover for the exploit advice."),
        ]
        self.model.clear()
        self.model.setColumnCount(len(columns))
        self.model.setHorizontalHeaderLabels([c[0] for c in columns])
        for idx, (_, tip) in enumerate(columns):
            self.model.setHeaderData(idx, Qt.Orientation.Horizontal, tip, Qt.ItemDataRole.ToolTipRole)

        for m in self._sorted_rows():
            row_items = []

            name_item = self._make_item(m["pname"], m["pname"], align_left=True)
            row_items.append(name_item)

            row_items.append(self._make_item(f"{m['hds']}", m["hds"]))

            net = m["hero_net_bb"]
            net_item = self._make_item(f"{net:+.0f}", net)
            net_item.setForeground(QBrush(QColor("#2e7d32") if net >= 0 else QColor("#c62828")))
            row_items.append(net_item)

            bb100 = m["hero_bb_per_100"]
            bb100_item = self._make_item(f"{bb100:+.1f}", bb100)
            bb100_item.setForeground(QBrush(QColor("#2e7d32") if bb100 >= 0 else QColor("#c62828")))
            row_items.append(bb100_item)

            vpr = f"{m['vpip']:.0f}/{m['pfr']:.0f}/{m['three_bet']:.0f}"
            row_items.append(self._make_item(vpr, m["vpip"]))

            row_items.append(self._make_item(m["profile"], m["profile"], align_left=True))

            danger = m["danger"]
            danger_item = self._make_item(f"{danger:.0f}/10", danger)
            row_items.append(danger_item)

            row_items.append(self._make_item(m["exploit"], m["exploit_score"], align_left=True))

            leaks = m.get("leaks", [])
            leaks_text = ", ".join(leak["title"] for leak in leaks) if leaks else "—"
            leaks_item = self._make_item(leaks_text, len(leaks), align_left=True)
            if leaks:
                advice = "\n".join(f"• {leak['title']} → {leak['advice']}" for leak in leaks)
                leaks_item.setData(advice, Qt.ItemDataRole.ToolTipRole)
            row_items.append(leaks_item)

            self.model.appendRow(row_items)

        self.view.setSortingEnabled(True)
        self.view.resizeColumnsToContents()
        self.view.resizeRowsToContents()

    @staticmethod
    def _make_item(text, sort_value, align_left: bool = False) -> QStandardItem:
        item = QStandardItem(str(text))
        item.setData(sort_value, Qt.ItemDataRole.UserRole)
        item.setEditable(False)
        if not align_left:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    # ------------------------------------------------------------------
    # Query refinement
    # ------------------------------------------------------------------
    def refineQuery(self, query, playerids, sitenos, limits, dates, games, currencies):
        # Hero player ids -> "in (1, 2)"
        nametest = str(tuple(playerids))
        nametest = nametest.replace("L", "").replace(",)", ")")
        query = query.replace("<player_test>", nametest)

        # Games
        gametest = ""
        if self.filters.display.get("Games") and games:
            gametest = str(tuple(games)).replace("L", "").replace(",)", ")").replace("u'", "'")
            gametest = f"and gt.category in {gametest}"
        elif self.filters.display.get("Games"):
            gametest = "and gt.category IS NULL"
        query = query.replace("<game_test>", gametest)

        # Currencies
        currencytest = str(tuple(currencies)).replace(",)", ")").replace("u'", "'")
        currencytest = f"AND gt.currency in {currencytest}"
        query = query.replace("<currency_test>", currencytest)

        # Sites
        sitetest = ""
        if self.filters.display.get("Sites"):
            if sitenos:
                sitetest = str(tuple(sitenos)).replace("L", "").replace(",)", ")").replace("u'", "'")
                sitetest = f"and gt.siteId in {sitetest}"
            else:
                sitetest = "and gt.siteId IS NULL"
        query = query.replace("<site_test>", sitetest)

        # Big blind / limits
        bbtest = self.filters.get_limits_where_clause(limits)
        query = query.replace("<gtbigBlind_test>", bbtest)

        # Cast helper used by some backends
        if self.db.backend == self.MYSQL_INNODB:
            query = query.replace("<signed>", "signed ")
        else:
            query = query.replace("<signed>", "")

        # Dates
        query = query.replace("<datestest>", " between '" + dates[0] + "' and '" + dates[1] + "'")

        # Minimum head-to-head hands
        query = query.replace("<minhands>", str(self.minhands_spin.value()))

        # Cap the number of opponents returned (top-N by hands played).
        query = query.replace("<maxopponents>", str(self.maxopponents_spin.value()))

        return query


def main(argv=None):
    import sys

    if argv is None:
        argv = sys.argv[1:]

    import fpdb_3_legacy.Configuration as Configuration

    config = Configuration.Config()

    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication([])
    import fpdb_3_legacy.SQL as SQL

    sql = SQL.Sql(db_server=settings["db-server"])
    main_window = QMainWindow()
    i = GuiOpponentsReport(config, sql, main_window)
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
