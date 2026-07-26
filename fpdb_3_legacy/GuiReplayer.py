#!/usr/bin/env python
from __future__ import annotations

# Copyright 2010-2011 Maxime Grandchamp
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
# Note that this now contains the replayer only! The list of hands has been moved to GuiHandViewer by zarturo.
import copy
import itertools
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from math import cos, hypot, pi, sin
from typing import Any

import defusedxml.minidom
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import SQL, Card, Configuration, Database, Deck, Hand
from fpdb_3_legacy.equity import EquityUnavailableError, calculate_equity
from fpdb_3_legacy.http_capture_ofc import OFCHand, build_ofc_hand, load_ofc_hand
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_number
from fpdb_3_legacy.loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()


log = get_logger("gui_replayer")

CARD_HEIGHT = 90
CARD_WIDTH = 70
PLAYER_PANEL_WIDTH = 184
PLAYER_PANEL_HEIGHT = 50
CONTROL_RESERVED_HEIGHT = 175
HEADER_HEIGHT = 92
TIMELINE_WIDTH = 280
TIMELINE_MIN_WINDOW_WIDTH = 1500
TABLE_MARGIN = 28
CARD_SPACING_RATIO = 0.52
MAX_VISIBLE_HOLE_CARDS = 7
MIN_CARD_SCALE = 0.58
CONTROL_BUTTON_MIN_WIDTH = 118
DEALER_BUTTON_BASE_SIZE = 32

_RANK_VALUE = {r: i for i, r in enumerate("23456789TJQKA", start=2)}


def _is_real_card(card: str) -> bool:
    return bool(card) and card not in {"0", "0x"} and len(card) == 2 and card[0] in _RANK_VALUE


def format_replay_amount(value: Decimal | int | float, currency: str) -> str:
    """Format real money with its currency and tournament/play chips as numbers."""
    if currency in {"", "T$", "play"}:
        return format_number(value)
    return format_currency(value, currency)


def replay_hero_equity(frame, hero_name: str, game: str, *, backend=None, iterations: int = 20_000) -> Decimal | None:
    """Return hero equity for a replay frame when every live pocket is known."""
    active_players = [player for player in frame.players if player.action != "folds"]
    if len(active_players) < 2:
        return None
    pockets: list[list[str]] = []
    hero_index = None
    for player in active_players:
        cards = list(player.holecards or [])
        if not cards or not all(_is_real_card(card) for card in cards):
            return None
        if player.name == hero_name:
            hero_index = len(pockets)
        pockets.append(cards)
    if hero_index is None:
        return None

    board: list[str] = []
    visible_streets = set(frame.render_board or ())
    for street in ("FLOP", "TURN", "RIVER"):
        if street in visible_streets:
            board.extend(card for card in (frame.board.get(street) or []) if _is_real_card(card))
    try:
        result = calculate_equity(game, pockets, board, iterations=iterations, backend=backend)
    except (EquityUnavailableError, RuntimeError, ValueError):
        return None
    return result.players[hero_index].equity


