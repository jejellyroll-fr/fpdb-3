#!/usr/bin/env python
"""Filters module for FPDB data filtering interface.

Provides a comprehensive filtering system for poker data analysis with support for:
- Site selection (PokerStars, Winamax, etc.)
- Game variants (Hold'em, Omaha, Stud, etc.)
- Date ranges and player selection
- Betting limits and position filters
- Modern UI with qt_material theme integration
"""

from __future__ import annotations

import itertools
import unicodedata
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QDateTime, Qt, QTime
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import SQL, Card, Configuration, Database
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
log = get_logger("filter")

# Constants for UI thresholds
MIN_ITEMS_FOR_CONTROLS = 2  # Minimum number of items to show control buttons
ICONS_DIR = Path(__file__).parent.parent / "icons"
ROOM_WEB_LOGOS_DIR = ICONS_DIR / "room_logos"
ROOM_ICON_FILES = {
    "betonline": "betonline.png",
    "betonlineag": "betonline.png",
    "betonlinepoker": "betonline.png",
    "boss": "boss.ico",
    "bovada": "bovada.png",
    "bwin": "party.png",
    "bwindepoker": "party.png",
    "bwinespoker": "party.png",
    "bwinfrpoker": "party.png",
    "bwinitpoker": "party.png",
    "bwinpoker": "party.png",
    "cake": "cake.jpg",
    "cakepoker": "cake.jpg",
    "enet": "enet.png",
    "entraction": "entraction.png",
    "everygame": "cake.jpg",
    "everygamepoker": "cake.jpg",
    "everleaf": "everleaf.png",
    "fulltilt": "ft.svg",
    "fulltiltpoker": "ft.svg",
    "ggpoker": "gg.png",
    "ipoker": "ipoker.png",
    "kingsclub": "kingsclub.png",
    "merge": "merge.png",
    "microgaming": "microgaming.png",
    "pacific": "pacific.png",
    "partypoker": "party.png",
    "partypokereu": "party.png",
    "partypokerfr": "party.png",
    "partypokerit": "party.png",
    "partypokeres": "party.png",
    "partypokerde": "party.png",
    "partypokernj": "party.png",
    "partypokerpt": "party.png",
    "partypokercom": "party.png",
    "pkr": "pkr.png",
    "pokerstars": "ps.svg",
    "pokerstarscom": "ps.svg",
    "pokerstarsde": "ps.svg",
    "pokerstarseu": "ps.svg",
    "pokerstarses": "ps.svg",
    "pokerstarsfr": "ps.svg",
    "pokerstarsit": "ps.svg",
    "pokerstarspt": "ps.svg",
    "sealswithclubs": "swc.png",
    "winamax": "wina.svg",
    "winningpoker": "winning.png",
}
ROOM_ICON_NETWORK_HINTS = (
    (("pokerstars",), "ps.svg"),
    (("party", "bwin", "borgata", "empire", "gamebookers", "intertops", "pokerroom", "wptpoker", "wpt"), "party.png"),
    (
        (
            "cake",
            "everygame",
            "juicystakes",
            "redstar",
            "sportsbetting",
            "tigergaming",
            "doylesroom",
            "poker4ever",
            "playersonly",
            "sunpoker",
        ),
        "cake.jpg",
    ),
    (("betonline",), "betonline.png"),
    (("americascardroom", "acrpoker", "blackchippoker", "truepoker", "yapoker"), "winning.png"),
    (("pacificpoker",), "pacific.png"),
)
ROOM_ICON_BADGE_COLORS = (
    "#2f80ed",
    "#00a86b",
    "#d45b9f",
    "#f2994a",
    "#8b5cf6",
    "#14b8a6",
    "#ef4444",
    "#64748b",
)
ROOM_ICON_CACHE: dict[str, QIcon] = {}


def _site_icon_key(site: str) -> str:
    normalized = unicodedata.normalize("NFKD", site)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return "".join(character for character in ascii_name.lower() if character.isalnum())


def resolve_site_icon_path(site: str) -> Path | None:
    site_key = _site_icon_key(site)
    for suffix in (".png", ".jpg", ".jpeg", ".svg"):
        web_logo_path = ROOM_WEB_LOGOS_DIR / f"{site_key}{suffix}"
        if web_logo_path.exists():
            return web_logo_path

    icon_file = ROOM_ICON_FILES.get(site_key)
    if not icon_file:
        for hints, hinted_icon_file in ROOM_ICON_NETWORK_HINTS:
            if any(hint in site_key for hint in hints):
                icon_file = hinted_icon_file
                break

    if not icon_file:
        return None

    icon_path = ICONS_DIR / icon_file
    return icon_path if icon_path.exists() else None


def _site_icon_badge_text(site: str) -> str:
    ignored_words = {"ag", "casino", "com", "de", "es", "eu", "fr", "it", "nj", "poker", "pt"}
    normalized = unicodedata.normalize("NFKD", site)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    words = [
        "".join(character for character in word if character.isalnum())
        for word in ascii_name.replace(".", " ").replace("-", " ").split()
    ]
    words = [word for word in words if word and word.lower() not in ignored_words]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return "".join(word[0] for word in words[:2]).upper()


def _build_generated_site_icon(site: str) -> QIcon:
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)

    site_key = _site_icon_key(site)
    color_index = sum(ord(character) for character in site_key) % len(ROOM_ICON_BADGE_COLORS)
    background_color = QColor(ROOM_ICON_BADGE_COLORS[color_index])

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(background_color)
    painter.setPen(QColor("#d8e6f3"))
    painter.drawRoundedRect(2, 2, 44, 44, 10, 10)
    painter.setPen(QColor("#ffffff"))
    font = QFont()
    font.setBold(True)
    font.setPointSize(15 if len(_site_icon_badge_text(site)) == 2 else 18)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, _site_icon_badge_text(site))
    painter.end()

    return QIcon(pixmap)


def resolve_site_icon(site: str) -> QIcon:
    site_key = _site_icon_key(site)
    if site_key in ROOM_ICON_CACHE:
        return ROOM_ICON_CACHE[site_key]

    icon_path = resolve_site_icon_path(site)
    icon = QIcon(str(icon_path)) if icon_path else _build_generated_site_icon(site)
    ROOM_ICON_CACHE[site_key] = icon
    return icon