def _rank_five(cards: list[str]) -> tuple:
    """Return a comparable strength tuple for exactly five cards (high hand)."""
    values = sorted((_RANK_VALUE[c[0]] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    counts = Counter(values)
    # (count, value) sorted so pairs/trips lead, then kickers by value.
    by_count = sorted(values, key=lambda v: (counts[v], v), reverse=True)
    is_flush = len(set(suits)) == 1
    distinct = sorted(set(values), reverse=True)
    straight_high = 0
    if {14, 5, 4, 3, 2}.issubset(set(values)):
        straight_high = 5  # wheel
    for i in range(len(distinct) - 4 + 1):
        window = distinct[i : i + 5]
        if len(window) == 5 and window[0] - window[4] == 4:
            straight_high = max(straight_high, window[0])
            break
    count_sig = sorted(counts.values(), reverse=True)
    if is_flush and straight_high:
        category = 8
    elif count_sig == [4, 1]:
        category = 7
    elif count_sig == [3, 2]:
        category = 6
    elif is_flush:
        category = 5
    elif straight_high:
        category = 4
    elif count_sig == [3, 1, 1]:
        category = 3
    elif count_sig == [2, 2, 1]:
        category = 2
    elif count_sig == [2, 1, 1, 1]:
        category = 1
    else:
        category = 0
    if category in (4, 8):
        return (category, [straight_high])
    return (category, by_count)


def best_hand(holecards: list[str], board: list[str], base: str, category: str):
    """Return (rank_tuple, frozenset_of_cards) for the best high hand, or
    (None, frozenset()) when it cannot be resolved.

    Respects the game rules: Omaha-style games must use exactly two hole cards
    and three board cards; flop games (hold'em) use any five of hole+board;
    stud/draw use the best five hole cards.
    """
    hole = [c for c in holecards if _is_real_card(c)]
    board = [c for c in board if _is_real_card(c)]
    cat = (category or "").lower()
    omaha_like = any(k in cat for k in ("omaha", "cour", "fusion", "irish"))

    best: tuple[tuple, frozenset[str]] | None = None
    if base == "hold" and omaha_like:
        if len(hole) < 2 or len(board) < 3:
            return (None, frozenset())
        for h2 in itertools.combinations(hole, 2):
            for b3 in itertools.combinations(board, 3):
                five = list(h2) + list(b3)
                rank = _rank_five(five)
                if best is None or rank > best[0]:
                    best = (rank, frozenset(five))
    elif base == "hold":
        pool: list[str] = hole + board
        if len(pool) < 5:
            return (None, frozenset())
        for five_cards in itertools.combinations(pool, 5):
            rank = _rank_five(list(five_cards))
            if best is None or rank > best[0]:
                best = (rank, frozenset(five_cards))
    else:  # stud / draw: hole cards only
        pool = hole
        if len(pool) < 5:
            return (None, frozenset(pool))
        for five_cards in itertools.combinations(pool, 5):
            rank = _rank_five(list(five_cards))
            if best is None or rank > best[0]:
                best = (rank, frozenset(five_cards))
    return best if best else (None, frozenset())


def best_hand_cards(holecards: list[str], board: list[str], base: str, category: str) -> frozenset:
    """Return only the cards forming the best high hand (see ``best_hand``)."""
    return best_hand(holecards, board, base, category)[1]


_CATEGORY_NAMES = {
    8: "Straight Flush",
    7: "Four of a Kind",
    6: "Full House",
    5: "Flush",
    4: "Straight",
    3: "Three of a Kind",
    2: "Two Pair",
    1: "Pair",
    0: "High Card",
}


def hand_category_name(rank) -> str:
    """Human-readable name for a rank tuple returned by ``best_hand``."""
    if not rank:
        return ""
    return _CATEGORY_NAMES.get(rank[0], "")


# Distinct outline colours per run (run 1, 2, 3) for run-it-twice/three boards:
# run 1 = yellow, run 2 = violet, run 3 = blue.
RUN_COLORS = ("#ffd34d", "#c08bff", "#4dd2ff")


@dataclass(frozen=True)
class SeatAnchor:
    """Seat location normalized around the table ellipse."""

    x: float
    y: float


@dataclass
class SeatLayout:
    seat: int
    center: QPointF
    cards_rect: QRectF
    panel_rect: QRectF
    bet_rect: QRectF
    dealer_pos: QPointF


@dataclass
class ReplayLayout:
    table_rect: QRectF
    board_rect: QRectF
    pot_rect: QRectF
    timeline_rect: QRectF
    card_width: int
    card_height: int
    card_spacing: float
    seats: dict[str, SeatLayout] = field(default_factory=dict)


@dataclass
class ReplayPlayer:
    name: str
    seat: int
    stack: Decimal
    chips: Decimal
    action: str | None
    justacted: bool
    holecards: list[str]
    allin: bool = False
    # Showdown info (only populated on the final frame).
    combination: str | None = None
    winning_cards: frozenset[str] = field(default_factory=frozenset)
    is_winner: bool = False
    cashout: Decimal | None = None
    # Draw games: cards discarded on the frame the player just drew (the actual
    # cards for the hero, otherwise an empty list with discard_count set).
    discard_count: int = 0
    discard_cards: list[str] = field(default_factory=list)
    # Run-it-twice/three: hole card -> list of run outline colours (one per run
    # whose winning combination this card is part of).
    hole_run_colors: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ReplayFrame:
    street: str | None
    board: dict[str, list[str]]
    render_board: set[str]
    pot: Decimal
    players: list[ReplayPlayer]
    pots: list[tuple[str, Decimal]] = field(default_factory=list)
    # Run-it boards: one dict per run with color/board_highlight/winner/combo.
    runs: list[dict[str, Any]] = field(default_factory=list)
    # ``double`` reveals parallel boards street-by-street; ``run`` reveals
    # sequential runouts. Both reuse the same Boards storage representation.
    board_mode: str = "single"
    # Game category (e.g. "cour_hi"); used to expose the Courchevel flopet pre-flop.
    category: str = ""


@dataclass
class ReplayModel:
    hand: Any
    info: str
    states: list[Any]
    seen_streets: set[str]


def replay_street_groups(hand: Any) -> list[tuple[str, ...]]:
    """Return replay phases, grouping bomb-pot boards by poker street.

    Database reconstruction represents every multiboard hand as numbered
    streets. A true RIT is sequential (run 1, then run 2), while a double-board
    bomb pot deals both flops, both turns and both rivers in parallel.
    """
    streets = list(getattr(hand, "allStreets", []) or [])
    if not getattr(hand, "bombPot", 0):
        return [(street,) for street in streets]
    numbered = {street for street in streets if street in GuiReplayer._RUN_IT_STREETS}
    if not numbered:
        return [(street,) for street in streets]
    first = min(streets.index(street) for street in numbered)
    prefix = [(street,) for street in streets[:first] if street not in numbered]
    groups = [
        tuple(f"{phase}{run}" for run in (1, 2, 3) if f"{phase}{run}" in numbered)
        for phase in ("FLOP", "TURN", "RIVER")
    ]
    suffix = [(street,) for street in streets[first:] if street not in numbered]
    return prefix + [group for group in groups if group] + suffix


def replay_button_streets(hand: Any) -> list[str]:
    """Return navigation phases matching the replay model's visible states."""
    groups = replay_street_groups(hand)[1:]
    if not getattr(hand, "bombPot", 0):
        return [group[0] for group in groups]
    return [group[0].rstrip("123") if len(group) > 1 else group[0] for group in groups]


@dataclass
class OFCReplayState:
    round_index: int
    phase: str
    rounds: list
    current_round: dict | None
    visible_rows: dict[str, dict[str, list[str]]]
    actor: str | None = None
    pending_cards: list[str] = field(default_factory=list)
    placed_cards: list[str] = field(default_factory=list)
    discarded_cards: list[str] = field(default_factory=list)
    private_pending: bool = True


def hidden_card_count(category: str, known_cards: list[str] | None = None) -> int:
    """Return the number of card backs to show for a hidden hand."""
    normalized = (category or "").lower()
    if normalized in {"holdem", "fusion", "6_holdem"}:
        return 2
    if normalized == "2_holdem":
        return 3
    if normalized in {"omahahi", "omahahilo", "irish"}:
        return 4
    if normalized in {"5_omahahi", "5_omaha8", "cour_hi", "cour_hilo"}:
        return 5
    if normalized == "6_omahahi":
        return 6
    return max(0, len(known_cards or []))


def visible_hole_card_count(category: str, street: str | None, final_frame: bool = False) -> int:
    """Return how many player cards belong on screen at this replay street."""
    normalized = (category or "").lower()
    normalized_street = (street or "").upper()
    if normalized == "fusion":
        if final_frame:
            return 4
        if normalized_street in {"FLOP"}:
            return 3
        if normalized_street in {"TURN", "RIVER"}:
            return 4
        return 2

    # Check Card.games to see base game type
    game_def = Card.games.get(normalized)
    if game_def:
        base = game_def[0]
        if base == "stud":
            street_dict = game_def[3]
            if normalized_street in street_dict:
                idx = street_dict[normalized_street]
                rng = game_def[5][idx]
                return rng[1] - rng[0]
            else:
                if normalized == "5_studhi":
                    return 5 if final_frame else 2
                return 7 if final_frame else 3
        elif base == "draw":
            street_dict = game_def[3]
            if normalized_street in street_dict:
                idx = street_dict[normalized_street]
                rng = game_def[5][idx]
                return rng[1] - rng[0]
            else:
                if normalized == "badugi":
                    return 4
                return 5

    if final_frame:
        return hidden_card_count(normalized)
    return hidden_card_count(normalized)


def action_colors(action: str | None, highlighted: bool = False) -> tuple[QColor, QColor, QColor]:
    """Return panel, border and accent colors for a player/action state."""
    normalized = (action or "").lower()
    if normalized == "folds":
        return QColor("#2a2226"), QColor("#ff6f79"), QColor("#ff6f79")
    if normalized in {"bets", "raises"}:
        return QColor("#202735"), QColor("#d45aff"), QColor("#ffe769")
    if normalized in {"calls", "checks"}:
        return QColor("#17252a"), QColor("#58d68d"), QColor("#9ee8b6")
    if normalized == "collected":
        return QColor("#1d2b21"), QColor("#ffd84a"), QColor("#ffe769")
    if "blind" in normalized or normalized in {"ante", "both", "bringin"}:
        return QColor("#202735"), QColor("#6aa9ff"), QColor("#a9d1ff")
    if highlighted:
        return QColor("#202735"), QColor("#d45aff"), QColor("#ffe769")
    return QColor("#1c252b"), QColor("#5c6870"), QColor("#9aa5ad")


def seat_anchors(player_count: int) -> list[SeatAnchor]:
    """Return clockwise anchors with seat zero at the hero/bottom position."""
    if player_count <= 0:
        return []
    if player_count == 1:
        return [SeatAnchor(0.0, 1.0)]
    anchors = []
    for index in range(player_count):
        angle = pi / 2 + (2 * pi * index / player_count)
        anchors.append(SeatAnchor(cos(angle), sin(angle)))
    return anchors


def build_replay_layout(
    width: int,
    height: int,
    player_names: list[str],
    hero_name: str | None = None,
    category: str = "",
) -> ReplayLayout:
    """Compute a responsive table layout independent from the old fixed pixels."""
    usable_bottom = height - CONTROL_RESERVED_HEIGHT
    has_timeline = width >= TIMELINE_MIN_WINDOW_WIDTH
    timeline_width = min(340, max(260, int(width * 0.16))) if has_timeline else 0
    right_reserved = timeline_width + TABLE_MARGIN * 2 if has_timeline else TABLE_MARGIN
    table_area_width = max(360, width - TABLE_MARGIN - right_reserved)
    table_area_height = max(300, usable_bottom - HEADER_HEIGHT - TABLE_MARGIN)

    table_width = min(table_area_width * 0.72, table_area_height * 1.62)
    table_width = max(420, table_width)
    table_height = table_width * 0.55
    if table_height > table_area_height:
        table_height = table_area_height
        table_width = table_height / 0.55

    table_x = TABLE_MARGIN + (table_area_width - table_width) / 2
    table_y = HEADER_HEIGHT + (table_area_height - table_height) / 2
    table_rect = QRectF(table_x, table_y, table_width, table_height)

    card_scale = max(MIN_CARD_SCALE, min(1.0, table_width / 880, table_area_height / 520))
    card_width = int(CARD_WIDTH * card_scale)
    card_height = int(CARD_HEIGHT * card_scale)
    card_spacing = card_width * CARD_SPACING_RATIO

    board_width = min(card_width * 5 + 20, table_width * 0.46)
    board_rect = QRectF(
        table_rect.center().x() - board_width / 2,
        table_rect.center().y() - card_height / 2 - table_rect.height() * 0.04,
        board_width,
        card_height,
    )
    pot_rect = QRectF(
        table_rect.center().x() - 80,
        board_rect.y() + board_rect.height() + 18,
        160,
        28,
    )
    timeline_rect = QRectF(
        width - timeline_width - 16,
        HEADER_HEIGHT,
        timeline_width,
        max(180, usable_bottom - HEADER_HEIGHT - 18),
    )
    if not has_timeline:
        timeline_rect = QRectF()

    ordered_names = list(player_names)
    if hero_name in ordered_names:
        hero_index = ordered_names.index(hero_name)
        ordered_names = ordered_names[hero_index:] + ordered_names[:hero_index]

    seats = {}
    rx = table_rect.width() * 0.56
    ry = table_rect.height() * 0.62

    panel_w = max(130, int(PLAYER_PANEL_WIDTH * card_scale))
    panel_h = max(38, int(PLAYER_PANEL_HEIGHT * card_scale))

    num_cards = hidden_card_count(category) if category else 4
    num_cards = max(2, num_cards)
    card_w = card_width + (num_cards - 1) * card_spacing
    card_h = card_height

    panel_offset_y = int(24 * card_scale)

    for index, name in enumerate(ordered_names):
        anchor = seat_anchors(len(ordered_names))[index]
        center = QPointF(
            table_rect.center().x() + anchor.x * rx,
            table_rect.center().y() + anchor.y * ry,
        )
        panel_rect = QRectF(center.x() - panel_w / 2, center.y() + panel_offset_y, panel_w, panel_h)
        cards_rect = QRectF(center.x() - card_w / 2, center.y() - card_h / 2, card_w, card_h)
        if anchor.y > 0.6:
            cards_rect.moveTop(center.y() - card_h - int(4 * card_scale))
            panel_rect.moveTop(cards_rect.bottom() + int(6 * card_scale))
        elif anchor.y < -0.6:
            panel_rect.moveTop(center.y() - panel_h - int(36 * card_scale))
            cards_rect.moveTop(panel_rect.bottom() + int(6 * card_scale))
        elif anchor.x > 0:
            panel_rect.moveLeft(center.x() - panel_w * 0.34)
            cards_rect.moveLeft(panel_rect.center().x() - card_w / 2)
            cards_rect.moveTop(panel_rect.y() - card_h - int(6 * card_scale))
        elif anchor.x < 0:
            panel_rect.moveLeft(center.x() - panel_w * 0.66)
            cards_rect.moveLeft(panel_rect.center().x() - card_w / 2)
            cards_rect.moveTop(panel_rect.y() - card_h - int(6 * card_scale))

        panel_rect.moveTop(max(HEADER_HEIGHT + 6, min(panel_rect.y(), usable_bottom - panel_h - 10)))
        cards_rect.moveTop(max(HEADER_HEIGHT + 6, min(cards_rect.y(), usable_bottom - card_h - 16)))
        panel_rect.moveLeft(max(8, min(panel_rect.x(), width - right_reserved - panel_w - 8)))
        cards_rect.moveLeft(max(8, min(cards_rect.x(), width - right_reserved - cards_rect.width() - 8)))
        if panel_rect.intersects(cards_rect):
            if anchor.y > 0.6:
                cards_rect.moveBottom(panel_rect.top() - int(6 * card_scale))
            elif anchor.y < -0.6:
                cards_rect.moveTop(panel_rect.bottom() + int(6 * card_scale))
            else:
                cards_rect.moveBottom(panel_rect.top() - int(6 * card_scale))
        cards_rect.moveTop(max(HEADER_HEIGHT + 6, min(cards_rect.y(), usable_bottom - card_h - 16)))
        cards_rect.moveLeft(panel_rect.center().x() - cards_rect.width() / 2)
        cards_rect.moveLeft(max(8, min(cards_rect.x(), width - right_reserved - cards_rect.width() - 8)))
        panel_rect.moveLeft(cards_rect.center().x() - panel_w / 2)
        panel_rect.moveLeft(max(8, min(panel_rect.x(), width - right_reserved - panel_w - 8)))

        bet_x = table_rect.center().x() + anchor.x * table_rect.width() * 0.26
        bet_y = table_rect.center().y() + anchor.y * table_rect.height() * 0.28
        if abs(anchor.y) < 0.35:
            bet_y += int(24 * card_scale) if index % 2 else int(-24 * card_scale)
        if abs(anchor.x) < 0.35:
            bet_x += int(48 * card_scale) if index % 2 else int(-48 * card_scale)
        if anchor.y > 0.6:
            bet_y = min(bet_y, cards_rect.y() - int(24 * card_scale))
        elif anchor.y < -0.6:
            bet_y = max(bet_y, cards_rect.bottom() + int(24 * card_scale))

        dealer_x = table_rect.center().x() + anchor.x * table_rect.width() * 0.38
        dealer_y = table_rect.center().y() + anchor.y * table_rect.height() * 0.38
        dealer_pos = QPointF(dealer_x, dealer_y)
        dealer_size = int(DEALER_BUTTON_BASE_SIZE * card_scale)
        dealer_rect = QRectF(
            dealer_pos.x() - dealer_size / 2,
            dealer_pos.y() - dealer_size / 2,
            dealer_size,
            dealer_size,
        )
        if dealer_rect.intersects(cards_rect.adjusted(-4, -4, 4, 4)):
            shift_x = table_rect.center().x() - dealer_pos.x()
            shift_y = table_rect.center().y() - dealer_pos.y()
            shift_length = max(1.0, hypot(shift_x, shift_y))
            shift_distance = int(42 * card_scale)
            dealer_pos = QPointF(
                dealer_pos.x() + shift_x / shift_length * shift_distance,
                dealer_pos.y() + shift_y / shift_length * shift_distance,
            )

        bet_w = int(88 * card_scale)
        bet_h = int(26 * card_scale)
        seats[name] = SeatLayout(
            seat=index,
            center=center,
            cards_rect=cards_rect,
            panel_rect=panel_rect,
            bet_rect=QRectF(bet_x - bet_w / 2, bet_y - bet_h / 2, bet_w, bet_h),
            dealer_pos=dealer_pos,
        )

    return ReplayLayout(
        table_rect=table_rect,
        board_rect=board_rect,
        pot_rect=pot_rect,
        timeline_rect=timeline_rect,
        card_width=card_width,
        card_height=card_height,
        card_spacing=card_spacing,
        seats=seats,
    )


def order_players_clockwise(players: list[ReplayPlayer], hero_name: str | None = None) -> list[ReplayPlayer]:
    """Sort players by physical seat and rotate the hero to the bottom anchor."""
    ordered = sorted(players, key=lambda player: player.seat)
    if hero_name:
        for index, player in enumerate(ordered):
            if player.name == hero_name:
                return ordered[index:] + ordered[:index]
    return ordered


class GuiReplayer(QWidget):
    """A Replayer to replay hands."""

    def __init__(self, config, querylist, mainwin, handlist) -> None:
        QWidget.__init__(self, None)
        self.resize(1800, 1080)
        self.setMinimumSize(800, 600)
        self.conf = config
        self.main_window = mainwin
        self.sql = querylist
        self.newpot = Decimal()
        self.db = Database.Database(self.conf, sql=self.sql)
        self.states: list[Any] = []  # List with all table states.
        self.handlist = handlist
        self.handidx = 0
        self.Heroes = ""
        self.setWindowTitle(_("FPDB Hand Replayer"))

        self.replayBox = QVBoxLayout()
        self.replayBox.setContentsMargins(10, 4, 10, 10)
        self.replayBox.setSpacing(4)
        self.setLayout(self.replayBox)

        # Buttons
        self.prevButton = QPushButton(_("Prev"))
        self.prevButton.setToolTip(_("Previous action"))
        self.prevButton.clicked.connect(self.prev_clicked)
        self.prevButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.startButton = QPushButton(_("Start"))
        self.startButton.clicked.connect(self.start_clicked)
        self.startButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.endButton = QPushButton(_("End"))
        self.endButton.clicked.connect(self.end_clicked)
        self.endButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.playPauseButton = QPushButton(_("Play"))
        self.playPauseButton.clicked.connect(self.play_clicked)
        self.playPauseButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.nextButton = QPushButton(_("Next"))
        self.nextButton.setToolTip(_("Next action"))
        self.nextButton.clicked.connect(self.next_clicked)
        self.nextButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Control layouts
        self.playbackBox = QHBoxLayout()
        self.playbackBox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playbackBox.setSpacing(6)
        self.playbackBox.addWidget(self.startButton)
        self.playbackBox.addWidget(self.prevButton)
        self.playbackBox.addWidget(self.playPauseButton)
        self.playbackBox.addWidget(self.nextButton)
        self.playbackBox.addWidget(self.endButton)

        self.buttonBox = QHBoxLayout()
        self.buttonBox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.buttonBox.setSpacing(6)

        self.buttonBox2 = QHBoxLayout()
        self.buttonBox2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.buttonBox2.setSpacing(12)

        self.showCards = QCheckBox(_("Hide Cards"))
        self.showCards.setChecked(True)
        self.buttonBox2.addWidget(self.showCards)

        self.deckLabel = QLabel(_("Deck:"))
        self.deckLabel.setStyleSheet("font-weight: 600; color: #9aa5ad; margin-left: 10px;")
        self.buttonBox2.addWidget(self.deckLabel)

        self.deckType = getattr(getattr(self.conf, "ui", None), "deck_type", "simple") or "simple"
        self.deckTypeCombo = QComboBox()
        self.deckTypeCombo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.deckTypeCombo.setToolTip(_("Card deck"))
        self._populate_deck_selector()
        self.deckTypeCombo.currentTextChanged.connect(self._deck_type_changed)
        self.deckTypeCombo.setMaximumWidth(140)
        self.buttonBox2.addWidget(self.deckTypeCombo)

        self.deckPreview = QLabel()
        self.deckPreview.setObjectName("deckPreviewLabel")
        self.deckPreview.setFixedSize(72, 38)
        self.deckPreview.setToolTip(_("Current card deck preview"))
        self.buttonBox2.addWidget(self.deckPreview)

        self.stateSlider = QSlider(Qt.Orientation.Horizontal)
        self.stateSlider.valueChanged.connect(self.slider_changed)
        self.stateSlider.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.replayBox.addStretch()
        self.replayBox.addWidget(self.stateSlider, False)
        self.replayBox.addLayout(self.playbackBox)
        self.replayBox.addLayout(self.buttonBox)
        self.replayBox.addLayout(self.buttonBox2)

        self.playing = False

        # Fold animation state: {player_name: start_monotonic_time}
        self._fold_anim: dict[str, Any] = {}
        self._discard_anim: dict[str, Any] = {}  # player_name -> start time, for draw discard toss
        self._fold_anim_value = None  # slider value the current anims belong to
        self._fold_timer = QTimer()
        self._fold_timer.timeout.connect(self._fold_tick)

        self.tableImage = None
        self.playerBackdrop = None

        self.cardImages: list[Any] | None = None
        self.deck_inst = Deck.Deck(self.conf, deck_type=self.deckType, height=CARD_HEIGHT, width=CARD_WIDTH)
        self._apply_replayer_style()
        self._update_deck_preview()
        self.show()

    def _ensure_replayer_assets(self) -> None:
        self.cardwidth = CARD_WIDTH
        self.cardheight = CARD_HEIGHT
        if getattr(self, "dealer", None) is None:
            self.dealer = QImage(os.path.join(self.conf.graphics_path, "dealer.png"))
        if self.cardImages is None:
            self.cardImages = [None] * 53
            suits = ("s", "h", "d", "c")
            ranks = (14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2)
            for j in range(13):
                for i in range(4):
                    index = Card.cardFromValueSuit(ranks[j], suits[i])
                    self.cardImages[index] = self.deck_inst.card(suits[i], ranks[j])
            self.cardImages[0] = self.deck_inst.back()

    def _available_deck_types(self) -> list[str]:
        cards_path = os.path.join(self.conf.graphics_path, "cards")
        try:
            decks = [
                name
                for name in sorted(os.listdir(cards_path))
                if os.path.isdir(os.path.join(cards_path, name)) and name not in {"backs", "readme"}
            ]
        except OSError:
            return ["simple"]
        return decks or ["simple"]

    def _populate_deck_selector(self) -> None:
        decks = self._available_deck_types()
        self.deckTypeCombo.addItems(decks)
        if self.deckType in decks:
            self.deckTypeCombo.setCurrentText(self.deckType)

    def _deck_type_changed(self, deck_type: str) -> None:
        if not deck_type or deck_type == getattr(self, "deckType", None):
            return
        self.deckType = deck_type
        self.deck_inst = Deck.Deck(self.conf, deck_type=self.deckType, height=CARD_HEIGHT, width=CARD_WIDTH)
        self.cardImages = None
        self._update_deck_preview()
        self.update()

    def _update_deck_preview(self) -> None:
        if not hasattr(self, "deckPreview"):
            return
        preview = self.deck_inst.card("s", 14).scaled(
            28,
            36,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        back = self.deck_inst.back().scaled(
            28,
            36,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(70, 34)
        canvas.fill(QColor(getattr(self, "_replayer_panel_color", "#242b31")))
        painter = QPainter(canvas)
        painter.drawPixmap(6, 2, preview)
        painter.drawPixmap(34, 2, back)
        painter.end()
        self.deckPreview.setPixmap(canvas)

    def _apply_replayer_style(self) -> None:
        try:
            from fpdb_3_legacy.ThemeManager import ThemeManager

            colors = ThemeManager().get_legacy_palette()
        except Exception:
            log.exception("Unable to load theme colors for replayer")
            colors = {}

        dark = self._is_dark_color(colors.get("window", "#20262b"))
        background = colors.get("sidebar", "#20262b") if dark else colors.get("surface", "#f4f4f4")
        panel = colors.get("sidebar_panel", "#242b31") if dark else colors.get("panel", "#ffffff")
        panel_hover = colors.get("panel_alt", "#2f3740")
        input_bg = colors.get("input", panel)
        border = "#46505a" if dark else colors.get("border", "#c7cfd8")
        text = "#eef3f7" if dark else colors.get("text", "#17202a")
        muted = colors.get("muted_text", "#9aa5ad")
        accent = colors.get("accent", "#5fa8ff")
        accent_hover = colors.get("accent_hover", accent)
        active_bg = colors.get("accent_soft", "#24364a")
        disabled_bg = colors.get("surface_panel", "#22282e")
        disabled_text = colors.get("muted_text", "#68727b")
        slider_groove = colors.get("surface", "#11161a")
        self._replayer_background_color = background
        self._replayer_panel_color = panel
        self.setStyleSheet(
            f"""
            QWidget {{
                background: {background};
                color: {text};
                font-size: 13px;
            }}
            QPushButton {{
                min-height: 24px;
                min-width: 78px;
                border: 1px solid {accent};
                border-radius: 4px;
                color: {accent_hover};
                background: {panel};
                font-weight: 700;
                font-size: 12px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background: {panel_hover};
                border-color: {accent_hover};
            }}
            QPushButton:disabled {{
                color: {disabled_text};
                border-color: {border};
                background: {disabled_bg};
            }}
            QPushButton[streetActive="true"] {{
                background: {active_bg};
                color: {text};
                border-color: {accent_hover};
            }}
            QCheckBox {{
                spacing: 8px;
                font-weight: 600;
                color: {text};
            }}
            QComboBox {{
                min-height: 30px;
                max-width: 260px;
                border: 1px solid {border};
                border-radius: 5px;
                padding: 4px 8px;
                color: {text};
                background: {input_bg};
                font-weight: 600;
            }}
            QSlider::groove:horizontal {{
                height: 5px;
                background: {slider_groove};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                width: 18px;
                margin: -7px 0;
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            """,
        )
        self.deckLabel.setStyleSheet(f"font-weight: 600; color: {muted}; margin-left: 10px;")
        self._update_deck_preview()
        self.update()

    @staticmethod
    def _is_dark_color(color: str) -> bool:
        qcolor = QColor(color)
        return not qcolor.isValid() or qcolor.lightness() < 128

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        self._apply_replayer_style()

    def _resolve_hero(self, sitename) -> str:
        if getattr(self, "_hero_site_cache", None) is None:
            self._hero_site_cache = {}
            path = os.path.join(Configuration.Config().config_path, "HUD_config.xml")
            try:
                doc = defusedxml.minidom.parse(path)
                for site_node in doc.getElementsByTagName("site"):
                    site_name = site_node.getAttribute("site_name")
                    self._hero_site_cache[site_name] = site_node.getAttribute("screen_name")
            except Exception as exc:
                log.warning("Unable to read HUD screen names for replayer: %s", exc)
        return self._hero_site_cache.get(str(sitename), "")

    def _format_hand_info(self, hand) -> str:
        game_names = {
            "omahahilo": "Omaha Hi/Lo",
            "fusion": "Fusion",
            "27_1draw": "Single Draw 2-7 Lowball",
            "27_3draw": "Triple Draw 2-7 Lowball",
            "a5_3draw": "Triple Draw A-5 Lowball",
            "5_studhi": "5 Card Stud",
            "badugi": "Badugi",
            "badacey": "Badacey",
            "badeucey": "Badeucey",
            "drawmaha": "2-7 Drawmaha",
            "a5_1draw": "A-5 Single Draw",
            "27_razz": "2-7 Razz",
            "fivedraw": "5 Card Draw",
            "holdem": "Hold'em",
            "6_holdem": "Hold'em",
            "omahahi": "Omaha",
            "razz": "Razz",
            "studhi": "7 Card Stud",
            "studhilo": "7 Card Stud Hi/Lo",
            "5_omahahi": "5 Card Omaha",
            "5_omaha8": "5 Card Omaha Hi/Lo",
            "cour_hi": "Courchevel",
            "cour_hilo": "Courchevel Hi/Lo",
            "2_holdem": "Double Hold'em",
            "irish": "Irish",
            "6_omahahi": "6 Card Omaha",
        }
        limit_names = {
            "fl": "Fixed Limit",
            "nl": "No Limit",
            "pl": "Pot Limit",
            "cn": "Cap No Limit",
            "cp": "Cap Pot Limit",
        }
        category = game_names.get(hand.gametype.get("category"), str(hand.gametype.get("category", "unknown")))
        limit = limit_names.get(hand.gametype.get("limitType"), str(hand.gametype.get("limitType", "unknown")))
        info = (
            f"{limit} {category} {hand.gametype['bb']}{hand.gametype['currency']} "
            f"hand n° {hand.handid} played on {hand.sitename}"
        )
        return info + self._special_pot_suffix(hand)

    @staticmethod
    def _special_pot_suffix(hand) -> str:
        """Header markers for bomb pots and splash pots (amounts stored in cents)."""
        currency = hand.gametype.get("currency", "")
        markers = []
        if getattr(hand, "bombPot", 0):
            markers.append("Bomb pot")
        splash = getattr(hand, "splashPot", 0)
        if splash:
            markers.append(f"Splash pot: {Decimal(splash) / 100:.2f}{currency}")
        return ("  ·  " + "  ·  ".join(markers)) if markers else ""

    _RUN_IT_STREETS = frozenset(f"{s}{n}" for s in ("FLOP", "TURN", "RIVER") for n in (1, 2, 3))

    def _is_ofc_replay_entry(self, entry) -> bool:
        if isinstance(entry, OFCHand):
            return True
        if isinstance(entry, dict):
            return entry.get("ofc_variant") is not None or (entry.get("game") or {}).get("base") == "ofc"
        return isinstance(entry, str) and entry.startswith("ofc:")

    def _load_ofc_replay_entry(self, entry) -> OFCHand:
        if isinstance(entry, OFCHand):
            return entry
        if isinstance(entry, dict):
            return build_ofc_hand(entry)
        if isinstance(entry, str) and entry.startswith("ofc:"):
            return load_ofc_hand(self.db, entry.split(":", 1)[1])
        raise ValueError(f"unsupported OFC replay entry: {entry!r}")

    def _format_ofc_info(self, ofc_hand: OFCHand) -> str:
        variant = str(ofc_hand.variant.get("variant", "ofc")).upper()
        return f"{variant} hand n° {ofc_hand.hand_id} played on {ofc_hand.site}"

    def _build_ofc_replay_model(self, ofc_hand: OFCHand) -> ReplayModel:
        states = []
        row_limits = {"top": 3, "middle": 5, "bottom": 5}
        visible_rows = {
            player.name: {row: ["--"] * limit for row, limit in row_limits.items()} for player in ofc_hand.players
        }
        if ofc_hand.rounds:
            for index in range(len(ofc_hand.rounds)):
                current_round = ofc_hand.rounds[index]
                actor = str(current_round.get("player") or "")
                actor_rows = visible_rows.setdefault(
                    actor,
                    {row: ["--"] * limit for row, limit in row_limits.items()},
                )
                has_actor_board = any(card and card != "--" for cards in actor_rows.values() for card in cards)
                round_placed_cards = [card for cards in (current_round.get("placed") or {}).values() for card in cards]
                captured_pending = list(current_round.get("dealt") or current_round.get("active") or [])
                pending_cards = captured_pending
                private_pending = True
                if captured_pending and len(captured_pending) == 5 and not has_actor_board:
                    private_pending = False
                elif not captured_pending and len(round_placed_cards) == 5 and not has_actor_board:
                    pending_cards = list(round_placed_cards)
                    private_pending = False
                elif (
                    not captured_pending
                    and len(round_placed_cards) == 2
                    and has_actor_board
                    and ofc_hand.variant.get("pineapple")
                ):
                    pending_cards = ["0", "0", "0"]
                    private_pending = True
                discarded_cards = list(current_round.get("discarded") or [])
                if pending_cards:
                    states.append(
                        OFCReplayState(
                            round_index=index,
                            phase="deal",
                            rounds=ofc_hand.rounds[: index + 1],
                            current_round=current_round,
                            visible_rows={
                                player: {row: list(cards) for row, cards in rows.items()}
                                for player, rows in visible_rows.items()
                            },
                            actor=actor,
                            pending_cards=pending_cards,
                            discarded_cards=discarded_cards,
                            private_pending=private_pending,
                        )
                    )
                player_rows = visible_rows.setdefault(
                    actor,
                    {row: ["--"] * limit for row, limit in row_limits.items()},
                )
                placed_cards = []
                placed_slots = current_round.get("placed_slots") or {}
                if placed_slots:
                    for row, slots in placed_slots.items():
                        row_cards = player_rows.setdefault(row, ["--"] * row_limits.get(row, 5))
                        for slot in slots:
                            slot_index = int(slot.get("index", 0))
                            card = slot.get("card")
                            if card and 0 <= slot_index < len(row_cards):
                                row_cards[slot_index] = card
                                placed_cards.append(card)
                    for row, cards in (current_round.get("layout") or {}).items():
                        limit = row_limits.get(row, len(cards))
                        player_rows[row] = (list(cards) + ["--"] * limit)[:limit]
                else:
                    for row, cards in (current_round.get("placed") or {}).items():
                        row_cards = player_rows.setdefault(row, ["--"] * row_limits.get(row, 5))
                        for card in cards:
                            if not card or card in row_cards:
                                continue
                            try:
                                slot_index = row_cards.index("--")
                            except ValueError:
                                continue
                            row_cards[slot_index] = card
                            placed_cards.append(card)
                states.append(
                    OFCReplayState(
                        round_index=index,
                        phase="place",
                        rounds=ofc_hand.rounds[: index + 1],
                        current_round=current_round,
                        visible_rows={
                            player: {row: list(cards) for row, cards in rows.items()}
                            for player, rows in visible_rows.items()
                        },
                        actor=actor,
                        placed_cards=placed_cards,
                        discarded_cards=discarded_cards,
                    )
                )
            states.append(
                OFCReplayState(
                    round_index=len(ofc_hand.rounds),
                    phase="result",
                    rounds=list(ofc_hand.rounds),
                    current_round=None,
                    visible_rows={
                        player: {row: list(cards) for row, cards in rows.items()}
                        for player, rows in visible_rows.items()
                    },
                )
            )
        else:
            states.append(
                OFCReplayState(round_index=0, phase="result", rounds=[], current_round=None, visible_rows=visible_rows)
            )
        return ReplayModel(
            hand=ofc_hand,
            info=self._format_ofc_info(ofc_hand),
            states=states,
            seen_streets={f"ROUND{index + 1}" for index in range(len(states))},
        )

    def _ofc_state_label(self, state: OFCReplayState) -> str:
        if state.phase == "deal":
            if not state.private_pending:
                return f"Initial {state.round_index + 1}"
            return f"Deal {state.round_index + 1}"
        if state.phase == "place":
            return f"Place {state.round_index + 1}"
        return "Result"

    def _draw_ofc_header(self, painter: QPainter) -> None:
        painter.setPen(QColor("#eef3f7"))
        painter.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        painter.drawText(QRectF(28, 18, self.width() - 56, 28), Qt.AlignmentFlag.AlignLeft, self.info)
        state = self.states[self.stateSlider.value()] if self.states else None
        label = self._ofc_state_label(state) if state else "Result"
        actor = f"  ·  {state.actor}" if state and state.actor else ""
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.DemiBold))
        painter.setPen(QColor("#9aa5ad"))
        painter.drawText(
            QRectF(28, 48, self.width() - 56, 24),
            Qt.AlignmentFlag.AlignLeft,
            f"{label}{actor}  ·  step {self.stateSlider.value() + 1}/{max(1, len(self.states))}",
        )

    def _ofc_table_rect(self) -> QRectF:
        right_margin = TIMELINE_WIDTH + 68 if self.width() >= TIMELINE_MIN_WINDOW_WIDTH else 28
        return QRectF(
            28,
            HEADER_HEIGHT,
            max(620, self.width() - right_margin - 28),
            max(360, self.height() - HEADER_HEIGHT - CONTROL_RESERVED_HEIGHT - 18),
        )

    def _draw_ofc_table(self, painter: QPainter, table_rect: QRectF) -> None:
        painter.fillRect(self.rect(), QColor(getattr(self, "_replayer_background_color", "#20262b")))
        rail = QLinearGradient(table_rect.topLeft(), table_rect.bottomRight())
        rail.setColorAt(0, QColor("#57636c"))
        rail.setColorAt(0.45, QColor("#11161a"))
        rail.setColorAt(1, QColor("#7c8790"))
        painter.setPen(QPen(QColor("#0c1013"), 5))
        painter.setBrush(rail)
        painter.drawEllipse(table_rect)

        felt_rect = table_rect.adjusted(30, 26, -30, -26)
        felt = QLinearGradient(felt_rect.topLeft(), felt_rect.bottomRight())
        felt.setColorAt(0, QColor("#263338"))
        felt.setColorAt(0.55, QColor("#11191d"))
        felt.setColorAt(1, QColor("#324047"))
        painter.setPen(QPen(QColor("#72808a"), 1))
        painter.setBrush(felt)
        painter.drawEllipse(felt_rect)

        painter.save()
        painter.setOpacity(0.18)
        painter.setPen(QColor("#dce7ee"))
        logo_font = QFont("Helvetica", max(22, int(felt_rect.width() * 0.055)), QFont.Weight.Black)
        logo_font.setItalic(True)
        painter.setFont(logo_font)
        painter.drawText(felt_rect, Qt.AlignmentFlag.AlignCenter, "OFC")
        painter.restore()

    def _ofc_board_center(self, table_rect: QRectF, index: int, player_count: int) -> QPointF:
        if player_count == 1:
            return table_rect.center()
        angle = -pi / 2 + (2 * pi * index / player_count)
        return QPointF(
            table_rect.center().x() + cos(angle) * table_rect.width() * 0.21,
            table_rect.center().y() + sin(angle) * table_rect.height() * 0.20,
        )

    def _ofc_seat_center(self, table_rect: QRectF, index: int, player_count: int) -> QPointF:
        if player_count == 1:
            angle = pi / 2
        else:
            angle = -pi / 2 + (2 * pi * index / player_count)
        return QPointF(
            table_rect.center().x() + cos(angle) * table_rect.width() * 0.43,
            table_rect.center().y() + sin(angle) * table_rect.height() * 0.43,
        )

    def _draw_ofc_seat(self, painter: QPainter, player, center: QPointF, active: bool) -> None:
        panel = QRectF(center.x() - 92, center.y() - 29, 184, 58)
        painter.setPen(QPen(QColor("#78b7ff") if active else QColor("#40505b"), 2 if active else 1))
        painter.setBrush(QColor("#1b252b"))
        painter.drawRoundedRect(panel, 8, 8)

        painter.setPen(QColor("#eef3f7"))
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        painter.drawText(panel.adjusted(10, 7, -10, -28), Qt.AlignmentFlag.AlignLeft, player.name)
        painter.setFont(QFont("Helvetica", 8, QFont.Weight.DemiBold))
        painter.setPen(QColor("#9aa5ad"))
        painter.drawText(
            panel.adjusted(10, 26, -10, -6),
            Qt.AlignmentFlag.AlignLeft,
            f"Seat {format_number(player.seat_idx, 0)}  ·  {format_number(player.points, 0)} pts  ·  "
            f"{format_replay_amount(player.collected, self.currency_code)}",
        )

    def _draw_ofc_board(
        self, painter: QPainter, center: QPointF, rows: dict[str, list[str]], highlight: set[str]
    ) -> None:
        row_defs = [("top", "Top", 3), ("middle", "Middle", 5), ("bottom", "Bottom", 5)]
        card_w = max(28, min(46, int(self._ofc_table_rect().width() / 30), int(self._ofc_table_rect().height() / 8)))
        card_h = int(card_w * CARD_HEIGHT / CARD_WIDTH)
        gap = 4
        board_w = 5 * card_w + 4 * gap + 56
        board_h = 3 * card_h + 28
        board = QRectF(center.x() - board_w / 2, center.y() - board_h / 2, board_w, board_h)

        painter.setPen(QPen(QColor("#3e4d57"), 1))
        painter.setBrush(QColor(24, 32, 37, 190))
        painter.drawRoundedRect(board, 10, 10)

        self.render_card_width = card_w
        self.render_card_height = card_h
        self.render_card_spacing: float = float(card_w + gap)
        for row_index, (row_key, label, limit) in enumerate(row_defs):
            y = board.y() + 10 + row_index * (card_h + 4)
            painter.setFont(QFont("Helvetica", 8, QFont.Weight.Bold))
            painter.setPen(QColor("#9aa5ad"))
            painter.drawText(QRectF(board.x() + 9, y, 42, card_h), Qt.AlignmentFlag.AlignVCenter, label)

            row_width = limit * card_w + (limit - 1) * gap
            x = board.x() + 52 + (5 * card_w + 4 * gap - row_width) / 2
            for slot in range(limit):
                slot_rect = QRectF(x + slot * (card_w + gap), y, card_w, card_h)
                painter.setPen(QPen(QColor("#46545e"), 1))
                painter.setBrush(QColor(13, 19, 22, 130))
                painter.drawRoundedRect(slot_rect, 4, 4)

            cards = list(rows.get(row_key, []))
            for slot, card in enumerate(cards[:limit]):
                if not card or card == "--":
                    continue
                slot_rect = QRectF(x + slot * (card_w + gap), y, card_w, card_h)
                self._draw_cards(
                    painter,
                    [card],
                    slot_rect,
                    overlap=False,
                    highlight=highlight,
                    lift_highlight=False,
                )

    def _draw_ofc_pending_cards(self, painter: QPainter, table_rect: QRectF, state: OFCReplayState) -> None:
        if state.phase != "deal" or not state.pending_cards:
            return
        max_cards_per_row = 8
        card_w = max(28, min(48, int(table_rect.width() / 32)))
        card_h = int(card_w * CARD_HEIGHT / CARD_WIDTH)
        gap = 5
        rows = [
            state.pending_cards[index : index + max_cards_per_row]
            for index in range(0, len(state.pending_cards), max_cards_per_row)
        ]
        tray_w = max(len(row) for row in rows) * card_w + (max(len(row) for row in rows) - 1) * gap + 28
        tray_h = len(rows) * card_h + (len(rows) - 1) * gap + 46
        tray = QRectF(table_rect.center().x() - tray_w / 2, table_rect.center().y() - tray_h / 2, tray_w, tray_h)

        painter.setPen(QPen(QColor("#78b7ff"), 2))
        painter.setBrush(QColor(20, 29, 34, 225))
        painter.drawRoundedRect(tray, 10, 10)
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#eef3f7"))
        painter.drawText(
            tray.adjusted(14, 8, -14, -tray.height() + 32), Qt.AlignmentFlag.AlignLeft, f"{state.actor} receives"
        )

        self.render_card_width = card_w
        self.render_card_height = card_h
        self.render_card_spacing = card_w + gap
        for row_index, cards in enumerate(rows):
            row_w = len(cards) * card_w + max(0, len(cards) - 1) * gap
            x = tray.center().x() - row_w / 2
            y = tray.y() + 34 + row_index * (card_h + gap)
            self._draw_cards(
                painter,
                ["0"] * len(cards) if state.private_pending else cards,
                QRectF(x, y, row_w, card_h),
                overlap=False,
                highlight=set() if state.private_pending else set(cards),
                lift_highlight=False,
            )

    def _draw_ofc_result_summary(
        self, painter: QPainter, table_rect: QRectF, ofc_hand: OFCHand, state: OFCReplayState
    ) -> None:
        if state.phase != "result":
            return
        panel = QRectF(table_rect.center().x() - 180, table_rect.center().y() - 62, 360, 124)
        painter.setPen(QPen(QColor("#d5b85b"), 2))
        painter.setBrush(QColor(18, 25, 29, 230))
        painter.drawRoundedRect(panel, 10, 10)

        painter.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        painter.setPen(QColor("#eef3f7"))
        painter.drawText(panel.adjusted(14, 10, -14, -88), Qt.AlignmentFlag.AlignCenter, "Final result")
        painter.setFont(QFont("Helvetica", 9, QFont.Weight.DemiBold))
        y = panel.y() + 42
        for player in sorted(ofc_hand.players, key=lambda item: item.points, reverse=True):
            line = f"{player.name}: {format_number(player.points, 0)} pts"
            if player.collected:
                line += f" · collected {format_replay_amount(player.collected, self.currency_code)}"
            painter.setPen(
                QColor("#9ee6a7")
                if player.points > 0
                else QColor("#f0a0a0")
                if player.points < 0
                else QColor("#c4cdd4")
            )
            painter.drawText(QRectF(panel.x() + 18, y, panel.width() - 36, 20), Qt.AlignmentFlag.AlignLeft, line)
            y += 21

    def _draw_ofc_scene(self, painter: QPainter, ofc_hand: OFCHand, state: OFCReplayState) -> None:
        table_rect = self._ofc_table_rect()
        self._draw_ofc_table(painter, table_rect)

        current = state.current_round or {}
        current_player = state.actor or current.get("player")
        highlight_cards = set(state.pending_cards) if state.phase == "deal" else set(state.placed_cards)
        highlight_by_player = {current_player: highlight_cards} if current_player else {}
        player_count = max(1, len(ofc_hand.players))

        for index, player in enumerate(ofc_hand.players):
            active = player.name == current_player
            self._draw_ofc_board(
                painter,
                self._ofc_board_center(table_rect, index, player_count),
                state.visible_rows.get(player.name, {}),
                highlight_by_player.get(player.name, set()),
            )
            self._draw_ofc_seat(painter, player, self._ofc_seat_center(table_rect, index, player_count), active)
        self._draw_ofc_pending_cards(painter, table_rect, state)
        self._draw_ofc_result_summary(painter, table_rect, ofc_hand, state)

    def _draw_ofc_timeline(self, painter: QPainter, state: OFCReplayState) -> None:
        width = 280
        rect = QRectF(
            self.width() - width - 28,
            HEADER_HEIGHT,
            width,
            self.height() - HEADER_HEIGHT - CONTROL_RESERVED_HEIGHT - 18,
        )
        if rect.x() < 680:
            return
        painter.setPen(QPen(QColor("#46505a"), 1))
        painter.setBrush(QColor("#171d22"))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        painter.setPen(QColor("#eef3f7"))
        painter.drawText(rect.adjusted(14, 12, -14, -12), Qt.AlignmentFlag.AlignTop, "OFC rounds")
        painter.setFont(QFont("Helvetica", 9, QFont.Weight.Medium))
        y = rect.y() + 44
        row_h = 44
        max_rows = max(3, int((rect.height() - 54) // row_h))
        for round_info in state.rounds[-max_rows:]:
            placed = round_info.get("placed") or {}
            parts = [f"{row}: {' '.join(cards)}" for row, cards in placed.items()]
            entry = f"{round_info.get('round')}. {round_info.get('player')}\n" + ("; ".join(parts) or "no placement")
            entry_rect = QRectF(rect.x() + 10, y, rect.width() - 20, row_h - 5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#20272d"))
            painter.drawRoundedRect(entry_rect, 4, 4)
            painter.setPen(QColor("#c4cdd4"))
            painter.drawText(
                entry_rect.adjusted(8, 2, -8, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, entry
            )
            y += row_h

    def _paint_ofc_replay(self, painter: QPainter) -> None:
        ofc_hand = self.replay_model.hand
        state = self.states[self.stateSlider.value()]
        self._draw_ofc_scene(painter, ofc_hand, state)
        self._draw_ofc_header(painter)
        self._draw_ofc_timeline(painter, state)

    def _build_replay_model(self, hand) -> ReplayModel:
        states = []
        seen_streets: list[str] = []
        state = TableState(hand)
        # Index of the last street worth showing: one that carries actions OR has
        # board cards dealt. Keep showing up to this street even if an intermediate
        # (or trailing) street has no betting — e.g. an unbet DEAL before a draw, or
        # a turn/river that were dealt to showdown with no further action (checks not
        # recorded). Otherwise the replay stops at the flop and never reveals the
        # turn/river even though the showdown is evaluated on the full board.
        board = getattr(hand, "board", {}) or {}
        last_shown_idx = -1
        street_groups = replay_street_groups(hand)
        for idx, group in enumerate(street_groups):
            if any(hand.actions.get(street) or board.get(street) for street in group):
                last_shown_idx = idx
        for idx, group in enumerate(street_groups):
            street = group[0]
            if state.called > 0:
                for player in list(state.players.values()):
                    if player.stack == 0:
                        state.allin = True
                        break
            # Run-it streets (FLOP1/TURN1/.../RIVER3) carry no betting but must
            # always be shown, even when the all-in could not be inferred from
            # the reconstructed stacks.
            is_run_it = any(item in self._RUN_IT_STREETS for item in group)
            # .get() guards a DB-reconstructed hand that lists a street in
            # allStreets without an actions entry.
            street_actions = [action for item in group for action in hand.actions.get(item, [])]
            # Stop only once we are past the last street worth showing (and not
            # all-in / run-it), not at the first empty intermediate street.
            if not street_actions and not state.allin and not is_run_it and idx > last_shown_idx:
                break
            seen_streets.extend(group)
            state = copy.deepcopy(state)
            state.startPhase(street)
            for parallel_street in group[1:]:
                state.renderBoard.add(parallel_street)
            if getattr(hand, "bombPot", 0) and is_run_it:
                state.street = street.rstrip("123")
                seen_streets.append(state.street)
            states.append(state)
            for action in street_actions:
                state = copy.deepcopy(state)
                state.updateForAction(action)
                states.append(state)

        state = copy.deepcopy(state)
        state.endHand(hand.collectees, hand.pot.returned)
        states.append(state)
        return ReplayModel(hand=hand, info=self._format_hand_info(hand), states=states, seen_streets=set(seen_streets))

    def _frame_from_state(self, state) -> ReplayFrame:
        hand = self.replay_model.hand
        is_showdown = getattr(state, "ended", False)
        showdown_strings = getattr(hand, "showdownStrings", {}) or {}
        winning_hands = getattr(hand, "winningHand", {}) or {}
        collectees = getattr(hand, "collectees", {}) or {}
        cashouts = getattr(hand, "cashOutAmounts", {}) or {}
        base = hand.gametype.get("base", "")
        category = hand.gametype.get("category", "")
        # Build the board as separate runs (run-it-twice/three keeps each board
        # apart so hands are evaluated against the correct run, never mixed).
        board = state.board or {}
        # Run-it boards first (FLOP1/2/3). The plain FLOP/TURN/RIVER are only a
        # copy of run 1 for RIT hands, so use them only when there are no runs
        # (normal hands). This keeps board_runs aligned with what _draw_board
        # shows, so per-run winner/combination data is not shifted.
        board_runs = []
        for r in (1, 2, 3):
            rc = []
            for street in (f"FLOP{r}", f"TURN{r}", f"RIVER{r}"):
                rc.extend(self._normalized_cards(board.get(street) or []))
            if rc:
                board_runs.append(rc)
        if not board_runs:
            single = []
            for street in ("FLOP", "TURN", "RIVER"):
                single.extend(self._normalized_cards(board.get(street) or []))
            board_runs = [single] if single else [[]]
        players = []
        for player in state.players.values():
            combination = None
            winning_cards: frozenset[str] = frozenset()
            is_winner = False
            if is_showdown:
                combination = showdown_strings.get(player.name)
                is_winner = player.name in collectees
                explicit = winning_hands.get(player.name)
                hole = self._normalized_cards(list(player.holecards or []))
                if explicit:
                    winning_cards = frozenset(self._normalized_cards(explicit))
                elif is_winner:
                    # Best hand per run (Omaha = 2 hole + 3 board), unioned so
                    # the highlight reflects every run the winner contests.
                    for run in board_runs:
                        winning_cards |= best_hand_cards(hole, run, base, category)
                    if not winning_cards:
                        winning_cards = frozenset(c for c in hole if c != "0")
            players.append(
                ReplayPlayer(
                    name=player.name,
                    seat=player.seat,
                    stack=player.stack,
                    chips=player.chips,
                    action=player.action,
                    justacted=player.justacted,
                    allin=player.allin,
                    holecards=list(player.holecards or []),
                    combination=combination,
                    winning_cards=winning_cards,
                    is_winner=is_winner,
                    cashout=cashouts.get(player.name) if is_showdown else None,
                    discard_count=(
                        getattr(player, "discardCount", 0)
                        if player.justacted and (player.action or "").startswith("discards")
                        else 0
                    ),
                    discard_cards=(
                        list(getattr(player, "discardCards", []))
                        if player.justacted and (player.action or "").startswith("discards")
                        else []
                    ),
                )
            )
        runs_info = []
        if is_showdown and len(board_runs) > 1:
            runs_info = self._compute_run_winners(players, board_runs, base, category)
        return ReplayFrame(
            street=state.street,
            board=state.board,
            render_board=set(state.renderBoard),
            pot=state.newpot,
            players=players,
            pots=state.computePots(),
            runs=runs_info,
            board_mode="double"
            if getattr(hand, "bombPot", 0) and len(board_runs) > 1
            else "run"
            if len(board_runs) > 1
            else "single",
            category=category,
        )

    def _compute_run_winners(self, players, board_runs, base, category) -> list:
        """For each run board, find the winner among shown players and record the
        board/hole highlight colours. Mutates each winner's hole_run_colors so
        a hole card used in N runs gets N nested outlines."""
        contesting = [
            p for p in players if p.action != "folds" and any(c not in ("0", "0x", None) for c in (p.holecards or []))
        ]
        runs_info = []
        for i, run in enumerate(board_runs):
            color = RUN_COLORS[i % len(RUN_COLORS)]
            info: dict[str, Any] = {"color": color, "board_highlight": frozenset(), "winner": None, "combo": ""}
            real_cards = sum(1 for c in run if c not in ("0", "0x", None))
            if contesting and real_cards >= 5:
                best_rank = winner = winner_cards = None
                for p in contesting:
                    rank, cards = best_hand(self._normalized_cards(list(p.holecards or [])), run, base, category)
                    if rank is not None and (best_rank is None or rank > best_rank):
                        best_rank, winner, winner_cards = rank, p, cards
                if winner is not None:
                    info["winner"] = winner.name
                    info["combo"] = hand_category_name(best_rank)
                    # Outline only the board cards that form the winning
                    # combination (e.g. the 3 board cards of an Omaha hand),
                    # in the run's colour.
                    info["board_highlight"] = frozenset(c for c in (winner_cards or frozenset()) if c in run)
                    # The hole cards the winner uses, for nested outlines.
                    hole_used = frozenset(winner_cards or frozenset()) & frozenset(
                        self._normalized_cards(list(winner.holecards or []))
                    )
                    for card in hole_used:
                        winner.hole_run_colors.setdefault(card, []).append(color)
            runs_info.append(info)
        return runs_info

    def _normalized_cards(self, cards: list[str]) -> list[str]:
        return ["0" if card in {"0x", "0", None} else card for card in cards]

    def _visible_cards(self, player: ReplayPlayer, street: str | None, is_final_frame: bool) -> list[str]:
        hand = self.replay_model.hand
        category = hand.gametype.get("category", "")
        base = hand.gametype.get("base", "")
        is_hero = player.name == self.Heroes
        show_all_known = not self.showCards.isChecked() or is_hero or is_final_frame
        visible_count = visible_hole_card_count(category, street, is_final_frame)
        actual_cards = self._normalized_cards(player.holecards[:visible_count])
        if is_hero:
            # The hero's own cards are always known, so a trailing unknown card
            # means the history is missing it (e.g. a stud 7th-street down card
            # absent from an anonymized/converted hand). Drop it instead of drawing
            # a misleading face-down back among the hero's revealed cards.
            while actual_cards and actual_cards[-1] in {"0", "0x", ""}:
                actual_cards.pop()
        if show_all_known:
            return actual_cards
        if base == "stud":
            result = []
            for idx, card in enumerate(actual_cards):
                is_closed = (idx == 0) if category == "5_studhi" else (idx in (0, 1, 6))
                if is_closed:
                    result.append("0")
                else:
                    result.append(card)
            return result
        return ["0"] * visible_count

    def _button_street_name(self, street: str | None) -> str:
        if street in ("BLINDSANTES", "PREFLOP", "DEAL"):
            return "PREFLOP"
        return street or ""

    def _sync_replayer_controls(self) -> None:
        if getattr(self, "replay_mode", "hand") == "ofc":
            current_round = f"ROUND{self.stateSlider.value() + 1}"
            for round_name, button in getattr(self, "streetButtons", {}).items():
                active = round_name == current_round
                button.setProperty("streetActive", active)
                button.style().unpolish(button)
                button.style().polish(button)
            self.prevButton.setEnabled(self.stateSlider.value() > 0)
            self.nextButton.setEnabled(self.stateSlider.value() < self.stateSlider.maximum())
            return
        current_state = self.states[self.stateSlider.value()] if self.states else None
        current_street = self._button_street_name(getattr(current_state, "street", None))
        for street, button in getattr(self, "streetButtons", {}).items():
            active = self._button_street_name(street) == current_street
            button.setProperty("streetActive", active)
            button.style().unpolish(button)
            button.style().polish(button)
        self.prevButton.setEnabled(self.stateSlider.value() > 0)
        self.nextButton.setEnabled(self.stateSlider.value() < self.stateSlider.maximum())

    def _draw_cards(
        self,
        painter: QPainter,
        cards: list[str],
        rect: QRectF,
        overlap: bool = True,
        highlight: frozenset | set | None = None,
        dim_others: bool = False,
        lift_up: bool = True,
        highlight_color: str = "#ffd34d",
        lift_highlight: bool = True,
    ) -> None:
        if not cards:
            return
        card_width = getattr(self, "render_card_width", self.cardwidth)
        card_height = getattr(self, "render_card_height", self.cardheight)
        spacing = getattr(self, "render_card_spacing", card_width * CARD_SPACING_RATIO) if overlap else card_width + 4
        total_width = card_width + spacing * (len(cards) - 1)
        x = rect.center().x() - total_width / 2
        y = rect.y()
        highlight = highlight or frozenset()
        # Offset winning cards away from the player's panel so they never slide
        # behind it (panel is above the cards for top seats, below for bottom).
        lift = int(card_height * 0.18) * (-1 if lift_up else 1) if lift_highlight else 0
        for card in cards:
            is_win = card in highlight and card not in {"0", "0x", None}
            card_token = f"T{card[-1]}" if isinstance(card, str) and len(card) == 3 and card.startswith("10") else card
            card_index = Card.encodeCard(card_token)
            assert self.cardImages is not None
            pixmap = self.cardImages[card_index]
            card_y = y + lift if is_win else y
            card_rect = QRectF(x, card_y, card_width, card_height)
            if highlight and not is_win and dim_others:
                # Fade the cards that are not part of the winning combination.
                painter.save()
                painter.setOpacity(0.45)
                painter.drawPixmap(card_rect.toRect(), pixmap)
                painter.restore()
            else:
                painter.drawPixmap(card_rect.toRect(), pixmap)
            if is_win:
                pen = QPen(QColor(highlight_color), max(2, int(card_width * 0.06)))
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(card_rect.adjusted(1, 1, -1, -1), 4, 4)
            x += spacing

    def _draw_cards_multi_outline(self, painter, cards, rect, card_colors, lift_up=True) -> None:
        """Draw hole cards where each card may carry several nested outlines, one
        per run whose winning combination it belongs to (run-it-twice/three)."""
        if not cards:
            return
        card_width = getattr(self, "render_card_width", self.cardwidth)
        card_height = getattr(self, "render_card_height", self.cardheight)
        spacing = getattr(self, "render_card_spacing", card_width * CARD_SPACING_RATIO)
        total_width = card_width + spacing * (len(cards) - 1)
        x = rect.center().x() - total_width / 2
        y = rect.y()
        lift = int(card_height * 0.18) * (-1 if lift_up else 1)
        any_highlight = any(card_colors.get(c) for c in cards)
        pen_w = max(2, int(card_width * 0.06))
        for card in cards:
            colors = card_colors.get(card, []) if card not in {"0", "0x", None} else []
            card_y = y + lift if colors else y
            card_rect = QRectF(x, card_y, card_width, card_height)
            assert self.cardImages is not None
            pixmap = self.cardImages[Card.encodeCard(card)]
            if any_highlight and not colors:
                painter.save()
                painter.setOpacity(0.45)
                painter.drawPixmap(card_rect.toRect(), pixmap)
                painter.restore()
            else:
                painter.drawPixmap(card_rect.toRect(), pixmap)
            # Nested outlines: one ring per run, inset progressively.
            for depth, color in enumerate(colors):
                inset = 1 + depth * (pen_w + 1)
                painter.setPen(QPen(QColor(color), pen_w))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(card_rect.adjusted(inset, inset, -inset, -inset), 4, 4)
            x += spacing

    def _draw_folded_cards(self, painter, cards, seat, layout, progress) -> None:
        """Draw a folded player's cards as mucked: slide toward the table
        centre, rotate slightly and fade. progress 0..1 drives the animation
        (1.0 = at rest, fully mucked)."""
        if not cards:
            return
        # Smoothstep easing for a natural toss.
        e = progress * progress * (3 - 2 * progress)
        center = layout.table_rect.center()
        cx = seat.cards_rect.center().x()
        cy = seat.cards_rect.center().y()
        offset_x = (center.x() - cx) * 0.20 * e
        offset_y = (center.y() - cy) * 0.20 * e
        painter.save()
        painter.setOpacity(max(0.12, 1.0 - 0.85 * e))
        painter.translate(offset_x, offset_y)
        painter.translate(cx, cy)
        painter.rotate(14 * e)
        painter.translate(-cx, -cy)
        self._draw_cards(painter, cards, seat.cards_rect, overlap=True)
        painter.restore()

    def _draw_discarded_cards(self, painter, cards, count, seat, layout, progress) -> None:
        """Animate a draw player's discarded cards flying off toward the muck.

        Uses the actual cards when known (hero), otherwise ``count`` card backs.
        progress 0..1 drives the toss (fades out as it completes)."""
        n = len(cards) if cards else int(count or 0)
        if n <= 0:
            return
        draw_cards = list(cards) if cards else ["0"] * n
        card_w = getattr(self, "render_card_width", self.cardwidth)
        card_h = getattr(self, "render_card_height", self.cardheight)
        e = progress * progress * (3 - 2 * progress)  # smoothstep
        center = layout.table_rect.center()
        cx = seat.cards_rect.center().x()
        cy = seat.cards_rect.center().y()
        # Slide toward the centre with a slight upward arc, fading out.
        offset_x = (center.x() - cx) * 0.45 * e
        offset_y = (center.y() - cy) * 0.45 * e - int(card_h * 0.25 * (e - e * e) * 4)
        painter.save()
        painter.setOpacity(max(0.0, 1.0 - e))
        painter.translate(offset_x, offset_y)
        spacing = card_w * 0.5
        total = card_w + spacing * (n - 1)
        x = cx - total / 2
        y = seat.cards_rect.y() - int(card_h * 0.12)
        painter.translate(cx, cy)
        painter.rotate(10 * e)
        painter.translate(-cx, -cy)
        for c in draw_cards:
            assert self.cardImages is not None
            painter.drawPixmap(QRectF(x, y, card_w, card_h).toRect(), self.cardImages[Card.encodeCard(c)])
            x += spacing
        painter.restore()

    def _draw_table(self, painter: QPainter, layout: ReplayLayout) -> None:
        painter.fillRect(self.rect(), QColor(getattr(self, "_replayer_background_color", "#20262b")))
        outer = QLinearGradient(layout.table_rect.topLeft(), layout.table_rect.bottomRight())
        outer.setColorAt(0, QColor("#565e66"))
        outer.setColorAt(0.5, QColor("#161a1f"))
        outer.setColorAt(1, QColor("#7b858c"))
        painter.setPen(QPen(QColor("#0e1115"), 4))
        painter.setBrush(outer)
        painter.drawEllipse(layout.table_rect)

        inner = layout.table_rect.adjusted(26, 24, -26, -24)
        felt = QLinearGradient(inner.topLeft(), inner.bottomRight())
        felt.setColorAt(0, QColor("#273137"))
        felt.setColorAt(0.55, QColor("#11171b"))
        felt.setColorAt(1, QColor("#343c42"))
        painter.setPen(QPen(QColor("#747d84"), 1))
        painter.setBrush(felt)
        painter.drawEllipse(inner)

        logo_rect = QRectF(
            inner.center().x() - inner.width() * 0.2,
            inner.top() + inner.height() * 0.17,
            inner.width() * 0.4,
            inner.height() * 0.16,
        )
        painter.save()
        painter.setOpacity(0.2)
        painter.setPen(QColor("#05090c"))
        logo_font = QFont("Helvetica", max(20, int(inner.width() * 0.055)), QFont.Weight.Black)
        logo_font.setItalic(True)
        logo_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        painter.setFont(logo_font)
        painter.drawText(logo_rect.adjusted(3, 3, 3, 3), Qt.AlignmentFlag.AlignCenter, "FPDB")
        painter.setPen(QColor("#dce7ee"))
        painter.drawText(logo_rect, Qt.AlignmentFlag.AlignCenter, "FPDB")

        poker_rect = logo_rect.translated(0, logo_rect.height() * 0.58)
        poker_font = QFont("Helvetica", max(8, int(inner.width() * 0.017)), QFont.Weight.Bold)
        poker_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 150)
        painter.setFont(poker_font)
        painter.setPen(QColor("#6aa9ff"))
        painter.drawText(poker_rect, Qt.AlignmentFlag.AlignCenter, "POKER")
        painter.restore()

    def _draw_header(self, painter: QPainter) -> None:
        painter.setPen(QColor("#eef3f7"))
        painter.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        painter.drawText(QRectF(28, 18, self.width() - 56, 28), Qt.AlignmentFlag.AlignLeft, self.info)
        state = self.states[self.stateSlider.value()] if self.states else None
        street = self._button_street_name(getattr(state, "street", None)) or "START"
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.DemiBold))
        painter.setPen(QColor("#9aa5ad"))
        painter.drawText(
            QRectF(28, 48, self.width() - 56, 24),
            Qt.AlignmentFlag.AlignLeft,
            f"{street}  ·  action {self.stateSlider.value() + 1}/{max(1, len(self.states))}",
        )

    def _draw_board(self, painter: QPainter, frame: ReplayFrame, layout: ReplayLayout) -> None:
        # Gather the board as one or more runs (run-it-twice/three stacks).
        runs = []
        single = []
        for street in ("FLOP", "TURN", "RIVER"):
            if street in frame.render_board and frame.board.get(street):
                single.extend(frame.board[street])
        if single:
            runs.append(single)
        for r in (1, 2, 3):
            rc = []
            for street in (f"FLOP{r}", f"TURN{r}", f"RIVER{r}"):
                if street in frame.render_board and frame.board.get(street):
                    rc.extend(frame.board[street])
            if rc:
                runs.append(rc)
        # Courchevel: the first flop card (the "flopet") is dealt face-up during
        # pre-flop, before any board street is rendered. Show it on its own only
        # while no street/run board is on screen yet; once the flop (or a run
        # board) appears, the flopet is already part of that board.
        if not runs and (frame.category or "").lower().startswith("cour") and frame.board.get("FLOP"):
            runs.append(list(frame.board["FLOP"][:1]))
        board_cards = [c for run in runs for c in run]

        board_highlight: frozenset[str] = frozenset()
        for fplayer in frame.players:
            if fplayer.is_winner and fplayer.winning_cards:
                board_highlight |= fplayer.winning_cards

        if len(runs) <= 1:
            self._draw_cards(
                painter,
                board_cards,
                layout.board_rect,
                overlap=False,
                highlight=board_highlight or None,
            )
        else:
            # Run-it-twice/three: always stack each run on its own row (even
            # during the run-out, before the winner is known); apply per-run
            # colour/highlight/label once the model has resolved them.
            card_h = getattr(self, "render_card_height", self.cardheight)
            card_w = getattr(self, "render_card_width", self.cardwidth)
            row_gap = int(card_h * 0.18)
            row_h = card_h + row_gap
            top = layout.board_rect.center().y() - (row_h * len(runs) - row_gap) / 2
            for i, run in enumerate(runs):
                rect = QRectF(layout.board_rect.x(), top + i * row_h, layout.board_rect.width(), card_h)
                info = frame.runs[i] if i < len(frame.runs) else {}
                run_color = info.get("color", RUN_COLORS[i % len(RUN_COLORS)])
                self._draw_cards(
                    painter,
                    run,
                    rect,
                    overlap=False,
                    highlight=info.get("board_highlight") or None,
                    highlight_color=run_color,
                    lift_highlight=False,
                )
                # A double-board bomb pot is simultaneous, not a second runout.
                n_cards = sum(1 for c in run if c not in ("0", "0x", None)) or len(run)
                strip_w = card_w + (card_w + 4) * (n_cards - 1)
                label_kind = "Board" if frame.board_mode == "double" else "Run"
                parts = [f"{label_kind} {i + 1}"]
                if info.get("winner"):
                    parts.append(info["winner"])
                    if info.get("combo"):
                        parts.append(info["combo"])
                label = "\n".join(parts)
                lbl_w = 200
                lbl_right = rect.center().x() - strip_w / 2 - 8
                lbl_rect = QRectF(lbl_right - lbl_w, rect.y() - row_gap, lbl_w, card_h + row_gap)
                painter.setPen(QColor(run_color) if info.get("winner") else QColor("#9aa5ad"))
                painter.setFont(QFont("Helvetica", max(9, int(card_h * 0.2)), QFont.Weight.Bold))
                painter.drawText(
                    lbl_rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    label,
                )

        pots = frame.pots if frame.pots else [("Pot", frame.pot)]
        pot_total = sum(amount for _label, amount in pots)
        if pot_total <= 0:
            # Pot already collected (hand conclusion): nothing to display.
            return
        if len(pots) <= 1:
            pot_text = f"Pot: {format_replay_amount(pot_total, self.currency_code)}"
        else:
            pot_text = "\n".join(
                f"{label}: {format_replay_amount(amount, self.currency_code)}" for label, amount in pots
            )

        pot_rect = layout.pot_rect
        if not board_cards:
            pot_rect = QRectF(
                layout.table_rect.center().x() - 88,
                layout.table_rect.center().y() - 14,
                176,
                28,
            )
        if len(pots) > 1:
            extra = (len(pots) - 1) * 18
            pot_rect = QRectF(
                pot_rect.x(),
                pot_rect.y() - extra / 2,
                pot_rect.width(),
                pot_rect.height() + extra,
            )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 12, 15, 190))
        painter.drawRoundedRect(pot_rect, 8, 8)
        painter.setPen(QColor("#ffe769"))
        painter.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        painter.drawText(pot_rect, Qt.AlignmentFlag.AlignCenter, pot_text)

    def _draw_player(
        self,
        painter: QPainter,
        player: ReplayPlayer,
        seat: SeatLayout,
        layout: ReplayLayout,
        street: str | None,
        is_final_frame: bool,
    ) -> None:
        table_area_height = max(300, self.height() - CONTROL_RESERVED_HEIGHT - HEADER_HEIGHT - TABLE_MARGIN)
        card_scale = max(MIN_CARD_SCALE, min(1.0, layout.table_rect.width() / 880, table_area_height / 520))

        name_font_size = max(8, int(10 * card_scale))
        action_font_size = max(7, int(9 * card_scale))

        panel_color, border, accent = action_colors(player.action, player.justacted)
        text = QColor("#f5f8fa") if player.action != "folds" else accent

        cards = self._visible_cards(player, street, is_final_frame)
        panel_above_cards = seat.panel_rect.center().y() < seat.cards_rect.center().y()
        if player.action == "folds":
            # Folded: muck the cards (slide toward the centre, rotate and fade).
            self._draw_folded_cards(painter, cards, seat, layout, self._fold_progress(player.name))
        elif is_final_frame and player.hole_run_colors:
            # Run-it: each hole card gets one outline per run it wins (nested).
            self._draw_cards_multi_outline(
                painter,
                cards,
                seat.cards_rect,
                player.hole_run_colors,
                lift_up=not panel_above_cards,
            )
        else:
            highlight = player.winning_cards if (is_final_frame and player.is_winner) else None
            self._draw_cards(
                painter,
                cards,
                seat.cards_rect,
                overlap=True,
                highlight=highlight,
                dim_others=bool(highlight),
                lift_up=not panel_above_cards,
            )

        # Draw-game discard: animate the discarded cards flying off to the muck.
        if player.discard_count:
            dprog = self._discard_progress(player.name)
            if dprog is not None:
                self._draw_discarded_cards(painter, player.discard_cards, player.discard_count, seat, layout, dprog)

        if player.justacted:
            focus_offset = int(5 * card_scale)
            focus_rect = seat.panel_rect.adjusted(-focus_offset, -focus_offset, focus_offset, focus_offset)
            painter.setPen(QPen(QColor(border.red(), border.green(), border.blue(), 90), int(7 * card_scale)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(focus_rect, 9, 9)

        painter.setPen(QPen(border, 2.2 if player.justacted else 1.4))
        painter.setBrush(panel_color)
        painter.drawRoundedRect(seat.panel_rect, 6, 6)

        painter.setPen(text)
        painter.setFont(QFont("Helvetica", name_font_size, QFont.Weight.Bold))
        stack_text = f"{player.name}  {format_replay_amount(player.stack, self.currency_code)}"
        name_rect = QRectF(
            seat.panel_rect.x() + 6,
            seat.panel_rect.y() + 2,
            seat.panel_rect.width() - 12,
            seat.panel_rect.height() * 0.48,
        )
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, stack_text)

        action_text = player.action or ""
        if player.justacted and player.action == "collected" and player.chips:
            action_text = f"collected {format_replay_amount(player.chips, self.currency_code)}"
        elif player.allin and player.action not in (None, "collected", "folds"):
            action_text = f"{action_text} all-in".strip()
        if is_final_frame and player.cashout is not None:
            action_text = f"cashout {format_replay_amount(player.cashout, self.currency_code)}"
        painter.setPen(accent if player.justacted else QColor("#9aa5ad"))
        painter.setFont(QFont("Helvetica", action_font_size, QFont.Weight.DemiBold))
        action_rect = QRectF(
            seat.panel_rect.x() + 6,
            seat.panel_rect.y() + seat.panel_rect.height() * 0.48,
            seat.panel_rect.width() - 12,
            seat.panel_rect.height() * 0.48,
        )
        painter.drawText(action_rect, Qt.AlignmentFlag.AlignCenter, action_text)

        if is_final_frame and player.combination:
            combo_font_size = max(9, int(10 * card_scale))
            combo_font = QFont("Helvetica", combo_font_size, QFont.Weight.Bold)
            metrics = QFontMetrics(combo_font)
            combo_text = player.combination
            pad_x, pad_y = 10, 5
            text_w = metrics.horizontalAdvance(combo_text)
            pill_w = text_w + pad_x * 2
            pill_h = metrics.height() + pad_y * 2
            center_x = seat.panel_rect.center().x()
            # Place the badge beyond the panel (away from the cards) so it never
            # overlaps them; if that would fall off-screen, place it on the other
            # side of the cards (toward the table centre) instead. Winning cards
            # are offset toward the centre, so the inner placement must clear
            # that offset too.
            card_h = getattr(self, "render_card_height", self.cardheight)
            lift = int(card_h * 0.18) + 4
            cards_above_panel = seat.cards_rect.center().y() < seat.panel_rect.center().y()
            usable_bottom = self.height() - CONTROL_RESERVED_HEIGHT
            if cards_above_panel:
                outer_top = seat.panel_rect.bottom() + 6
                inner_top = seat.cards_rect.top() - lift - pill_h - 6
            else:
                outer_top = seat.panel_rect.top() - pill_h - 6
                inner_top = seat.cards_rect.bottom() + lift + 6
            top = outer_top
            if top < HEADER_HEIGHT + 2 or top + pill_h > usable_bottom:
                top = inner_top
            top = max(HEADER_HEIGHT + 2, min(top, usable_bottom - pill_h))
            combo_rect = QRectF(center_x - pill_w / 2, top, pill_w, pill_h)
            is_win = player.is_winner
            painter.setPen(QPen(QColor("#ffd34d") if is_win else QColor(120, 130, 138), 1.4))
            painter.setBrush(QColor(18, 26, 16, 235) if is_win else QColor(10, 14, 18, 230))
            painter.drawRoundedRect(combo_rect, pill_h / 2, pill_h / 2)
            painter.setPen(QColor("#ffd34d") if is_win else QColor("#c4cdd4"))
            painter.setFont(combo_font)
            painter.drawText(combo_rect, Qt.AlignmentFlag.AlignCenter, combo_text)

        if player.chips and player.action != "collected":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(8, 12, 15, 205))
            painter.drawRoundedRect(seat.bet_rect, 8, 8)
            painter.setPen(QColor("#ffe769"))
            painter.setFont(QFont("Helvetica", name_font_size, QFont.Weight.Bold))
            painter.drawText(
                seat.bet_rect,
                Qt.AlignmentFlag.AlignCenter,
                format_replay_amount(player.chips, self.currency_code),
            )

        if getattr(self.replay_model.hand, "buttonpos", 0) == player.seat and not self.dealer.isNull():
            dealer_size = max(24, int(DEALER_BUTTON_BASE_SIZE * card_scale))
            dealer_rect = QRectF(
                seat.dealer_pos.x() - dealer_size / 2,
                seat.dealer_pos.y() - dealer_size / 2,
                dealer_size,
                dealer_size,
            )
            painter.drawImage(
                dealer_rect.toRect(),
                self.dealer.scaled(dealer_size, dealer_size, Qt.AspectRatioMode.KeepAspectRatio),
            )

    def _timeline_entries(self, max_entries: int = 10) -> list[str]:
        entries = []
        states_shown = self.states[: self.stateSlider.value() + 1]
        for state in states_shown:
            for player in state.players.values():
                if player.justacted and player.action:
                    allin_suffix = " (all-in)" if player.allin and player.action != "collected" else ""
                    if player.action == "collected" and player.chips:
                        entries.append(
                            f"{player.name}: collected {format_replay_amount(player.chips, self.currency_code)}"
                        )
                    elif player.chips and player.action not in {"folds", "checks"}:
                        amount = format_replay_amount(player.chips, self.currency_code)
                        entries.append(f"{player.name}: {player.action} {amount}{allin_suffix}")
                    else:
                        entries.append(f"{player.name}: {player.action}{allin_suffix}")
        # At the showdown frame, append each revealed combination and any cashout.
        if states_shown and getattr(states_shown[-1], "ended", False):
            hand = self.replay_model.hand
            showdown_strings = getattr(hand, "showdownStrings", {}) or {}
            collectees = getattr(hand, "collectees", {}) or {}
            for name, combo in showdown_strings.items():
                if not combo:
                    continue
                suffix = " (wins)" if name in collectees else ""
                entries.append(f"{name}: {combo}{suffix}")
            for name, amount in (getattr(hand, "cashOutAmounts", {}) or {}).items():
                entries.append(f"{name}: cashout {format_replay_amount(amount, self.currency_code)}")
        return entries[-max_entries:]

    def _current_action_summary(self, frame: ReplayFrame) -> str:
        acted = [player for player in frame.players if player.justacted and player.action]
        if not acted:
            return "Start of hand"
        player = acted[-1]
        allin_suffix = " (all-in)" if player.allin and player.action != "collected" else ""
        if player.action == "collected" and player.chips:
            return f"{player.name} collected {format_replay_amount(player.chips, self.currency_code)}"
        if player.chips and player.action not in {"folds", "checks"}:
            amount = format_replay_amount(player.chips, self.currency_code)
            return f"{player.name} {player.action} {amount}{allin_suffix}"
        return f"{player.name} {player.action}{allin_suffix}"

    def _next_actor_name(self, current_index: int) -> str | None:
        for state in self.states[current_index + 1 :]:
            for player in state.players.values():
                if player.justacted and player.action:
                    return player.name
        return None

    def _hero_odds_summary(self, frame: ReplayFrame, current_index: int) -> str:
        if self._next_actor_name(current_index) != self.Heroes:
            return ""
        hero = next((player for player in frame.players if player.name == self.Heroes), None)
        if hero is None:
            return ""
        call_amount = max((player.chips for player in frame.players), default=Decimal(0)) - hero.chips
        if call_amount <= 0 or frame.pot <= 0:
            return ""
        pot_after_call = frame.pot + call_amount
        if pot_after_call <= 0:
            return ""
        equity_needed = (call_amount / pot_after_call) * Decimal(100)
        summary = (
            f"Hero call {format_replay_amount(call_amount, self.currency_code)} · "
            f"pot odds {format_number(equity_needed, 1)}%"
        )
        hand = self.replay_model.hand
        category = hand.gametype.get("category", "")
        game_info = Card.games.get(category)
        game = game_info[1] if game_info else None
        if not game:
            return summary
        cache: dict[Any, Decimal | None] = getattr(self, "_equity_cache", None) or {}
        self._equity_cache = cache
        key = (
            game,
            tuple((player.name, tuple(player.holecards), player.action) for player in frame.players),
            tuple(sorted(frame.render_board)),
            tuple((street, tuple(frame.board.get(street) or [])) for street in ("FLOP", "TURN", "RIVER")),
        )
        if key not in cache:
            cache[key] = replay_hero_equity(frame, self.Heroes, game)
        equity = cache[key]
        if equity is not None:
            equity_pct = equity * Decimal(100)
            edge = equity_pct - equity_needed
            summary += f" · equity {format_number(equity_pct, 1)}% · edge {format_number(edge, 1, show_plus=True)} pts"
        return summary

    def _draw_summary(self, painter: QPainter, frame: ReplayFrame, layout: ReplayLayout, current_index: int) -> None:
        summary_width = min(620, max(300, layout.table_rect.width() * 0.46))
        if layout.timeline_rect.isNull():
            x = self.width() - summary_width - 28
        else:
            x = layout.timeline_rect.x() - summary_width - 16
        x = max(28, x)
        rect = QRectF(x, 14, summary_width, 64)
        painter.setPen(QPen(QColor("#46505a"), 1))
        painter.setBrush(QColor("#171d22"))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#eef3f7"))
        painter.drawText(
            rect.adjusted(12, 8, -12, -34),
            Qt.AlignmentFlag.AlignLeft,
            self._current_action_summary(frame),
        )
        odds = self._hero_odds_summary(frame, current_index)
        painter.setFont(QFont("Helvetica", 9, QFont.Weight.DemiBold))
        painter.setPen(QColor("#ffe769") if odds else QColor("#9aa5ad"))
        painter.drawText(
            rect.adjusted(12, 32, -12, -8),
            Qt.AlignmentFlag.AlignLeft,
            odds or "Use arrows/space to review decisions",
        )

    def _draw_timeline(self, painter: QPainter, layout: ReplayLayout) -> None:
        if layout.timeline_rect.isNull():
            return
        painter.setPen(QPen(QColor("#46505a"), 1))
        painter.setBrush(QColor("#171d22"))
        painter.drawRoundedRect(layout.timeline_rect, 7, 7)
        painter.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        painter.setPen(QColor("#eef3f7"))
        painter.drawText(layout.timeline_rect.adjusted(14, 12, -14, -12), Qt.AlignmentFlag.AlignTop, "Action timeline")

        row_height = 32
        max_entries = max(4, int((layout.timeline_rect.height() - 54) // row_height))
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.Medium))
        y = layout.timeline_rect.y() + 44
        for index, entry in enumerate(self._timeline_entries(max_entries=max_entries)):
            entry_rect = QRectF(layout.timeline_rect.x() + 10, y, layout.timeline_rect.width() - 20, row_height - 4)
            action = entry.split(": ", 1)[1] if ": " in entry else entry
            if index % 2 == 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#20272d"))
                painter.drawRoundedRect(entry_rect, 4, 4)
            painter.setPen(action_colors(action.split(" ", 1)[0])[2])
            painter.drawText(
                entry_rect.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                entry,
            )
            y += row_height

    def paintEvent(self, event) -> None:  # noqa: F811
        if not getattr(self, "states", None):
            return
        if not getattr(self, "replay_model", None):
            return
        self._ensure_replayer_assets()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if getattr(self, "replay_mode", "hand") == "ofc":
            self._paint_ofc_replay(painter)
            return
        state = self.states[self.stateSlider.value()]
        frame = self._frame_from_state(state)
        frame.players = order_players_clockwise(frame.players, self.Heroes)
        player_names = [player.name for player in frame.players]
        category = self.replay_model.hand.gametype.get("category", "")
        layout = build_replay_layout(self.width(), self.height(), player_names, self.Heroes, category)
        self.render_card_width = layout.card_width
        self.render_card_height = layout.card_height
        self.render_card_spacing = layout.card_spacing
        is_final_frame = self.stateSlider.value() == self.stateSlider.maximum()

        self._draw_table(painter, layout)
        self._draw_header(painter)
        self._draw_summary(painter, frame, layout, self.stateSlider.value())
        self._draw_board(painter, frame, layout)
        for player in frame.players:
            seat = layout.seats.get(player.name)
            if seat is not None:
                self._draw_player(painter, player, seat, layout, frame.street, is_final_frame)
        self._draw_timeline(painter, layout)

    def play_hand(self, handidx) -> None:  # noqa: F811
        if handidx < 0 or handidx >= len(self.handlist):
            return
        self._apply_replayer_style()
        self.handidx = handidx
        entry = self.handlist[handidx]
        is_ofc = self._is_ofc_replay_entry(entry)
        self.replay_mode = "ofc" if is_ofc else "hand"
        if is_ofc:
            ofc_hand = self._load_ofc_replay_entry(entry)
            self.currency = ""
            self.currency_code = "play"
            self.Heroes = ""
            self.replay_model = self._build_ofc_replay_model(ofc_hand)
        else:
            hand = Hand.hand_factory(entry, self.conf, self.db)
            self.currency = hand.sym
            self.currency_code = str(hand.gametype.get("currency", "USD"))
            self.Heroes = hand.hero or self._resolve_hero(hand.sitename)
            self.replay_model = self._build_replay_model(hand)
        self.info = self.replay_model.info
        self.states = self.replay_model.states

        for idx in reversed(list(range(self.buttonBox.count()))):
            item = self.buttonBox.takeAt(idx)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.streetButtons = {}
        self.buttonBox.addStretch()
        if is_ofc:
            button_names = [f"ROUND{index + 1}" for index in range(len(self.states))]
        else:
            button_names = replay_button_streets(hand)
        for street in button_names:
            if is_ofc:
                try:
                    label = self._ofc_state_label(self.states[int(street.replace("ROUND", "")) - 1])
                except (ValueError, IndexError):
                    label = street.replace("ROUND", "Step ")
            else:
                label = street.capitalize()
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, s=street: self.street_clicked(checked, s))
            btn.setEnabled(street in self.replay_model.seen_streets)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setProperty("streetActive", False)
            self.streetButtons[street] = btn
            self.buttonBox.addWidget(btn)
        self.buttonBox.addStretch()

        self.stateSlider.setMaximum(max(0, len(self.states) - 1))
        self.stateSlider.setValue(0)
        self._sync_replayer_controls()
        self.update()

    def increment_state(self) -> None:  # noqa: F811
        if self.stateSlider.value() >= self.stateSlider.maximum():
            self.playing = False
            self.playPauseButton.setText("Play")
            if getattr(self, "playTimer", None):
                self.playTimer.stop()
            return
        if self.playing:
            self.stateSlider.setValue(self.stateSlider.value() + 1)

    _FOLD_DURATION = 0.45  # seconds

    def slider_changed(self, value) -> None:  # noqa: F811
        if getattr(self, "states", None):
            self._sync_replayer_controls()
            self._maybe_start_fold_animation(value)
        self.update()

    def _maybe_start_fold_animation(self, value) -> None:
        """Trigger fold (muck) and draw (discard) animations for this frame."""
        if getattr(self, "replay_mode", "hand") == "ofc":
            return
        if value == self._fold_anim_value:
            return
        self._fold_anim_value = value
        states = getattr(self, "states", None)
        if not states or value < 0 or value >= len(states):
            return
        state = states[value]
        now = time.monotonic()
        started = False
        for p in state.players.values():
            if not getattr(p, "justacted", False):
                continue
            action = getattr(p, "action", None) or ""
            if action == "folds":
                self._fold_anim[p.name] = now
                started = True
            elif action.startswith("discards") and getattr(p, "discardCount", 0):
                self._discard_anim[p.name] = now
                started = True
        if started and not self._fold_timer.isActive():
            self._fold_timer.start(16)

    def _fold_tick(self) -> None:
        now = time.monotonic()
        self._fold_anim = {n: t for n, t in self._fold_anim.items() if now - t < self._FOLD_DURATION}
        self._discard_anim = {n: t for n, t in self._discard_anim.items() if now - t < self._FOLD_DURATION}
        self.update()
        if not self._fold_anim and not self._discard_anim:
            self._fold_timer.stop()

    def _fold_progress(self, name: str) -> float:
        t0 = self._fold_anim.get(name)
        if t0 is None:
            return 1.0
        return max(0.0, min(1.0, (time.monotonic() - t0) / self._FOLD_DURATION))

    def _discard_progress(self, name: str):
        t0 = self._discard_anim.get(name)
        if t0 is None:
            return None
        return max(0.0, min(1.0, (time.monotonic() - t0) / self._FOLD_DURATION))

    def play_clicked(self, checkState) -> None:  # noqa: F811
        self.playing = not self.playing
        if not getattr(self, "playTimer", None):
            self.playTimer = QTimer()
            self.playTimer.timeout.connect(self.increment_state)
        if self.playing:
            self.playPauseButton.setText("Pause")
            self.playTimer.start(700)
        else:
            self.playPauseButton.setText("Play")
            self.playTimer.stop()

    def keyPressEvent(self, event) -> None:  # noqa: F811
        if event.key() == Qt.Key.Key_Left:
            self.stateSlider.setValue(max(0, self.stateSlider.value() - 1))
        elif event.key() == Qt.Key.Key_Right:
            self.stateSlider.setValue(min(self.stateSlider.maximum(), self.stateSlider.value() + 1))
        elif event.key() == Qt.Key.Key_Space:
            self.play_clicked(False)
        elif event.key() == Qt.Key.Key_Home:
            self.stateSlider.setValue(0)
        elif event.key() == Qt.Key.Key_End:
            self.stateSlider.setValue(self.stateSlider.maximum())
        elif event.key() == Qt.Key.Key_Up:
            if self.handidx < len(self.handlist) - 1:
                self.play_hand(self.handidx + 1)
        elif event.key() == Qt.Key.Key_Down:
            if self.handidx > 0:
                self.play_hand(self.handidx - 1)
        else:
            QWidget.keyPressEvent(self, event)

    def start_clicked(self, checkState) -> None:
        self.stateSlider.setValue(0)

    def end_clicked(self, checkState) -> None:
        self.stateSlider.setValue(self.stateSlider.maximum())

    def prev_clicked(self, checkState) -> None:
        self.stateSlider.setValue(max(0, self.stateSlider.value() - 1))

    def next_clicked(self, checkState) -> None:
        self.stateSlider.setValue(min(self.stateSlider.maximum(), self.stateSlider.value() + 1))

    def street_clicked(self, checkState, street) -> None:
        if getattr(self, "replay_mode", "hand") == "ofc" and str(street).startswith("ROUND"):
            try:
                self.stateSlider.setValue(max(0, min(self.stateSlider.maximum(), int(str(street)[5:]) - 1)))
            except ValueError:
                pass
            return
        for i, state in enumerate(self.states):
            if self._button_street_name(state.street) == self._button_street_name(street):
                self.stateSlider.setValue(i)
                break