class Filters(QWidget):
    """Main filtering widget for FPDB data analysis.

    Provides comprehensive filtering capabilities for poker data including:
    - Site and game selection
    - Date range filtering
    - Player and position filters
    - Betting limits and currency selection
    """

    def __init__(self, db: Any, display: dict[str, Any] | None = None) -> None:
        """Initialize the Filters widget.

        Args:
            db: Database connection object
            display: Dictionary controlling which filter sections to display
        """
        if display is None:
            display = {}
        super().__init__(None)
        self.db = db
        self.db_cursor: Any = db.cursor
        self.sql = db.sql
        self.conf = db.config
        self.display = display
        self.heroList: Any = None
        self.cbSites: dict[str, QCheckBox] = {}
        self.cbGames: dict[str, QCheckBox] = {}
        self.cbLimits: dict[str, QCheckBox] = {}
        self.cbPositions: dict[str, QCheckBox] = {}
        self.cbCurrencies: dict[str, QCheckBox] = {}
        self.cbGraphops: dict[str, Any] = {}
        self.cbTourney: dict[str, QCheckBox] = {}
        self.cbTourneyCat: dict[str, QCheckBox] = {}
        self.cbTourneyLim: dict[str, QCheckBox] = {}
        self.cbTourneyBuyin: dict[str, QCheckBox] = {}

        self.gameName = {
            "27_1draw": _("Single Draw 2-7 Lowball"),
            "27_3draw": _("Triple Draw 2-7 Lowball"),
            "a5_3draw": _("Triple Draw A-5 Lowball"),
            "5_studhi": _("5 Card Stud"),
            "badugi": _("Badugi"),
            "badacey": _("Badacey"),
            "badeucey": _("Badeucey"),
            "drawmaha": _("2-7 Drawmaha"),
            "a5_1draw": _("A-5 Single Draw"),
            "27_razz": _("2-7 Razz"),
            "fivedraw": _("5 Card Draw"),
            "holdem": _("Hold'em"),
            "6_holdem": _("Hold'em"),
            "omahahi": _("Omaha"),
            "fusion": _("Fusion"),
            "omahahilo": _("Omaha Hi/Lo"),
            "razz": _("Razz"),
            "studhi": _("7 Card Stud"),
            "studhilo": _("7 Card Stud Hi/Lo"),
            "5_omahahi": _("5 Card Omaha"),
            "5_omaha8": _("5 Card Omaha Hi/Lo"),
            "cour_hi": _("Courchevel"),
            "cour_hilo": _("Courchevel Hi/Lo"),
            "2_holdem": _("Double hold'em"),
            "irish": _("Irish"),
            "6_omahahi": _("6 Card Omaha"),
        }

        self.currencyName = {
            "USD": _("US Dollar"),
            "EUR": _("Euro"),
            "T$": _("Tournament Dollar"),
            "play": _("Play Money"),
        }

        self.filterText = {
            "limitsall": _("All"),
            "limitsnone": _("None"),
            "limitsshow": _("Show Limits"),
            "gamesall": _("All"),
            "gamesnone": _("None"),
            "positionsall": _("All"),
            "positionsnone": _("None"),
            "currenciesall": _("All"),
            "currenciesnone": _("None"),
            "seatsbetween": _("Between:"),
            "seatsand": _("And:"),
            "seatsshow": _("Show Number of Players"),
            "playerstitle": _("Hero:"),
            "sitestitle": (_("Sites") + ":"),
            "gamestitle": (_("Games") + ":"),
            "tourneytitle": (_("Tourney") + ":"),
            "tourneycat": (_("Category") + ":"),
            "limitstitle": _("Limits:"),
            "positionstitle": _("Positions:"),
            "seatstitle": _("Number of Players:"),
            "tourneylim": (_("Limit Type") + ":"),
            "groupstitle": _("Grouping:"),
            "posnshow": _("Show Position Stats"),
            "tourneybuyin": (_("Buyin") + ":"),
            "datestitle": _("Date:"),
            "currenciestitle": (_("Currencies") + ":"),
            "groupsall": _("All Players"),
            "cardstitle": (_("Hole Cards") + ":"),
            "limitsFL": "FL",
            "limitsNL": "NL",
            "limitsPL": "PL",
            "limitsCN": "CAP",
            "ring": _("Ring"),
            "tour": _("Tourney"),
            "limitsHP": "HP",
        }

        gen = self.conf.get_general_params()
        self.day_start = 0.0

        if "day_start" in gen:
            self.day_start = float(gen["day_start"])

        self.setLayout(QVBoxLayout())

        self.callback: dict[str, Any] = {}

        # Style is managed by qt_material applied at application level
        # We only add specific adjustments if necessary
        self.setStyleSheet(self.get_filter_specific_styles())
        self.make_filter()

    def get_filter_specific_styles(self) -> str:
        """Specific styles for filters that complement the qt_material theme."""
        try:
            from fpdb_3_legacy.ThemeManager import ThemeManager

            return ThemeManager().build_filter_stylesheet()
        except Exception:
            log.exception("Unable to build theme-aware filter stylesheet")
            return ""

    def make_filter(self) -> None:  # noqa: PLR0912, C901
        """Create all filter widgets based on display configuration.

        This method is complex by design as it handles multiple filter types
        and their conditional display logic.
        """
        self.siteid: dict[str, int] = {}
        self.cards: dict[str, bool] = {}
        self.type: str | None = None

        for site in self.conf.get_supported_sites():
            self.db_cursor.execute(self.sql.query["getSiteId"], (site,))
            result = self.db.cursor.fetchall()
            if len(result) == 1:
                self.siteid[site] = result[0][0]
            else:
                log.debug("Either 0 or more than one site matched for %s", site)

        self.start_date = QDateEdit(QDate(1970, 1, 1))
        self.end_date = QDateEdit(QDate(2100, 1, 1))

        self.cbGroups: dict[str, QCheckBox] = {}
        self.phands: Any = None
        layout = self.layout()
        assert layout is not None

        if self.display.get("Heroes", False):
            layout.addWidget(self.create_player_frame())
        if self.display.get("Sites", False):
            layout.addWidget(self.create_sites_frame())
        if self.display.get("Games", False):
            layout.addWidget(self.create_games_frame())
        if self.display.get("Tourney", False):
            layout.addWidget(self.create_tourney_frame())
        if self.display.get("TourneyCat", False):
            layout.addWidget(self.create_tourney_cat_frame())
        if self.display.get("TourneyLim", False):
            layout.addWidget(self.create_tourney_lim_frame())
        if self.display.get("TourneyBuyin", False):
            layout.addWidget(self.create_tourney_buyin_frame())
        if self.display.get("Currencies", False):
            layout.addWidget(self.create_currencies_frame())
        if self.display.get("Limits", False):
            layout.addWidget(self.create_limits_frame())
        if self.display.get("Positions", False):
            layout.addWidget(self.create_positions_frame())
        if self.display.get("GraphOps", False):
            layout.addWidget(self.create_graph_ops_frame())
        if self.display.get("Seats", False):
            layout.addWidget(self.create_seats_frame())
        if self.display.get("Groups", False):
            layout.addWidget(self.create_groups_frame())
        if self.display.get("Dates", False):
            layout.addWidget(self.create_date_frame())
        if self.display.get("Cards", False):
            layout.addWidget(self.create_cards_frame())
        if self.display.get("Button1", False) or self.display.get("Button2", False):
            layout.addWidget(self.create_buttons())

        self.db.rollback()
        self.set_default_hero()

    def _clear_layout(self, layout: Any) -> None:
        """Recursively remove and delete every item from a layout."""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                self._clear_layout(item.layout())

    def rebuild(self) -> None:
        """Rebuild every filter widget from the current database state.

        Called after an import so newly imported games, limits, currencies and
        tournament types appear without reopening the stats tab. Each tab builds
        its Filters panel only once (at creation), so without this the panel keeps
        showing the pre-import database state. Button names/callbacks installed by
        the parent tab are preserved; transient selections (dates, checkboxes,
        hero) reset to defaults, which is the intended behaviour for a refresh.
        """
        saved_callbacks = dict(self.callback)
        button1_text = self.Button1.text() if getattr(self, "Button1", None) else None
        button2_text = self.Button2.text() if getattr(self, "Button2", None) else None

        self._clear_layout(self.layout())

        self.heroList = None
        for name in (
            "cbSites", "cbGames", "cbLimits", "cbPositions", "cbCurrencies",
            "cbGraphops", "cbTourney", "cbTourneyCat", "cbTourneyLim",
            "cbTourneyBuyin", "cbGroups",
        ):
            setattr(self, name, {})
        self.callback = {}

        self.make_filter()

        # Restore the wiring the parent tab installed after construction.
        if button1_text is not None and getattr(self, "Button1", None):
            self.Button1.setText(button1_text)
        if button2_text is not None and getattr(self, "Button2", None):
            self.Button2.setText(button2_text)
        if "button1" in saved_callbacks and getattr(self, "Button1", None):
            self.registerButton1Callback(saved_callbacks["button1"])
        if "button2" in saved_callbacks and getattr(self, "Button2", None):
            self.registerButton2Callback(saved_callbacks["button2"])
        if "cards" in saved_callbacks:
            self.callback["cards"] = saved_callbacks["cards"]

    def set_default_hero(self) -> None:
        """Set the default hero selection to the first available hero."""
        if self.heroList and self.heroList.count() > 0:
            self.heroList.setCurrentIndex(0)
            self.update_filters_for_hero()

    def _create_card_container(self, title: str, fill_func: Any, tooltip: str = "", *args, **kwargs) -> QWidget:
        """Helper to create a container widget with a QLabel title badge and a titleless QGroupBox card."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Title Label styled as badge
        title_label = QLabel(title)
        title_label.setObjectName("filterTitle")
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # Card QGroupBox
        card_box = QGroupBox()
        if tooltip:
            card_box.setToolTip(tooltip)
            title_label.setToolTip(tooltip)

        # Call the fill function to add contents to the card
        fill_func(card_box, *args, **kwargs)

        layout.addWidget(card_box)
        return container

    def create_player_frame(self) -> QWidget:
        """Create the player selection frame."""
        self.leHeroes: dict[str, QLineEdit] = {}
        return self._create_card_container(
            "🎭 " + self.filterText["playerstitle"],
            self.fillPlayerFrame,
            "Select the poker player (hero) to analyze",
            self.display
        )

    def create_sites_frame(self) -> QWidget:
        """Create the sites selection frame."""
        self.cbSites = {}
        return self._create_card_container(
            "🌐 " + self.filterText["sitestitle"],
            self.fillSitesFrame,
            "Filter by poker sites (PokerStars, Winamax, etc.)"
        )

    def create_games_frame(self) -> QWidget:
        """Create the games selection frame."""
        return self._create_card_container(
            "🃏 " + self.filterText["gamestitle"],
            self.fillGamesFrame,
            "Filter by poker game variants (Hold'em, Omaha, Stud, etc.)"
        )

    def create_tourney_frame(self) -> QWidget:
        """Create the tournament type selection frame."""
        self.cbTourney = {}
        return self._create_card_container(
            "🏆 " + self.filterText["tourneytitle"],
            self.fillTourneyTypesFrame,
            "Filter by tournament type (Ring games vs Tournaments)"
        )

    def create_tourney_cat_frame(self) -> QWidget:
        """Create the tournament category selection frame."""
        self.cbTourneyCat = {}
        return self._create_card_container(
            self.filterText["tourneycat"],
            self.fillTourneyCatFrame
        )

    def create_tourney_lim_frame(self) -> QWidget:
        """Create the tournament limit selection frame."""
        self.cbTourneyLim = {}
        return self._create_card_container(
            self.filterText["tourneylim"],
            self.fillTourneyLimFrame
        )

    def create_tourney_buyin_frame(self) -> QWidget:
        """Create the tournament buyin selection frame."""
        self.cbTourneyBuyin = {}
        return self._create_card_container(
            self.filterText["tourneybuyin"],
            self.fillTourneyBuyinFrame
        )

    def create_currencies_frame(self) -> QWidget:
        """Create the currencies selection frame."""
        return self._create_card_container(
            "💱 " + self.filterText["currenciestitle"],
            self.fillCurrenciesFrame,
            "Filter by currency (USD, EUR, Play Money, etc.)"
        )

    def create_limits_frame(self) -> QWidget:
        """Create the limits selection frame."""
        return self._create_card_container(
            "💰 " + self.filterText["limitstitle"],
            self.fillLimitsFrame,
            "Filter by betting limits and stake levels",
            self.display
        )

    def create_positions_frame(self) -> QWidget:
        """Create the positions selection frame."""
        return self._create_card_container(
            "📍 " + self.filterText["positionstitle"],
            self.fillPositionsFrame,
            "Filter by table positions (Button, Small Blind, Big Blind, etc.)",
            self.display
        )

    def create_graph_ops_frame(self) -> QWidget:
        """Create the graph options frame."""
        self.cbGraphops = {}
        return self._create_card_container(
            "Graphing Options:",
            self.fillGraphOpsFrame
        )

    def create_seats_frame(self) -> QWidget:
        """Create the seats selection frame."""
        self.sbSeats: dict[str, QSpinBox] = {}
        return self._create_card_container(
            self.filterText["seatstitle"],
            self.fillSeatsFrame
        )

    def create_groups_frame(self) -> QWidget:
        """Create the groups selection frame."""
        return self._create_card_container(
            self.filterText["groupstitle"],
            self.fillGroupsFrame,
            "",
            self.display
        )

    def create_date_frame(self) -> QWidget:
        """Create the date range selection frame."""
        return self._create_card_container(
            "📅 " + self.filterText["datestitle"],
            self.fillDateFrame,
            "Filter by date range for your poker sessions"
        )

    def create_cards_frame(self) -> QWidget:
        """Create the hole cards selection frame."""
        return self._create_card_container(
            "🎴 " + self.filterText["cardstitle"],
            self.fillHoleCardsFrame,
            "Filter by starting hole cards (AA, AK, etc.)"
        )

    def create_buttons(self) -> QWidget:
        """Create action buttons widget."""
        button_frame = QWidget()
        button_layout = QVBoxLayout(button_frame)
        if self.display.get("Button1", False):
            self.Button1 = QPushButton("Unnamed 1")
            button_layout.addWidget(self.Button1)
        if self.display.get("Button2", False):
            self.Button2 = QPushButton("Unnamed 2")
            button_layout.addWidget(self.Button2)
        return button_frame

    def getNumHands(self) -> int:
        """Get the number of hands filter value."""
        return self.phands.value() if self.phands else 0

    def getNumTourneys(self) -> int:
        """Get the number of tournaments filter value."""
        return 0

    def getGraphOps(self) -> list[str]:
        """Get selected graph options."""
        return [g for g in self.cbGraphops if self.cbGraphops[g].isChecked()]

    def getSites(self) -> list[str]:
        """Get selected sites."""
        return [s for s in self.cbSites if self.cbSites[s].isChecked() and self.cbSites[s].isEnabled()]

    def getPositions(self) -> list[str]:
        """Get selected positions."""
        return [p for p in self.cbPositions if self.cbPositions[p].isChecked() and self.cbPositions[p].isEnabled()]

    def getTourneyCat(self) -> list[str]:
        """Get selected tournament categories."""
        return [g for g in self.cbTourneyCat if self.cbTourneyCat[g].isChecked()]

    def getTourneyLim(self) -> list[str]:
        """Get selected tournament limits."""
        return [g for g in self.cbTourneyLim if self.cbTourneyLim[g].isChecked()]

    def getTourneyBuyin(self) -> list[str]:
        """Get selected tournament buyins."""
        return [g for g in self.cbTourneyBuyin if self.cbTourneyBuyin[g].isChecked()]

    def getTourneyTypes(self) -> list[str]:
        """Get selected tournament types."""
        return [g for g in self.cbTourney if self.cbTourney[g].isChecked()]

    def getGames(self) -> list[str]:
        """Get selected games."""
        return [g for g in self.cbGames if self.cbGames[g].isChecked() and self.cbGames[g].isEnabled()]

    def getCards(self) -> dict[str, Any]:
        """Get selected cards filter."""
        return self.cards

    def getCurrencies(self) -> list[str]:
        """Get selected currencies."""
        return [c for c in self.cbCurrencies if self.cbCurrencies[c].isChecked() and self.cbCurrencies[c].isEnabled()]

    def getSiteIds(self) -> dict[str, int]:
        """Get site IDs mapping."""
        return self.siteid

    def getHeroes(self) -> dict[str, str]:
        """Get selected hero as ``{site: hero}``.

        Returns ``{}`` when a multiroom profile is selected (handled separately
        via :meth:`get_selected_hero_profile`).
        """
        data = self.heroList.currentData() if self.heroList else None
        if isinstance(data, tuple) and data and data[0] == "profile":
            return {}
        if isinstance(data, tuple) and data and data[0] == "site":
            site = data[1]
            hero = ""
            if site in self.conf.supported_sites:
                hero = self.conf.supported_sites[site].screen_name
            return {site: hero}
        if isinstance(data, tuple) and data and data[0] == "site_alias":
            site = data[1]
            hero = data[2]
            return {site: hero}
        # Legacy fallback: parse the display text "name on site".
        if (selected_text := self.heroList.currentText()) and " on " in selected_text:
            hero, _, site = selected_text.partition(" on ")
            return {site: hero}
        return {}

    def get_selected_hero_profile(self):
        """Return the selected multiroom :class:`HeroProfile`, or ``None``."""
        data = self.heroList.currentData() if self.heroList else None
        if isinstance(data, tuple) and data and data[0] == "profile":
            getter = getattr(self.conf, "get_hero_profiles", None)
            if callable(getter):
                return getter().get(data[1])
        return None

    def get_hero_for_site(self, sitename: str, hand: Any = None) -> str | None:
        """Resolve hero name for the given sitename, mapping site variants if needed.

        If a hand object is provided, matches the exact alias that participated in the hand.
        """
        if hand and hasattr(hand, "players") and hand.players:
            # Resolve the base site name first
            site_name = None
            if sitename in self.conf.supported_sites:
                site_name = sitename
            else:
                norm_s = sitename.lower().replace(" ", "").replace(".", "").replace("-", "")
                for site in self.conf.get_supported_sites():
                    norm_parent = site.lower().replace(" ", "").replace(".", "").replace("-", "")
                    if norm_s.startswith(norm_parent) or norm_parent.startswith(norm_s):
                        site_name = site
                        break
            if site_name:
                aliases = self.conf.get_hero_aliases(site_name)
                player_names = {p[1] for p in hand.players if len(p) > 1}
                for alias in aliases:
                    if alias in player_names:
                        return alias

        heroes = self.getHeroes()
        if not heroes:
            return None
        if sitename in heroes:
            return heroes[sitename]
        norm_s = sitename.lower().replace(" ", "").replace(".", "").replace("-", "")
        for site, hero in heroes.items():
            norm_parent = site.lower().replace(" ", "").replace(".", "").replace("-", "")
            if norm_s.startswith(norm_parent) or norm_parent.startswith(norm_s):
                return hero
        if len(heroes) == 1:
            return list(heroes.values())[0]
        return None


    def getLimits(self) -> list[str]:
        """Get selected limits."""
        return [
            limit for limit in self.cbLimits if self.cbLimits[limit].isChecked() and self.cbLimits[limit].isEnabled()
        ]

    def getType(self) -> str | None:
        """Get filter type."""
        return self.type

    def getSeats(self) -> dict[str, Any]:
        """Get seats filter configuration."""
        result = {}
        if "from" in self.sbSeats:
            result["from"] = self.sbSeats["from"].value()
        if "to" in self.sbSeats:
            result["to"] = self.sbSeats["to"].value()
        return result

    def getGroups(self) -> list[str]:
        """Get selected groups."""
        return [g for g in self.cbGroups if self.cbGroups[g].isChecked()]

    def getDates(self) -> tuple[str, str]:
        """Get date range filter."""
        offset = int(self.day_start * 3600)
        t1 = self.start_date.date()
        t2 = self.end_date.date()
        adj_t1 = QDateTime(t1, QTime(0, 0, 0)).addSecs(offset)
        adj_t2 = QDateTime(t2, QTime(0, 0, 0)).addSecs(offset + 24 * 3600 - 1)
        return (
            adj_t1.toUTC().toString("yyyy-MM-dd HH:mm:ss"),
            adj_t2.toUTC().toString("yyyy-MM-dd HH:mm:ss"),
        )

    def fillCardsFrame(self, frame: QGroupBox) -> None:
        """Fill the cards frame with controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        grid = QGridLayout()
        vbox1.addLayout(grid)
        self.createCardsWidget(grid)

        hbox = QHBoxLayout()
        vbox1.addLayout(hbox)
        self.createCardsControls(hbox)

        self.cards = {}
        for i, j in itertools.product(range(2, 15), range(2, 15)):
            for s in ["s", "o"]:
                if i >= j:
                    hand = f"{i}{j}{s}"
                    self.cards[hand] = False

    def registerButton1Name(self, title: str) -> None:
        """Register button 1 name."""
        self.Button1.setText(title)

    def registerButton1Callback(self, callback: Any) -> None:
        """Register button 1 callback."""
        self.Button1.clicked.connect(callback)
        self.Button1.setEnabled(True)
        self.callback["button1"] = callback

    def registerButton2Name(self, title: str) -> None:
        """Register button 2 name."""
        self.Button2.setText(title)

    def registerButton2Callback(self, callback: Any) -> None:
        """Register button 2 callback."""
        self.Button2.clicked.connect(callback)
        self.Button2.setEnabled(True)
        self.callback["button2"] = callback

    def registerCardsCallback(self, callback: Any) -> None:
        """Register cards callback."""
        self.callback["cards"] = callback

    def __set_tourney_type_select(self, *_args: object, checkbox: QCheckBox, tourney_type: str) -> None:
        """Set tourney type selection."""
        self.tourneyTypes[tourney_type] = checkbox.isChecked()
        log.debug(
            "self.tourney_types[%s] set to %s",
            tourney_type,
            self.tourneyTypes[tourney_type],
        )

    def createTourneyTypeLine(self, hbox: QHBoxLayout, tourney_type: str) -> None:
        """Create tournament type line."""
        cb = QCheckBox(str(tourney_type))
        cb.clicked.connect(
            partial(self.__set_tourney_type_select, checkbox=cb, tourney_type=tourney_type),
        )
        hbox.addWidget(cb)
        cb.setChecked(True)

    def createCardsWidget(self, grid: QGridLayout) -> None:
        """Create the cards selection widget."""
        grid.setSpacing(0)
        for i in range(13):
            for j in range(13):
                abbr = Card.card_map_abbr[j][i]
                b = QPushButton("")
                import platform

                if platform.system() == "Darwin":
                    b.setStyleSheet("QPushButton {border-width:0;margin:6;padding:0;}")
                else:
                    b.setStyleSheet("QPushButton {border-width:0;margin:0;padding:0;}")
                b.clicked.connect(
                    partial(self.__toggle_card_select, widget=b, card=abbr),
                )
                self.cards[abbr] = False
                self.__toggle_card_select(widget=b, card=abbr)
                grid.addWidget(b, j, i)

    def createCardsControls(self, hbox: QHBoxLayout) -> None:
        """Create cards control buttons."""
        selections = [_("All"), _("Suited"), _("Off Suit")]
        for s in selections:
            cb = QCheckBox(s)
            cb.clicked.connect(self.__set_cards)
            hbox.addWidget(cb)

    def __card_select_bgcolor(self, card: str, selected: bool) -> str | None:  # noqa: FBT001
        """Get card selection background color."""
        pair_card_length = 2  # Length of pocket pair cards (e.g., "AA", "KK")
        s_on = "red"
        s_off = "orange"
        o_on = "white"
        o_off = "lightgrey"
        p_on = "blue"
        p_off = "lightblue"
        if len(card) == pair_card_length:
            return p_on if selected else p_off
        if card[2] == "s":
            return s_on if selected else s_off
        if card[2] == "o":
            return o_on if selected else o_off
        return None

    def __toggle_card_select(self, *_args: object, widget: QCheckBox, card: str) -> None:
        """Toggle card selection."""
        font = widget.font()
        font.setPointSize(10)
        widget.setFont(font)
        widget.setText(card)
        self.cards[card] = not self.cards[card]
        if "cards" in self.callback:
            self.callback["cards"](card)

    def __set_cards(self, _check_state: bool) -> None:  # noqa: FBT001
        """Set cards selection state."""

    def __set_checkboxes(self, *_args: object, check_boxes: dict[str, QCheckBox], set_state: bool) -> None:
        """Set checkbox states.

        ``*_args`` absorbs the optional ``checked`` bool from the QPushButton.clicked
        signal: PySide6 invokes ``functools.partial`` slots with zero positional args
        (clicked's bool has a default), so the bound ``check_boxes``/``set_state`` must
        be keyword-only to survive being called with no positional arguments.
        """
        for checkbox in list(check_boxes.values()):
            checkbox.setChecked(set_state)

    def __select_limit(self, *_args: object, limit: str) -> None:
        """Select only the limits of the given type (FL/NL/PL/CAP/HP).

        Acts as an exclusive quick-filter next to All/None: check every stake of
        this limit type and uncheck the rest. Setting only the matching boxes to
        True was a no-op because every limit checkbox starts checked.
        """
        for limit_key, checkbox in list(self.cbLimits.items()):
            checkbox.setChecked(limit_key.endswith(limit))

    def fillPlayerFrame(self, frame: QGroupBox, display: dict[str, Any]) -> None:  # noqa: PLR0915, C901, PLR0912
        """Fill the player selection frame with hero selection controls."""
        vbox = QVBoxLayout()
        frame.setLayout(vbox)
        self.heroList = QComboBox()

        for _count, site in enumerate(self.conf.get_supported_sites(), start=1):
            aliases = self.conf.get_hero_aliases(site)
            primary_name = aliases[0] if aliases else self.conf.supported_sites[site].screen_name
            self.leHeroes[site] = QLineEdit(primary_name)

            for alias in aliases:
                self.heroList.addItem(resolve_site_icon(site), f"{alias} on {site}", ("site_alias", site, alias))

        # Multiroom hero profiles (aggregate a player's identity across rooms).
        getter = getattr(self.conf, "get_hero_profiles", None)
        if callable(getter):
            for name in getter():
                self.heroList.addItem(f"[Profile] {name}", ("profile", name))

        vbox.addWidget(self.heroList)
        self.heroList.currentTextChanged.connect(self.update_filters_for_hero)

        if display.get("GroupsAll"):
            hbox = QHBoxLayout()
            vbox.addLayout(hbox)
            self.cbGroups["allplayers"] = QCheckBox(self.filterText["groupsall"])
            hbox.addWidget(self.cbGroups["allplayers"])

            lbl = QLabel(_("Min # Hands:"))
            hbox.addWidget(lbl)

            self.phands = QSpinBox()
            self.phands.setMaximum(int(1e5))
            hbox.addWidget(self.phands)

        refresh_button = QPushButton(_("Refresh Filters"))
        refresh_button.clicked.connect(self.update_filters_for_hero)
        vbox.addWidget(refresh_button)

    def fillSitesFrame(self, frame: QGroupBox) -> None:
        """Fill the sites frame with site selection checkboxes."""
        vbox = QVBoxLayout()
        frame.setLayout(vbox)

        for site in self.conf.get_supported_sites():
            self.cbSites[site] = QCheckBox(site)
            self.cbSites[site].setChecked(True)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            icon_label = QLabel()
            icon_label.setFixedSize(20, 20)
            icon_label.setPixmap(resolve_site_icon(site).pixmap(20, 20))
            row_layout.addWidget(icon_label)
            row_layout.addWidget(self.cbSites[site], 1)
            vbox.addWidget(row)

    def fillTourneyTypesFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament types frame with tournament selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute("SELECT DISTINCT tourneyName FROM Tourneys")
        result = self.db_cursor.fetchall()
        log.debug("Select distint tourney name %s", result)
        self.gameList = QComboBox()
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            if game == "(None,)":
                game = '("None",)'
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            log.debug("game %s", game)
            if game != '"None"':
                self.gameList.insertItem(count, game)
            else:
                self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in result:
                if str(line) == "(None,)":
                    self.cbTourney[line[0]] = QCheckBox("None")
                    self.cbTourney[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourney[line[0]])
                else:
                    self.cbTourney[line[0]] = QCheckBox(line[0])
                    self.cbTourney[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourney[line[0]])

        else:
            log.debug("No games returned from database")

    def fillTourneyCatFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament category frame with category selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute("SELECT DISTINCT category FROM TourneyTypes")
        result = self.db_cursor.fetchall()
        log.debug("show category from tourney %s", result)
        self.gameList = QComboBox()
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            if game == "(None,)":
                game = '("None",)'
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            log.debug(" game %s", game)
            if game != '"None"':
                self.gameList.insertItem(count, game)
            else:
                self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in result:
                if str(line) == "(None,)":
                    self.cbTourneyCat[line[0]] = QCheckBox("None")
                    self.cbTourneyCat[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyCat[line[0]])
                else:
                    self.cbTourneyCat[line[0]] = QCheckBox(line[0])
                    self.cbTourneyCat[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyCat[line[0]])

        else:
            log.debug("No games returned from database")

    def fillTourneyLimFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament limits frame with limit type selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute("SELECT DISTINCT limitType FROM TourneyTypes")
        result = self.db_cursor.fetchall()
        log.debug("show limit from from tourney %s", result)
        self.gameList = QComboBox()
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            if game == "(None,)":
                game = '("None",)'
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            log.debug("game %s", game)
            if game != '"None"':
                self.gameList.insertItem(count, game)
            else:
                self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in result:
                if str(line) == "(None,)":
                    self.cbTourneyLim[line[0]] = QCheckBox("None")
                    self.cbTourneyLim[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyLim[line[0]])
                else:
                    self.cbTourneyLim[line[0]] = QCheckBox(line[0])
                    self.cbTourneyLim[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyLim[line[0]])

        else:
            log.debug("No games returned from database")

    def fillTourneyBuyinFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament buyin frame with buyin selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute("SELECT DISTINCT buyin, fee FROM TourneyTypes")
        result = self.db_cursor.fetchall()

        if len(result) >= 1:
            for _count, (buyin, fee) in enumerate(result):
                if buyin is None and fee is None:
                    display_text = "None"
                    value = "None"
                else:
                    total = (buyin + fee) / 100  # Convert to dollars
                    display_text = f"${total:.2f}"
                    value = f"{buyin},{fee}"

                self.cbTourneyBuyin[value] = QCheckBox(display_text)
                self.cbTourneyBuyin[value].setChecked(True)
                vbox1.addWidget(self.cbTourneyBuyin[value])
        else:
            log.info("No buy-ins returned from database")

    def fillGamesFrame(self, frame: QGroupBox) -> None:
        """Fill the games frame with game variant selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute(self.sql.query["getGames"])
        result = self.db.cursor.fetchall()
        log.debug("get games %s", result)
        self.gameList = QComboBox()
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            game = game.replace("(", "")
            game = game.replace(",", "")
            game = game.replace(")", "")
            log.debug("game %s", game)
            self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in sorted(result, key=lambda game: self.gameName[game[0]]):
                self.cbGames[line[0]] = QCheckBox(self.gameName[line[0]])
                self.cbGames[line[0]].setChecked(True)
                vbox1.addWidget(self.cbGames[line[0]])

            if len(result) >= MIN_ITEMS_FOR_CONTROLS:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["gamesall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbGames,
                        set_state=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["gamesnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbGames,
                        set_state=False,
                    ),
                )
                hbox.addWidget(btn_none)
                hbox.addStretch()
        else:
            log.debug("No games returned from database")

    def fillTourneyFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament frame with tournament selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute(self.sql.query["getTourneyNames"])
        result = self.db.cursor.fetchall()
        log.debug("get tourney name %s", result)
        self.gameList = QComboBox()
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            game = game.replace("(", "")
            game = game.replace(",", "")
            game = game.replace(")", "")
            self.gameList.insertItem(count, game)

    def fillPositionsFrame(self, frame: QGroupBox, _display: dict[str, Any]) -> None:
        """Fill the positions frame with position selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        result: list[list[Any]] = [[0], [1], [2], [3], [4], [5], [6], [7], ["S"], ["B"]]
        res_count = len(result)

        if res_count > 0:
            v_count = 0
            col_count = 4
            hbox: QHBoxLayout | None = None
            for line in result:
                if v_count == 0:
                    hbox = QHBoxLayout()
                    vbox1.addLayout(hbox)

                line_str = str(line[0])
                self.cbPositions[line_str] = QCheckBox(line_str)
                self.cbPositions[line_str].setChecked(True)
                assert hbox is not None
                hbox.addWidget(self.cbPositions[line_str])

                v_count += 1
                if v_count == col_count:
                    v_count = 0

            dif = res_count % col_count
            while dif > 0:
                fillbox = QVBoxLayout()
                assert hbox is not None
                hbox.addLayout(fillbox)
                dif -= 1

            if res_count > 1:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["positionsall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbPositions,
                        set_state=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["positionsnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbPositions,
                        set_state=False,
                    ),
                )
                hbox.addWidget(btn_none)
                hbox.addStretch()
        else:
            log.debug("No positions returned from database")

    def fillHoleCardsFrame(self, frame: QGroupBox) -> None:
        """Fill the hole cards frame with card selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        grid = QGridLayout()
        vbox1.addLayout(grid)
        self.createCardsWidget(grid)

        hbox = QHBoxLayout()
        vbox1.addLayout(hbox)
        self.createCardsControls(hbox)

    def fillCurrenciesFrame(self, frame: QGroupBox) -> None:
        """Fill the currencies frame with currency selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute(self.sql.query["getCurrencies"])
        result = self.db.cursor.fetchall()
        if len(result) >= 1:
            for line in result:
                cname = self.currencyName[line[0]] if line[0] in self.currencyName else line[0]
                self.cbCurrencies[line[0]] = QCheckBox(cname)
                self.cbCurrencies[line[0]].setChecked(True)
                vbox1.addWidget(self.cbCurrencies[line[0]])

            if len(result) >= MIN_ITEMS_FOR_CONTROLS:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["currenciesall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbCurrencies,
                        set_state=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["currenciesnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbCurrencies,
                        set_state=False,
                    ),
                )
                hbox.addWidget(btn_none)
                hbox.addStretch()
            else:
                self.cbCurrencies[line[0]].setChecked(True)
        else:
            log.info("No currencies returned from database")

    def fillLimitsFrame(self, frame: QGroupBox, display: dict[str, Any]) -> None:
        """Fill the limits frame with betting limit selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.db_cursor.execute(self.sql.query["getCashLimits"])
        result = self.db.cursor.fetchall()
        limits_found = set()
        types_found = set()

        if len(result) >= 1:
            hbox = QHBoxLayout()
            vbox1.addLayout(hbox)
            vbox2 = QVBoxLayout()
            hbox.addLayout(vbox2)
            vbox3 = QVBoxLayout()
            hbox.addLayout(vbox3)
            for i, line in enumerate(result):
                if "UseType" in self.display and line[0] != self.display["UseType"]:
                    continue
                hbox = QHBoxLayout()
                if i < (len(result) + 1) // 2:
                    vbox2.addLayout(hbox)
                else:
                    vbox3.addLayout(hbox)
                if True:
                    name = str(line[2]) + line[1]
                    limits_found.add(line[1])
                    self.cbLimits[name] = QCheckBox(name)
                    self.cbLimits[name].setChecked(True)
                    hbox.addWidget(self.cbLimits[name])
                types_found.add(line[0])
                self.type = line[0]
            if "LimitSep" in display and display["LimitSep"] and len(result) >= MIN_ITEMS_FOR_CONTROLS:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["limitsall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbLimits,
                        set_state=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["limitsnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        check_boxes=self.cbLimits,
                        set_state=False,
                    ),
                )
                hbox.addWidget(btn_none)

                if "LimitType" in display and display["LimitType"] and len(limits_found) > 1:
                    for limit in limits_found:
                        btn = QPushButton(self.filterText["limits" + limit.upper()])
                        btn.clicked.connect(partial(self.__select_limit, limit=limit))
                        hbox.addWidget(btn)

                hbox.addStretch()
        else:
            log.debug("No games returned from database")

        if "Type" in display and display["Type"] and "ring" in types_found and "tour" in types_found:
            self.type = "ring"

    def fillGraphOpsFrame(self, frame: QGroupBox) -> None:
        """Fill the graph operations frame with graph option controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        hbox1 = QHBoxLayout()
        vbox1.addLayout(hbox1)

        label = QLabel(_("Show Graph In:"))
        hbox1.addWidget(label)

        self.cbGraphops["$"] = QRadioButton("$$", frame)
        hbox1.addWidget(self.cbGraphops["$"])
        self.cbGraphops["$"].setChecked(True)

        self.cbGraphops["BB"] = QRadioButton("BB", frame)
        hbox1.addWidget(self.cbGraphops["BB"])

        self.cbGraphops["showdown"] = QCheckBox(_("Showdown Winnings"))
        vbox1.addWidget(self.cbGraphops["showdown"])

        self.cbGraphops["nonshowdown"] = QCheckBox(_("Non-Showdown Winnings"))
        vbox1.addWidget(self.cbGraphops["nonshowdown"])

        self.cbGraphops["ev"] = QCheckBox(_("EV"))
        vbox1.addWidget(self.cbGraphops["ev"])

    def fillSeatsFrame(self, frame: QGroupBox) -> None:
        """Fill the seats frame with seat range selection controls."""
        hbox = QHBoxLayout()
        frame.setLayout(hbox)

        lbl_from = QLabel(self.filterText["seatsbetween"])
        lbl_to = QLabel(self.filterText["seatsand"])

        adj1 = QSpinBox()
        adj1.setRange(2, 10)
        adj1.setValue(2)
        adj1.valueChanged.connect(partial(self.__seats_changed, which="from"))

        adj2 = QSpinBox()
        adj2.setRange(2, 10)
        adj2.setValue(10)
        adj2.valueChanged.connect(partial(self.__seats_changed, which="to"))

        hbox.addStretch()
        hbox.addWidget(lbl_from)
        hbox.addWidget(adj1)
        hbox.addWidget(lbl_to)
        hbox.addWidget(adj2)
        hbox.addStretch()

        self.sbSeats["from"] = adj1
        self.sbSeats["to"] = adj2

    def fillGroupsFrame(self, frame: QGroupBox, display: dict[str, Any]) -> None:
        """Fill the groups frame with grouping option controls."""
        vbox = QVBoxLayout()
        frame.setLayout(vbox)

        self.cbGroups["limits"] = QCheckBox(self.filterText["limitsshow"])
        vbox.addWidget(self.cbGroups["limits"])

        self.cbGroups["posn"] = QCheckBox(self.filterText["posnshow"])
        vbox.addWidget(self.cbGroups["posn"])

        if display.get("SeatSep"):
            self.cbGroups["seats"] = QCheckBox(self.filterText["seatsshow"])
            vbox.addWidget(self.cbGroups["seats"])

    def fillDateFrame(self, frame: QGroupBox) -> None:
        """Fill the date frame with date range selection controls."""
        table = QGridLayout()
        frame.setLayout(table)

        lbl_start = QLabel(_("From:"))
        btn_start = QPushButton(_("Cal"))
        btn_start.clicked.connect(
            partial(self.__calendar_dialog, date_edit=self.start_date),
        )
        clr_start = QPushButton(_("Reset"))
        clr_start.clicked.connect(self.__clear_start_date)

        lbl_end = QLabel(_("To:"))
        btn_end = QPushButton(_("Cal"))
        btn_end.clicked.connect(partial(self.__calendar_dialog, date_edit=self.end_date))
        clr_end = QPushButton(_("Reset"))
        clr_end.clicked.connect(self.__clear_end_date)

        table.addWidget(lbl_start, 0, 0)
        table.addWidget(btn_start, 0, 1)
        table.addWidget(self.start_date, 0, 2)
        table.addWidget(clr_start, 0, 3)

        table.addWidget(lbl_end, 1, 0)
        table.addWidget(btn_end, 1, 1)
        table.addWidget(self.end_date, 1, 2)
        table.addWidget(clr_end, 1, 3)

        table.setColumnStretch(0, 1)

    def get_limits_where_clause(self, limits: list[str]) -> str:
        """Generate WHERE clause for limits filtering."""
        limit_suffix_length = 2  # Length of limit type suffix (e.g., "fl", "pl", "nl")
        where = ""
        lims = [
            int(x[0:-limit_suffix_length])
            for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "fl"
        ]
        potlims = [
            int(x[0:-limit_suffix_length])
            for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "pl"
        ]
        nolims = [
            int(x[0:-limit_suffix_length])
            for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "nl"
        ]
        capnolims = [
            int(x[0:-limit_suffix_length])
            for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "cn"
        ]
        hpnolims = [
            int(x[0:-limit_suffix_length])
            for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "hp"
        ]

        where = "AND ( "

        if lims:
            clause = "(gt.limitType = 'fl' and gt.bigBlind in ({}))".format(",".join(map(str, lims)))
        else:
            clause = "(gt.limitType = 'fl' and gt.bigBlind in (-1))"
        where = where + clause
        if potlims:
            clause = "or (gt.limitType = 'pl' and gt.bigBlind in ({}))".format(",".join(map(str, potlims)))
        else:
            clause = "or (gt.limitType = 'pl' and gt.bigBlind in (-1))"
        where = where + clause
        if nolims:
            clause = "or (gt.limitType = 'nl' and gt.bigBlind in ({}))".format(",".join(map(str, nolims)))
        else:
            clause = "or (gt.limitType = 'nl' and gt.bigBlind in (-1))"
        where = where + clause
        if hpnolims:
            clause = "or (gt.limitType = 'hp' and gt.bigBlind in ({}))".format(",".join(map(str, hpnolims)))
        else:
            clause = "or (gt.limitType = 'hp' and gt.bigBlind in (-1))"
        where = where + clause
        if capnolims:
            clause = "or (gt.limitType = 'cp' and gt.bigBlind in ({}))".format(",".join(map(str, capnolims)))
        else:
            clause = "or (gt.limitType = 'cp' and gt.bigBlind in (-1))"
        return where + clause + " )"

    def replace_placeholders_with_filter_values(self, query: str) -> str:
        """Replace query placeholders with actual filter values."""
        if "<game_test>" in query:
            games = self.getGames()
            gametest = f"AND gt.category IN {str(tuple(games)).replace(',)', ')')}" if games else ""
            usetype = self.display.get("UseType")
            if usetype:
                gametest += f" AND gt.type = '{usetype}'"
            query = query.replace("<game_test>", gametest)

        if "<limit_test>" in query:
            limits = self.getLimits()
            limittest = self.get_limits_where_clause(limits) if limits else ""
            query = query.replace("<limit_test>", limittest)

        if "<player_test>" in query:
            profile = self.get_selected_hero_profile()
            if profile is not None and hasattr(self.db, "get_hero_player_ids"):
                hero_ids = self.db.get_hero_player_ids(profile=profile)
            else:
                heroes = self.getHeroes()
                hero_ids = self.get_hero_ids(heroes) if heroes else []
            if hero_ids:
                player_test = f"AND hp.playerId IN ({','.join(map(str, hero_ids))})"
            else:
                player_test = ""
            query = query.replace("<player_test>", player_test)

        if "<position_test>" in query:
            positions = self.getPositions()
            if positions:
                formatted_positions = [f"'{position}'" for position in positions]
                positiontest = f"AND hp.position IN ({','.join(formatted_positions)})"
            else:
                positiontest = ""
            query = query.replace("<position_test>", positiontest)

        return query

    def get_hero_ids(self, heroes: dict[str, str]) -> list[int]:
        """Get hero IDs for the selected site(s).

        All hero aliases configured for a site (nickname changes, multiple
        accounts) are aggregated so reports cover the player's whole history on
        that room. Falls back to exact name resolution if alias resolution
        yields nothing (e.g. the hero hasn't been imported yet).
        """
        hero_ids: list[int] = []
        seen: set[int] = set()
        resolver = getattr(self.db, "get_hero_player_ids", None)
        if callable(resolver):
            for site in heroes:
                for pid in resolver(site):
                    if pid not in seen:
                        seen.add(pid)
                        hero_ids.append(int(pid))

        if not hero_ids:
            for site, hero in heroes.items():
                result = self.db.get_player_id(self.conf, site, hero)
                if result is not None and int(result) not in seen:
                    seen.add(int(result))
                    hero_ids.append(int(result))
        return hero_ids

    def __calendar_dialog(self, *_args: object, date_edit: QDateEdit) -> None:
        """Open calendar dialog for date selection."""
        d = QDialog()
        d.setWindowTitle(_("Pick a date"))

        vb = QVBoxLayout()
        d.setLayout(vb)
        cal = QCalendarWidget()
        vb.addWidget(cal)

        btn = QPushButton(_("Done"))
        btn.clicked.connect(
            partial(self.__get_date, dlg=d, calendar=cal, date_edit=date_edit),
        )
        vb.addWidget(btn)
        d.exec()

    def __clear_start_date(self, _check_state: Any) -> None:
        """Clear start date filter."""
        self.start_date.setDate(QDate(1970, 1, 1))

    def __clear_end_date(self, _check_state: Any) -> None:
        """Clear end date filter."""
        self.end_date.setDate(QDate(2100, 1, 1))

    def __get_date(self, *_args: object, dlg: QDialog, calendar: QCalendarWidget, date_edit: QDateEdit) -> None:
        """Handle date selection from calendar."""
        new_date = calendar.selectedDate()
        date_edit.setDate(new_date)

        if date_edit == self.start_date:
            end = self.end_date.date()
            if new_date > end:
                self.end_date.setDate(new_date)
        else:
            start = self.start_date.date()
            if new_date < start:
                self.start_date.setDate(new_date)
        dlg.accept()

    def __seats_changed(self, _value: int, which: str) -> None:
        """Handle seats value change."""
        seats_from = self.sbSeats["from"].value()
        seats_to = self.sbSeats["to"].value()
        if seats_from > seats_to:
            if which == "from":
                self.sbSeats["to"].setValue(seats_from)
            else:
                self.sbSeats["from"].setValue(seats_to)

    def setGames(self, games: list[str]) -> None:
        """Set games filter."""
        self.games = games

    def update_filters_for_hero(self) -> None:
        """Update all filters when hero selection changes."""
        if self.heroList and self.heroList.count() > 0:
            selected_text = self.heroList.currentText()
            if " on " in selected_text:
                selected_hero, selected_site = selected_text.split(" on ")
                self.update_sites_for_hero(selected_hero, selected_site)
                self.update_games_for_hero(selected_hero, selected_site)
                self.update_limits_for_hero(selected_hero, selected_site)
                self.update_positions_for_hero(selected_hero, selected_site)
                self.update_currencies_for_hero(selected_hero, selected_site)
                self.update_tourney_filters_for_hero(selected_hero, selected_site)

    def update_sites_for_hero(self, _hero: str, site: str) -> None:
        """Update sites filter for selected hero and site."""
        # Prefer the hero's own site checkbox when it exists. Prefix matching is
        # only a fallback for when the hero plays a skin that has no checkbox of
        # its own (e.g. data under "PokerStars.FR" but only "PokerStars" enabled).
        # Without the exact-match shortcut, selecting "jeje_sat on PokerStars.FR"
        # matched the "PokerStars" checkbox first (".FR" startswith "PokerStars"),
        # checking the wrong site so getSites() no longer matched the hero's key.
        if site in self.cbSites:
            parent_site = site
        else:
            parent_site = site
            norm_s = site.lower().replace(" ", "").replace(".", "").replace("-", "")
            for s in self.cbSites:
                norm_parent = s.lower().replace(" ", "").replace(".", "").replace("-", "")
                if norm_s.startswith(norm_parent) or norm_parent.startswith(norm_s):
                    parent_site = s
                    break

        for s, checkbox in self.cbSites.items():
            is_match = (s == parent_site)
            checkbox.setChecked(is_match)
            checkbox.setEnabled(is_match)
            # Hide the whole row (site icon + checkbox), not just the checkbox —
            # otherwise the icons of inactive rooms keep showing. The checkbox is
            # parented to the row QWidget built in fillSitesFrame.
            (checkbox.parentWidget() or checkbox).setVisible(is_match)

    def get_actual_site_id(self, site: str, hero: str) -> int:
        """Resolve the actual site ID for the hero, mapping site variants if needed."""
        player_id = self.db.get_player_id(self.conf, site, hero)
        if player_id is not None:
            actual_site_id = self.db.get_player_site_id(int(player_id))
            if actual_site_id is not None:
                return actual_site_id
        return self.siteid[site]

    def update_games_for_hero(self, hero: str, site: str) -> None:
        """Update games filter for selected hero and site."""
        site_id = self.get_actual_site_id(site, hero)
        usetype = self.display.get("UseType", "")
        log.debug("Game type for hero %s on site %s: %s", hero, site, usetype)

        pids = self.db.get_hero_player_ids(site)
        if not pids:
            pid = self.db.get_player_id(self.conf, site, hero)
            pids = [int(pid)] if pid is not None else []

        if pids:
            marks = ",".join(["?"] * len(pids))
            if usetype == "tour":
                query = f"""
                SELECT DISTINCT gt.category
                FROM GameTypes gt
                JOIN Hands h ON gt.id = h.gametypeId
                JOIN HandsPlayers hp ON h.id = hp.handId
                WHERE gt.siteId = ? AND hp.playerId IN ({marks}) AND gt.type = 'tour'
                """
            else:
                query = f"""
                SELECT DISTINCT gt.category
                FROM GameTypes gt
                JOIN Hands h ON gt.id = h.gametypeId
                JOIN HandsPlayers hp ON h.id = hp.handId
                WHERE gt.siteId = ? AND hp.playerId IN ({marks}) AND gt.type = 'ring'
                """
            ph = self.db.sql.query.get("placeholder", "%s")
            query = query.replace("?", ph)
            self.db_cursor.execute(query, tuple([site_id, *pids]))
        else:
            self.db_cursor.execute("SELECT 1 WHERE 1=2")

        games = [row[0] for row in self.db_cursor.fetchall()]
        log.debug("Available games for hero %s on site %s: %s", hero, site, games)

        for game, checkbox in self.cbGames.items():
            allowed = game in games
            checkbox.setChecked(allowed)
            checkbox.setEnabled(allowed)
            checkbox.setVisible(allowed)

        # update
        self.games = games

    def update_limits_for_hero(self, _hero: str, site: str) -> None:
        """Update limits filter for selected hero and site."""
        site_id = self.get_actual_site_id(site, _hero)
        query = self.sql.query["getCashLimits"].replace("%s", str(site_id))
        self.db_cursor.execute(query)
        limits = [f"{row[2]}{row[1]}" for row in self.db_cursor.fetchall()]
        for limit, checkbox in self.cbLimits.items():
            allowed = limit in limits
            checkbox.setChecked(allowed)
            checkbox.setEnabled(allowed)
            checkbox.setVisible(allowed)

    def update_positions_for_hero(self, hero: str, site: str) -> None:
        """Update positions filter for selected hero and site."""
        site_id = self.get_actual_site_id(site, hero)
        pids = self.db.get_hero_player_ids(site)
        if not pids:
            pid = self.db.get_player_id(self.conf, site, hero)
            pids = [int(pid)] if pid is not None else []

        if pids:
            marks = ",".join(["?"] * len(pids))
            # Filter by the actual site via Gametypes.siteId. The previous query used
            # "h.siteHandNo LIKE '{site_id}%'", but siteHandNo is the poker room's hand
            # number (e.g. 35839231732), not prefixed by the internal site_id. That
            # matched a random subset of hands, so the positions filter ended up
            # missing positions the hero actually played (e.g. 'B'), silently hiding
            # whole variants (Courchevel hands are all in the big blind).
            query = f"""
            SELECT DISTINCT hp.position
            FROM HandsPlayers hp
            JOIN Hands h ON hp.handId = h.id
            JOIN Gametypes gt ON h.gametypeId = gt.id
            WHERE hp.playerId IN ({marks}) AND gt.siteId = ?
            """
            ph = self.db.sql.query.get("placeholder", "%s")
            query = query.replace("?", ph)
            self.db_cursor.execute(query, tuple([*pids, site_id]))
        else:
            self.db_cursor.execute("SELECT 1 WHERE 1=2")
        positions = [str(row[0]) for row in self.db_cursor.fetchall()]
        for position, checkbox in self.cbPositions.items():
            allowed = position in positions
            checkbox.setChecked(allowed)
            checkbox.setEnabled(allowed)
            checkbox.setVisible(allowed)

    def getBuyIn(self) -> list[int]:
        """Get selected tournament buyins."""
        selected_buyins = []
        for value, checkbox in self.cbTourneyBuyin.items():
            if checkbox.isChecked() and value != "None":
                buyin, fee = map(int, value.split(","))
                total = buyin + fee
                selected_buyins.append(total)
        return selected_buyins

    def update_tourney_filters_for_hero(self, hero: str, site: str) -> None:
        """Update tournament filters for the selected hero and site."""
        if not (self.cbTourneyCat or self.cbTourneyLim or self.cbTourneyBuyin or self.cbTourney):
            return

        site_id = self.get_actual_site_id(site, hero)
        pids = self.db.get_hero_player_ids(site)
        if not pids:
            pid = self.db.get_player_id(self.conf, site, hero)
            pids = [int(pid)] if pid is not None else []
        if not pids:
            return

        marks = ",".join(["?"] * len(pids))
        query = f"""
            SELECT DISTINCT t.tourneyName, tt.category, tt.limitType, tt.buyin, tt.fee
            FROM TourneysPlayers tp
            JOIN Tourneys t ON t.id = tp.tourneyId
            JOIN TourneyTypes tt ON tt.id = t.tourneyTypeId
            WHERE tp.playerId IN ({marks})
              AND tt.siteId = ?
            """
        ph = self.db.sql.query.get("placeholder", "%s")
        query = query.replace("?", ph)
        self.db_cursor.execute(
            query,
            tuple([*pids, site_id]),
        )
        rows = self.db_cursor.fetchall()
        names = {row[0] for row in rows}
        categories = {row[1] for row in rows}
        limits = {row[2] for row in rows}
        buyins = {f"{row[3]},{row[4]}" for row in rows if row[3] is not None and row[4] is not None}

        self._update_checkbox_set(self.cbTourney, names)
        self._update_checkbox_set(self.cbTourneyCat, categories)
        self._update_checkbox_set(self.cbTourneyLim, limits)
        self._update_checkbox_set(self.cbTourneyBuyin, buyins)

    def _update_checkbox_set(self, checkboxes: dict[Any, QCheckBox], allowed_values: set[Any]) -> None:
        if not checkboxes:
            return
        for value, checkbox in checkboxes.items():
            enabled = value in allowed_values
            checkbox.setChecked(enabled)
            checkbox.setEnabled(enabled)
            # Hide values the hero never played in this room rather than leaving
            # them greyed out — otherwise every buy-in/category in the database
            # clutters the list for a single player/site.
            checkbox.setVisible(enabled)

    def update_currencies_for_hero(self, hero: str, site: str) -> None:
        """Update currencies filter for selected hero and site."""
        site_id = self.get_actual_site_id(site, hero)
        # debug
        log.debug("executed request for %s on %s (site_id: %s)", hero, site, site_id)
        pids = self.db.get_hero_player_ids(site)
        if not pids:
            pid = self.db.get_player_id(self.conf, site, hero)
            pids = [int(pid)] if pid is not None else []

        if pids:
            marks = ",".join(["?"] * len(pids))
            query = f"""
            SELECT DISTINCT gt.currency
            FROM GameTypes gt
            JOIN Hands h ON gt.id = h.gametypeId
            JOIN HandsPlayers hp ON h.id = hp.handId
            WHERE gt.siteId = ? AND hp.playerId IN ({marks})
            """
            ph = self.db.sql.query.get("placeholder", "%s")
            query = query.replace("?", ph)
            self.db_cursor.execute(query, tuple([site_id, *pids]))
        else:
            self.db_cursor.execute("SELECT 1 WHERE 1=2")
        currencies = [row[0] for row in self.db_cursor.fetchall()]
        # debug
        log.debug("currencies found for %s on %s: %s", hero, site, currencies)

        for currency, checkbox in self.cbCurrencies.items():
            allowed = currency in currencies
            # manage tour 'T$' on 'ring'
            if currency == "T$" and self.getType() == "ring":
                allowed = False
            checkbox.setChecked(allowed)
            checkbox.setEnabled(allowed)
            checkbox.setVisible(allowed)
            # debug
            log.debug(
                "Devise %s - Checked: %s, Activated: %s on %s",
                currency,
                checkbox.isChecked(),
                checkbox.isEnabled(),
                site,
            )


if __name__ == "__main__":
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)

    qdict = SQL.Sql(db_server="sqlite")

    filters_display = {
        "Heroes": False,
        "Sites": False,
        "Games": False,
        "Cards": True,
        "Currencies": True,
        "Limits": True,
        "LimitSep": False,
        "LimitType": False,
        "Type": False,
        "UseType": "ring",
        "Seats": False,
        "SeatSep": False,
        "Dates": False,
        "GraphOps": False,
        "Groups": False,
        "Button1": False,
        "Button2": False,
    }

    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication([])
    i = Filters(db, display=filters_display)
    main_window = QMainWindow()
    main_window.setCentralWidget(i)
    main_window.show()
    app.exec()