# ICM code originally grabbed from http://svn.gna.org/svn/pokersource/trunk/icm-calculator/icm-webservice.py
# Copyright (c) 2008 Thomas Johnson <tomfmason@gmail.com>


class ICM:
    def __init__(self, stacks, payouts) -> None:
        self.stacks = stacks
        self.payouts = payouts
        self.equities: list[Decimal] = []
        self.prepare()

    def prepare(self) -> None:
        total = sum(self.stacks)
        for k in self.stacks:
            self.equities.append(round(Decimal(str(self.getEquities(total, k, 0))), 4))

    def getEquities(self, total, player, depth):
        D = Decimal
        eq = D(self.stacks[player]) / total * D(str(self.payouts[depth]))
        if depth + 1 < len(self.payouts):
            i = 0
            for stack in self.stacks:
                if i != player and stack > 0.0:
                    self.stacks[i] = 0.0
                    eq += self.getEquities((total - stack), player, (depth + 1)) * ((stack) // (D(total)))
                    self.stacks[i] = stack
                i += 1
        return eq


class TableState:
    def __init__(self, hand) -> None:
        self.pot = Decimal(0)
        self.street: str | None = None
        self.board = hand.board
        self.renderBoard: set[str] = set()
        self.bet = Decimal(0)
        self.called = Decimal(0)
        self.gametype = hand.gametype["category"]
        self.gamebase = hand.gametype["base"]
        self.allin = False
        self.allinThisStreet = False
        self.ended = False
        self.newpot = Decimal()
        # NOTE: Need a useful way to grab payouts
        # self.icm = ICM(stacks,payouts)
        # print icm.equities

        self.players = {}
        # print ('hand.players', hand.players)
        # print (type(hand.players))
        # print (type(self.players))
        # for name, chips, seat in hand.players[-1]:
        #     self.players.append(Player(name, chips, seat))
        #     #  self.players[name] = Player(hand, name, chips, seat)
        for items in hand.players:
            # print (items)
            # print ('type', (type(items)))
            # print (items[0])
            # print (items[1])
            # print (items[2])
            # print (items[3])

            self.players[items[1]] = Player(hand, items[1], items[2], int(items[0]))
            log.debug(f"Items player: {self.players[items[1]]}")

    def startPhase(self, phase) -> None:
        self.street = phase
        self.newpot = self.newpot
        if phase in ("BLINDSANTES", "PREFLOP", "DEAL"):
            return

        self.renderBoard.add(phase)

        for player in list(self.players.values()):
            player.justacted = False
            if player.chips > self.called:
                player.stack += player.chips - self.called
                player.chips = self.called
            self.pot += player.chips

            player.chips = Decimal(0)
            if phase in ("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"):
                player.holecards = player.streetcards[self.street]
        self.bet = Decimal(0)
        self.called = Decimal(0)
        self.allinThisStreet = False

    def updateForAction(self, action) -> None:
        for player in list(self.players.values()):
            player.justacted = False

        player = self.players[action[0]]
        player.action = action[1]
        player.justacted = True
        if action[1] == "folds" or action[1] == "checks":
            if action[1] == "folds":
                player.folded = True
        elif action[1] == "raises" or action[1] == "bets":
            if self.allinThisStreet:
                self.called = Decimal(self.bet)
            else:
                self.called = Decimal(0)
            diff = self.bet - player.chips
            self.bet += action[2]
            player.chips += action[2] + diff
            player.stack -= action[2] + diff
            self.newpot += action[2] + diff
        elif action[1] == "big blind":
            self.bet = action[2]
            player.chips += action[2]
            player.stack -= action[2]
            self.newpot += action[2]
        elif action[1] == "calls" or action[1] == "small blind" or action[1] == "secondsb":
            player.chips += action[2]
            player.stack -= action[2]
            self.called = max(self.called, player.chips)
            self.newpot += action[2]
        elif action[1] == "both":
            player.chips += action[2]
            player.stack -= action[2]
            self.newpot += action[2]
        elif action[1] == "ante":
            self.pot += action[2]
            player.stack -= action[2]
            self.newpot += action[2]
        elif action[1] == "discards":
            player.action = (player.action or "") + " " + str(action[2])
            try:
                player.discardCount = int(action[2])
            except (TypeError, ValueError):
                player.discardCount = 0
            if len(action) > 3 and action[3]:
                cards = action[3]
                player.discardCards = cards.split() if isinstance(cards, str) else list(cards)
                # Must be hero as we have discard information.  Update holecards now.
                player.holecards = player.streetcards[self.street]
            else:
                player.discardCards = []
        elif action[1] == "stands pat":
            pass
        elif action[1] == "bringin":
            self.bet = action[2]
            player.chips += action[2]
            player.stack -= action[2]
            self.newpot += action[2]
        else:
            log.warning(f"unhandled action: {action!s}")

        if player.stack == 0 and action[1] not in ("folds", "checks", "discards", "stands pat"):
            self.allinThisStreet = True
            player.allin = True

    def computePots(self) -> list[tuple[str, Decimal]]:
        """Split the money committed so far into main/side pots.

        Returns a list of (label, amount) tuples. A genuine split into
        "Main pot" and "Side pot N" is only produced when a still-contending
        player is all-in for less than another player's contribution: an
        all-in player caps the pot they can win, so chips committed beyond
        that cap form a side pot they cannot contest. Players who are merely
        behind in the current betting round (still live, with chips left) do
        NOT create a side pot -- they are presumed able to match the bet, so
        an uneven, mid-street betting state stays a single pot. Each player's
        contribution is the chips that have left their stack; folded players'
        money stays in the pot as dead money but they are not eligible to win.
        A layer with a single contributor is an uncalled bet and is excluded
        (it is returned to the bettor).
        """
        if self.ended:
            # Money has been pushed to the winner(s); the central pot is empty.
            return [("Pot", Decimal(0))]

        contributions = {}
        for name, p in self.players.items():
            committed = p.startStack - p.stack
            if committed > 0:
                contributions[name] = committed

        total = sum(contributions.values())
        if not contributions:
            return [("Pot", self.newpot)]

        folded = {name for name, p in self.players.items() if p.folded}

        # Only a non-folded all-in player caps a pot; a live player who is
        # simply behind in the betting round does not. Without any such cap
        # the whole thing is one pot.
        cap_levels = sorted(
            {
                contributions[name]
                for name, p in self.players.items()
                if p.allin and not p.folded and name in contributions
            },
        )
        if not cap_levels:
            return [("Pot", Decimal(total))]

        # Pot boundaries are the all-in caps, plus the overall top so that any
        # chips committed above the highest cap (e.g. a live player betting
        # beyond an all-in) land in their own layer.
        boundaries = list(cap_levels)
        top = max(contributions.values())
        if boundaries[-1] < top:
            boundaries.append(top)

        layers: list[list[Any]] = []
        prev = Decimal(0)
        for level in boundaries:
            contributors = [c for c in contributions.values() if c > prev]
            amount = sum(min(c, level) - prev for c in contributors)
            eligible = frozenset(n for n, c in contributions.items() if c > prev and n not in folded)
            prev = level
            if len(contributors) <= 1:
                # Only one player committed into this layer: uncalled bet, returned.
                continue
            if amount > 0:
                layers.append([amount, eligible])

        # Merge adjacent layers that share the same set of eligible winners.
        merged: list[list[Any]] = []
        for amount, eligible in layers:
            if merged and merged[-1][1] == eligible:
                merged[-1][0] += amount
            else:
                merged.append([amount, eligible])

        if not merged:
            return [("Pot", Decimal(total))]
        if len(merged) == 1:
            # Single contended pot (uncalled bets, if any, were excluded above).
            return [("Pot", merged[0][0])]

        result: list[tuple[str, Decimal]] = [("Main pot", Decimal(merged[0][0]))]
        for index, (amount, _eligible) in enumerate(merged[1:], start=1):
            result.append((f"Side pot {index}", amount))
        return result

    def endHand(self, collectees, returned) -> None:
        self.pot = Decimal(0)
        self.ended = True
        for player in list(self.players.values()):
            player.justacted = False
            player.chips = Decimal(0)
            if self.gamebase == "draw":
                # Fall back to the player's current holecards if the final street
                # has no per-street draw cards (e.g. the hand ended before a draw).
                player.holecards = player.streetcards.get(self.street, player.holecards)
        for name, amount in list(collectees.items()):
            player = self.players[name]
            player.chips += amount
            player.action = "collected"
            player.justacted = True
        for name, amount in list(returned.items()):
            self.players[name].stack += amount


class Player:
    def __init__(self, hand, name, stack, seat) -> None:
        self.stack = Decimal(stack)
        self.startStack = Decimal(stack)
        self.chips = Decimal(0)
        self.seat = seat
        self.name = name
        self.action: str | None = None
        self.justacted = False
        self.allin = False
        self.folded = False
        self.discardCount = 0
        self.discardCards: list[str] = []
        self.holecards = hand.join_holecards(name, asList=True)
        self.streetcards = {}
        if hand.gametype["base"] == "draw":
            for street in hand.actionStreets[1:]:
                self.streetcards[street] = hand.join_holecards(
                    name,
                    asList=True,
                    street=street,
                )
            self.holecards = self.streetcards[hand.actionStreets[1]]
        elif hand.gametype["base"] == "stud":
            for i, street in enumerate(hand.actionStreets[1:]):
                self.streetcards[street] = self.holecards[: i + 3]
            self.holecards = self.streetcards[hand.actionStreets[1]]
        log.debug(f"Seat: {seat}")
        self.x = 0.5 * cos(2 * self.seat * pi / hand.maxseats)
        self.y = 0.8 * sin(2 * self.seat * pi / hand.maxseats)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Launch the replayer GUI like the original
    config = Configuration.Config()
    sql = SQL.Sql(db_server=config.get_db_parameters()["db-server"])

    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    handlist = [10, 39, 40]
    replayer = GuiReplayer(config, sql, None, handlist)
    replayer.play_hand(0)

    app.exec()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
