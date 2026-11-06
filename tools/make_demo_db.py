#!/usr/bin/env python3
"""Build a throwaway database of invented hands, safe to screenshot.

Every screenshot published to the wiki shows a database, and a real database
shows the people the user played against. Neither the golden fixtures nor the
regression corpus solve that -- both carry genuine screen names -- so this
invents the hands instead: a fixed roster of obviously fictional players, dealt
by a seeded generator, imported into a database of its own.

    python tools/make_demo_db.py                    # ~/fpdb-demo, 2000 hands
    python tools/make_demo_db.py --hands 5000 --out /tmp/shots

It leaves a directory holding the generated hand histories, a SQLite database
with them imported, and a configuration file pointing at that database. Launch
fpdb against it and every screen -- reports, graphs, replayer, HUD popups --
can be captured with no redaction at all:

    python fpdb_3_legacy/fpdb.pyw -c ~/fpdb-demo/HUD_config.xml

The real ``HUD_config.xml`` is copied, never written to: the copy is what gets
repointed at the demo database, so the reader's own setup is untouched.

What the generated hands are, and are not
-----------------------------------------
No-limit Hold'em 6-max cash, one stake, players with fixed and distinct styles
so the statistics separate the way they do in life -- a nit next to a maniac,
not fifteen players all at 24/18. The pot arithmetic is exact and the showdowns
are adjudicated by a real evaluator, so the imported statistics are internally
consistent.

The players also *play position*: each style opens wider toward the button,
three-bets and squeezes at a rate of its own, folds or raises against a c-bet,
and barrels the turn and river as its name suggests. That is not realism for
its own sake. The analytics views this corpus exists to demonstrate -- RFI by
position, facing a three-bet, squeeze, c-bet response, sizing buckets, turn and
river continuation -- are questions about exactly those behaviours, and a
corpus that never three-bets leaves those screens empty. Bets come from a small
menu of sizes rather than a continuous range, for the same reason: the sizing
analysis buckets bets, so arbitrary sizes would fill one bucket and leave the
others bare.

Deliberately not modelled: all-ins and side pots (stacks are deep and bet sizes
clamped well below them), tournaments, and any game but Hold'em. They add engine
complexity the screenshots do not need. Wanting a screenshot of a tournament
report is a reason to extend this, not to fall back on real hands.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RANKS = "23456789TJQKA"
SUITS = "shdc"
RANK_VALUE = {rank: index for index, rank in enumerate(RANKS, start=2)}

SMALL_BLIND = 0.05
BIG_BLIND = 0.10
STARTING_STACK = 20.00
"""200 big blinds, reset every hand. Deep enough that clamped bet sizes never
reach a stack, which is what keeps side pots out of the generator."""

RAKE_RATE = 0.05
RAKE_CAP = 0.50

MAX_SEATS = 6
HERO = "Hero"

# The seats named as poker names them, indexed by how far the seat sits from the
# button: index 0 is the button itself, then the two blinds, then the seats in
# acting order. ``_position`` indexes this with ``(seat - button) % players``,
# which is what makes the order of this tuple load-bearing -- read backwards it
# names every seat one place off, and the position statistics then describe the
# player to the left of the one they claim. The tables below are keyed by these
# names, so a different table size would be one tuple here and nothing else.
POSITIONS = ("BTN", "SB", "BB", "UTG", "HJ", "CO")

# How position bends a style. A nit still opens less under the gun than on the
# button, the blinds defend rather than open, and a seat with position defends
# its c-bet-calling range wider -- which is what gives the position views
# something to separate.
OPEN_FACTOR = {"UTG": 0.70, "HJ": 0.88, "CO": 1.00, "BTN": 1.30, "SB": 1.05, "BB": 0.0}
THREE_BET_FACTOR = {"UTG": 0.55, "HJ": 0.72, "CO": 0.95, "BTN": 1.12, "SB": 1.00, "BB": 1.28}
FOLD_TO_CBET_FACTOR = {"UTG": 1.00, "HJ": 1.00, "CO": 0.94, "BTN": 0.82, "SB": 1.08, "BB": 1.12}

# A raise that already has a cold caller behind it is a squeeze: there is dead
# money in the pot, so the same player takes it more often than a plain 3-bet.
SQUEEZE_MULTIPLIER = 1.5

# The open-raise size in big blinds, by position. Wider ranges on the button are
# raised smaller, and the sizing analysis sees more than one size because of it.
OPEN_SIZE_BB = {"UTG": 3.0, "HJ": 2.8, "CO": 2.5, "BTN": 2.3, "SB": 3.0, "BB": 3.0}

# The sizes a bet may take, as multipliers of the pot it faces, and how often
# each is drawn. A menu, not a smooth random size: the sizing analysis buckets
# bets into "third pot", "half pot", "three quarters", and arbitrary sizes
# would leave two of those buckets empty.
BET_SIZES = (0.33, 0.5, 0.66, 0.75, 1.0)
BET_SIZE_WEIGHTS = (3, 4, 3, 2, 1)


@dataclass(frozen=True)
class Style:
    """One invented player: the tendencies every decision of theirs is drawn from.

    Every field is the *frequency* of taking that action when the spot offers
    it, so a player is defined by how often they do a thing rather than by how
    they play a particular holding. That is what makes the corpus a statistics
    demo: a few dozen hands in, a player's VPIP has converged on their
    ``vpip``, and the HUD screenshots show contrast rather than six regulars.
    """

    name: str
    vpip: float
    """Plays an unopened pot at all, before position widens the range."""
    pfr: float
    """Total preflop aggressor rate, and the rate of opening when first in."""
    three_bet: float
    """Re-raises a single raise, when given the chance."""
    four_bet: float
    """Re-raises a three-bet after having opened, or cold four-bets without."""
    cbet_flop: float
    """Bets the flop as the preflop aggressor and the action checks to them."""
    barrel_turn: float
    """Bets the turn after having bet the flop."""
    barrel_river: float
    """Bets the river after having bet the turn."""
    fold_to_cbet: float
    """Folds when facing the flop continuation bet."""
    raise_facing_bet: float
    """Raises rather than calls when facing a bet on any street."""
    probe_turn: float
    """Bets the turn after the preflop aggressor checked the flop."""
    aggression: float
    """Appetite to bet when checked to and nothing more specific applies."""


HERO_STYLE = Style(
    name=HERO,
    vpip=0.25,
    pfr=0.21,
    three_bet=0.07,
    four_bet=0.09,
    cbet_flop=0.62,
    barrel_turn=0.55,
    barrel_river=0.45,
    fold_to_cbet=0.48,
    raise_facing_bet=0.11,
    probe_turn=0.35,
    aggression=0.55,
)

# Invented players with invented tendencies, spread out so a HUD screenshot
# shows contrast: a nit next to a maniac, a station who never folds next to a
# triple-barreller, two of everything in between. The names are absurd on
# purpose; nothing here can be mistaken for a real screen name.
ROSTER = (
    Style("NitPickerNed", 0.13, 0.11, 0.045, 0.11, 0.68, 0.36, 0.28, 0.62, 0.06, 0.22, 0.34),
    Style("CallingStation", 0.58, 0.04, 0.020, 0.01, 0.30, 0.18, 0.10, 0.30, 0.02, 0.12, 0.10),
    Style("MonsieurRegular", 0.24, 0.19, 0.065, 0.08, 0.62, 0.52, 0.42, 0.48, 0.10, 0.34, 0.55),
    Style("LoosePassivePat", 0.46, 0.09, 0.035, 0.02, 0.40, 0.25, 0.16, 0.38, 0.04, 0.18, 0.20),
    Style("TripleBarrelTom", 0.29, 0.25, 0.105, 0.11, 0.74, 0.68, 0.60, 0.40, 0.16, 0.48, 0.80),
    Style("ManiacMarcel", 0.67, 0.44, 0.160, 0.14, 0.80, 0.70, 0.58, 0.28, 0.22, 0.55, 0.72),
    Style("SolidSam", 0.21, 0.17, 0.060, 0.08, 0.60, 0.48, 0.38, 0.52, 0.09, 0.32, 0.50),
    Style("FishyFrancis", 0.52, 0.07, 0.030, 0.015, 0.34, 0.20, 0.12, 0.34, 0.03, 0.15, 0.15),
    Style("SqueezeQueen", 0.26, 0.22, 0.145, 0.10, 0.66, 0.56, 0.46, 0.44, 0.13, 0.40, 0.66),
    Style("RockRoland", 0.15, 0.12, 0.050, 0.09, 0.64, 0.34, 0.26, 0.60, 0.07, 0.24, 0.40),
    Style("SplashySteve", 0.61, 0.31, 0.120, 0.10, 0.72, 0.58, 0.48, 0.32, 0.18, 0.46, 0.58),
    Style("GrindGaston", 0.23, 0.18, 0.062, 0.075, 0.58, 0.50, 0.40, 0.50, 0.10, 0.33, 0.52),
)

@dataclass(frozen=True)
class HeroDeviation:
    """One way the demo hero is deliberately unlike the field (#371).

    The Study Explorer's *Biggest Differences vs Field* page is only worth
    demonstrating on a corpus where the hero actually differs -- and only worth
    trusting as a demo if the differences are stated rather than stumbled on.
    Each entry names the tendency, which way it points, and where in the
    shipped studies a reader will meet it.

    ``minimum`` is the gap the corpus guarantees between the hero's value and
    the roster's mean, in the same units as :class:`Style`. It is a floor, not
    a prediction: the observed frequency also moves with position, with who
    was dealt in, and with the cards, which is exactly the lesson the
    *Reading differences* guide is there to teach.
    """

    stat: str
    """The :class:`Style` field the tendency lives in."""
    direction: str
    """``"above"`` or ``"below"`` the field's mean."""
    minimum: float
    """How far apart the hero and the roster mean are, at least."""
    headline: str
    """What a reader should see, in the words the page uses."""
    study: str
    """The shipped study where the difference shows up."""


#: The deviations the demo corpus encodes on purpose. Changing a style without
#: updating this table fails a test, so the demo cannot quietly stop
#: demonstrating the thing it exists to demonstrate.
HERO_DEVIATIONS: Final[tuple[HeroDeviation, ...]] = (
    HeroDeviation(
        stat="vpip",
        direction="below",
        minimum=0.08,
        headline="The hero enters far fewer pots than the table does.",
        study="preflop_facing_open",
    ),
    HeroDeviation(
        stat="pfr",
        direction="above",
        minimum=0.02,
        headline="What the hero does play, the hero raises.",
        study="preflop_rfi",
    ),
    HeroDeviation(
        stat="barrel_turn",
        direction="above",
        minimum=0.08,
        headline="The hero keeps betting the turn when the field gives up.",
        study="srp_pfr_ip_flop",
    ),
    HeroDeviation(
        stat="barrel_river",
        direction="above",
        minimum=0.07,
        headline="And keeps betting the river.",
        study="srp_pfr_ip_flop",
    ),
    HeroDeviation(
        stat="fold_to_cbet",
        direction="above",
        minimum=0.03,
        headline="Facing a continuation bet, the hero folds more than the field.",
        study="srp_defender_oop_flop",
    ),
)

#: A tendency the hero and the field share, kept deliberately: a demo that
#: only ever shows large gaps teaches that every row is a finding. This one is
#: the counter-example the *Reading differences* guide points at.
HERO_AGREEMENT: Final[str] = "three_bet"


def field_mean(stat: str) -> float:
    """The roster's mean value for one tendency."""
    values = [getattr(style, stat) for style in ROSTER]
    return sum(values) / len(values)


def hero_gap(stat: str) -> float:
    """How far the hero sits from the field on one tendency."""
    return getattr(HERO_STYLE, stat) - field_mean(stat)


TABLE_NAMES = ("Wezen", "Alderamin", "Bellatrix", "Cursa", "Denebola", "Elnath")

HAND_CATEGORIES = (
    "high card",
    "a pair",
    "two pair",
    "three of a kind",
    "a straight",
    "a flush",
    "a full house",
    "four of a kind",
    "a straight flush",
)


# --------------------------------------------------------------------------
# cards
# --------------------------------------------------------------------------


def new_deck(rng: random.Random) -> list[str]:
    """A shuffled 52-card deck as ``Rs`` strings (``Ah``, ``Ts``...)."""
    deck = [rank + suit for rank in RANKS for suit in SUITS]
    rng.shuffle(deck)
    return deck


def _straight_high(values: list[int]) -> int | None:
    """Highest card of a straight inside ``values``, or None. Handles the wheel."""
    unique = sorted(set(values), reverse=True)
    if 14 in unique:
        unique.append(1)  # the ace plays low for A-5
    run = 1
    for index in range(1, len(unique)):
        if unique[index] == unique[index - 1] - 1:
            run += 1
            if run >= 5:
                return unique[index] + 4
        else:
            run = 1
    return None


def hand_rank(cards: list[str]) -> tuple[int, ...]:
    """Rank a 5-to-7-card hand; bigger tuples beat smaller ones.

    Returns ``(category, tiebreakers...)`` with category 8 for a straight flush
    down to 0 for a high card, so plain tuple comparison decides a showdown.
    """
    values = sorted((RANK_VALUE[card[0]] for card in cards), reverse=True)
    suit_counts = Counter(card[1] for card in cards)

    flush_suit = next((suit for suit, count in suit_counts.items() if count >= 5), None)
    if flush_suit is not None:
        flush_values = sorted((RANK_VALUE[c[0]] for c in cards if c[1] == flush_suit), reverse=True)
        straight_flush = _straight_high(flush_values)
        if straight_flush is not None:
            return (8, straight_flush)
        return (5, *flush_values[:5])

    straight = _straight_high(values)
    if straight is not None:
        return (4, straight)

    # Ranks grouped by how many of them there are, biggest group first.
    counts = Counter(values)
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    shape = [count for _, count in groups]
    ordered = [value for value, _ in groups]

    if shape[0] == 4:
        return (7, ordered[0], max(ordered[1:]))
    if shape[0] == 3 and len(shape) > 1 and shape[1] >= 2:
        return (6, ordered[0], ordered[1])
    if shape[0] == 3:
        return (3, ordered[0], *sorted(ordered[1:], reverse=True)[:2])
    if shape[0] == 2 and len(shape) > 1 and shape[1] == 2:
        return (2, *sorted(ordered[:2], reverse=True), max(ordered[2:]))
    if shape[0] == 2:
        return (1, ordered[0], *sorted(ordered[1:], reverse=True)[:3])
    return (0, *values[:5])


def describe(cards: list[str]) -> str:
    """The English name the client writes after a shown hand."""
    return HAND_CATEGORIES[hand_rank(cards)[0]]


def money(amount: float) -> str:
    """Format like the client does: ``$0.05``, ``$1.20``, ``$10``."""
    rounded = round(amount + 1e-9, 2)
    if abs(rounded - round(rounded)) < 0.005:
        return f"${int(round(rounded))}"
    return f"${rounded:.2f}"


# --------------------------------------------------------------------------
# the hand
# --------------------------------------------------------------------------


@dataclass(eq=False)
class Player:
    """One seat for the duration of one hand.

    Identity, not value: two seats are the same seat only when they are the
    same object, which is why this is ``eq=False`` -- every lookup in the
    writer (who raised, who checked) is an identity test.
    """

    style: Style
    seat: int
    stack: float = STARTING_STACK
    cards: list[str] = field(default_factory=list)
    street_bet: float = 0.0
    committed: float = 0.0
    folded: bool = False
    last_street_seen: int = 0
    """0 preflop, 1 flop, 2 turn, 3 river -- what the summary line reports."""
    bet_streets: set[int] = field(default_factory=set)
    """Streets on which this player bet or raised, for the barrel frequencies."""
    checked_streets: set[int] = field(default_factory=set)
    """Streets on which this player checked, which is what opens a probe."""

    @property
    def name(self) -> str:
        return self.style.name


class HandWriter:
    """Plays one hand out and renders it as a PokerStars hand history."""

    def __init__(self, rng: random.Random, players: list[Player], button: int, table: str) -> None:
        self.rng = rng
        self.players = players
        self.button = button  # index into self.players
        self.table = table
        self.lines: list[str] = []
        self.board: list[str] = []
        self.pot = 0.0
        # Context the later streets need. The opener is who made it two bets
        # preflop (the player whose 3-bet defence the analytics care about);
        # the aggressor is the last raiser on the street being played, and the
        # preflop aggressor is the one the flop c-bet belongs to.
        self.street = 0
        """0 preflop, 1 flop, 2 turn, 3 river."""
        self.opener: Player | None = None
        self.aggressor: Player | None = None
        self.preflop_aggressor: Player | None = None
        self.sequence: list[tuple[Player, str]] = []
        """This street's actions so far, in order: what a squeeze is read from."""

    # -- betting ---------------------------------------------------------

    @property
    def live(self) -> list[Player]:
        return [player for player in self.players if not player.folded]

    def _order(self, *, preflop: bool) -> list[Player]:
        """Players in acting order: UTG first preflop, small blind first after."""
        offset = 3 if preflop else 1
        start = (self.button + offset) % len(self.players)
        return [self.players[(start + step) % len(self.players)] for step in range(len(self.players))]

    def _position(self, player: Player) -> str:
        """The seat's poker name: SB and BB first, then UTG, HJ, CO and BTN."""
        return POSITIONS[(self.players.index(player) - self.button) % len(self.players)]

    def _cold_callers_since_raise(self) -> int:
        """How many players have cold-called the last raise on this street.

        Read from the action sequence rather than tracked separately, so the
        counter cannot disagree with what was written to the hand history: a
        caller who called *before* the raise is a limper, not a squeeze.
        """
        callers = 0
        for player, action in self.sequence:
            if player is self.aggressor:
                callers = 0
            elif action == "call":
                callers += 1
        return callers

    def _commit(self, player: Player, target: float) -> float:
        """Move ``player``'s street total up to ``target``. Returns what was added."""
        added = round(target - player.street_bet, 2)
        player.street_bet = round(target, 2)
        player.stack = round(player.stack - added, 2)
        player.committed = round(player.committed + added, 2)
        self.pot = round(self.pot + added, 2)
        return added

    def _run_street(self, current_bet: float, *, preflop: bool) -> bool:
        """Run one betting round. Returns True when more than one player is left.

        ``pending`` holds the indices, into the acting order, of players who
        still owe an action. A bet or raise refills it with everyone else still
        in the hand, which is exactly the rule that reopens the action.
        """
        order = self._order(preflop=preflop)
        size = len(order)
        raises = 1 if preflop else 0
        pending = [index for index in range(size) if not order[index].folded]
        self.aggressor = None
        self.sequence = []

        while pending and len(self.live) > 1:
            index = pending.pop(0)
            player = order[index]
            if player.folded:
                continue

            to_call = round(current_bet - player.street_bet, 2)
            action, target = self._decide(player, to_call, raises, preflop=preflop)
            self.sequence.append((player, action))

            if action == "fold":
                player.folded = True
                self.lines.append(f"{player.name}: folds")
            elif action == "check":
                player.checked_streets.add(self.street)
                self.lines.append(f"{player.name}: checks")
            elif action == "call":
                added = self._commit(player, current_bet)
                self.lines.append(f"{player.name}: calls {money(added)}")
            else:
                verb_is_bet = current_bet <= 0
                increment = round(target - current_bet, 2)
                self._commit(player, target)
                if verb_is_bet:
                    self.lines.append(f"{player.name}: bets {money(target)}")
                else:
                    self.lines.append(f"{player.name}: raises {money(increment)} to {money(target)}")
                current_bet = target
                raises += 1
                player.bet_streets.add(self.street)
                self.aggressor = player
                if preflop:
                    self.preflop_aggressor = player
                    if self.opener is None:
                        self.opener = player
                pending = [(index + step) % size for step in range(1, size) if not order[(index + step) % size].folded]

        self._return_uncalled()
        for player in self.players:
            player.street_bet = 0.0
        return len(self.live) > 1

    def _return_uncalled(self) -> None:
        """Hand back the part of the last bet nobody matched."""
        bets = sorted((player.street_bet for player in self.players), reverse=True)
        if len(bets) < 2 or bets[0] <= bets[1]:
            return
        excess = round(bets[0] - bets[1], 2)
        top = max(self.players, key=lambda player: player.street_bet)
        top.stack = round(top.stack + excess, 2)
        top.committed = round(top.committed - excess, 2)
        top.street_bet = round(top.street_bet - excess, 2)
        self.pot = round(self.pot - excess, 2)
        self.lines.append(f"Uncalled bet ({money(excess)}) returned to {top.name}")

    def _decide(self, player: Player, to_call: float, raises: int, *, preflop: bool) -> tuple[str, float]:
        """Pick an action from the player's style, the spot, and the price."""
        roll = self.rng.random()
        if preflop:
            return self._decide_preflop(player, to_call, raises, roll)
        if to_call <= 0:
            return self._decide_unbet_street(player, raises, roll)
        return self._decide_facing_bet(player, to_call, raises, roll)

    # -- preflop ---------------------------------------------------------

    def _decide_preflop(self, player: Player, to_call: float, raises: int, roll: float) -> tuple[str, float]:
        """Open, three-bet, four-bet, call or fold, on the player's style.

        ``raises`` counts the bets already in and the big blind is one of them,
        so an unopened pot is ``raises == 1`` and an open makes it two, a
        three-bet three. Only the big blind ever has no bet to call, which is
        why checking is possible here at all.
        """
        if to_call <= 0:
            return "check", 0.0
        return (
            self._decide_open(player, to_call, roll)
            if raises == 1
            else self._decide_facing_raise(player, to_call, raises, roll)
        )

    def _decide_open(self, player: Player, to_call: float, roll: float) -> tuple[str, float]:
        """Act first in an unopened pot: raise, limp or complete, or fold.

        Two tendencies, two decisions. The raise is drawn from the player's PFR
        rate and the *combined* entering range from their VPIP, so a 58/4
        calling station limps far more often than it raises instead of opening
        at its VPIP rate -- which is what keeps the demo's own PFR numbers
        meaning what the HUD calls them.
        """
        style = player.style
        position = self._position(player)
        # The big blind never limps into its own blind: it either raises or
        # takes a free flop, and it is not a blind defence spot.
        raise_rate = style.pfr
        enter_rate = style.pfr
        if position != "BB":
            raise_rate = style.pfr * OPEN_FACTOR[position]
            enter_rate = max(style.vpip * OPEN_FACTOR[position], raise_rate)
        if roll < raise_rate:
            target = self._legal_raise(player, BIG_BLIND * OPEN_SIZE_BB[position], BIG_BLIND)
            if target is not None:
                return "raise", target
        if roll < enter_rate:
            return "call", 0.0
        return "fold", 0.0

    def _decide_facing_raise(self, player: Player, to_call: float, raises: int, roll: float) -> tuple[str, float]:
        """React to a raise: re-raise, call, or fold."""
        current_bet = round(player.street_bet + to_call, 2)
        if raises == 2:
            return self._decide_vs_open(player, current_bet, roll)
        if raises == 3:
            return self._decide_vs_three_bet(player, current_bet, roll)
        return self._decide_vs_four_bet(player, current_bet, roll)

    def _decide_vs_open(self, player: Player, current_bet: float, roll: float) -> tuple[str, float]:
        """Face a single raise: three-bet, squeeze, call, or fold."""
        style = player.style
        rate = style.three_bet * THREE_BET_FACTOR[self._position(player)]
        if self._cold_callers_since_raise() >= 1:
            rate *= SQUEEZE_MULTIPLIER
        if roll < rate:
            target = self._legal_raise(player, current_bet * 3.4, current_bet)
            if target is not None:
                return "raise", target
        # Calling a raise is a narrower range than playing at all -- a station
        # still calls with almost anything, a nit still folds -- but nobody
        # calls as often as they enter a pot.
        if roll < rate + style.vpip * 0.55 + 0.04:
            return "call", 0.0
        return "fold", 0.0

    def _decide_vs_three_bet(self, player: Player, current_bet: float, roll: float) -> tuple[str, float]:
        """Face a three-bet: four-bet as the opener, cold four-bet rarely, or give up.

        The opener has the stronger range at this point, so they continue more
        often than a player who has not put money in yet.
        """
        style = player.style
        opened = player is self.opener
        four_bet_rate = style.four_bet if opened else style.four_bet * 0.35
        if roll < four_bet_rate:
            target = self._legal_raise(player, current_bet * 2.4, current_bet)
            if target is not None:
                return "raise", target
        continue_rate = style.vpip * (0.90 if opened else 0.50)
        if roll < four_bet_rate + continue_rate:
            return "call", 0.0
        return "fold", 0.0

    def _decide_vs_four_bet(self, player: Player, current_bet: float, roll: float) -> tuple[str, float]:
        """A fourth raise or beyond: only the reckless raise again."""
        style = player.style
        if roll < style.four_bet * 0.3:
            target = self._legal_raise(player, current_bet * 2.2, current_bet)
            if target is not None:
                return "raise", target
        if roll < 0.35 + style.vpip * 0.3:
            return "call", 0.0
        return "fold", 0.0

    # -- postflop --------------------------------------------------------

    def _decide_unbet_street(self, player: Player, raises: int, roll: float) -> tuple[str, float]:
        """Betting is opened to ``player``: c-bet, barrel, probe, bet, or check."""
        if raises >= 3 or roll >= self._open_bet_rate(player):
            return "check", 0.0
        target = self._legal_raise(player, self._bet_size(), 0.0)
        return ("raise", target) if target is not None else ("check", 0.0)

    def _open_bet_rate(self, player: Player) -> float:
        """How often ``player`` bets when the action checks to them.

        The c-bet and the turn and river barrels are the stats the analytics
        views are built on, so each reads the style's own frequency. A bet no
        frequency names -- a lead on a street nobody has bet, a probe after the
        aggressor checked -- falls back to the general aggression.
        """
        style = player.style
        if self.street == 1:
            return style.cbet_flop if player is self.preflop_aggressor else style.aggression * 0.5
        if self.street == 2:
            if 1 in player.bet_streets:
                return style.barrel_turn
            if self._aggressor_checked_the_flop():
                return style.probe_turn
            return style.aggression * 0.45
        if 2 in player.bet_streets:
            return style.barrel_river
        if 1 in player.bet_streets:
            return style.barrel_river * 0.8
        return style.aggression * 0.3

    def _aggressor_checked_the_flop(self) -> bool:
        """Whether the preflop aggressor passed on the flop, which opens a probe."""
        aggressor = self.preflop_aggressor
        return aggressor is not None and 1 in aggressor.checked_streets

    def _decide_facing_bet(self, player: Player, to_call: float, raises: int, roll: float) -> tuple[str, float]:
        """Face a bet: raise, call or fold.

        The single roll partitions the outcomes rather than testing them in
        sequence, so the three frequencies cannot add up to more than one and
        the resulting stats match the style by construction.
        """
        current_bet = round(player.street_bet + to_call, 2)
        fold_rate, raise_rate = self._defence_rates(player)
        if raises < 3 and roll < raise_rate:
            target = self._legal_raise(player, current_bet * 2.8, current_bet)
            if target is not None:
                return "raise", target
        if roll < raise_rate + fold_rate * (1.0 - raise_rate):
            return "fold", 0.0
        return "call", 0.0

    def _defence_rates(self, player: Player) -> tuple[float, float]:
        """(fold, raise) rates for facing a bet, in this spot.

        Facing the flop c-bet is the response the analytics have to get right,
        so it uses the style's own fold and raise numbers, bent by the seat:
        the blinds defend wide but fold more, the button folds least. Later
        streets use the same shape, since a player who folds to c-bets folds to
        barrels.
        """
        style = player.style
        if self.street == 1 and self.aggressor is self.preflop_aggressor:
            fold_rate = style.fold_to_cbet * FOLD_TO_CBET_FACTOR[self._position(player)]
            return min(fold_rate, 0.92), style.raise_facing_bet
        return 0.30 + (1.0 - style.vpip) * 0.35, style.raise_facing_bet * 0.8

    def _bet_size(self) -> float:
        """One size from the bet menu, which is what fills the sizing buckets."""
        multiplier = self.rng.choices(BET_SIZES, BET_SIZE_WEIGHTS)[0]
        return max(round(self.pot * multiplier, 2), BIG_BLIND)

    def _legal_raise(self, player: Player, wanted: float, current_bet: float) -> float | None:
        """``wanted`` clamped to a raise the player can make, or None if they can't.

        The ceiling keeps every bet well short of the stack: the generator does
        not model all-ins, so it must never produce one. The floor is the
        minimum raise, which also makes this function the legality check for a
        bet (``current_bet`` of zero).
        """
        ceiling = round((player.stack + player.street_bet) * 0.4, 2)
        target = round(min(wanted, ceiling), 2)
        floor = round(current_bet + BIG_BLIND, 2)
        return target if target >= floor else None

    # -- rendering -------------------------------------------------------

    def play(self, deck: list[str], hand_id: int, played_at: datetime) -> str:
        """Deal, bet, award, and return the finished hand history text."""
        self.lines.append(
            f"PokerStars Hand #{hand_id}: Hold'em No Limit "
            f"({money(SMALL_BLIND)}/{money(BIG_BLIND)} USD) - {played_at:%Y/%m/%d %H:%M:%S} CET "
            f"[{played_at:%Y/%m/%d %H:%M:%S} ET]",
        )
        self.lines.append(f"Table '{self.table}' {MAX_SEATS}-max Seat #{self.players[self.button].seat} is the button")
        for player in self.players:
            self.lines.append(f"Seat {player.seat}: {player.name} ({money(player.stack)} in chips)")

        small = self.players[(self.button + 1) % len(self.players)]
        big = self.players[(self.button + 2) % len(self.players)]
        self._commit(small, SMALL_BLIND)
        self.lines.append(f"{small.name}: posts small blind {money(SMALL_BLIND)}")
        self._commit(big, BIG_BLIND)
        self.lines.append(f"{big.name}: posts big blind {money(BIG_BLIND)}")

        for player in self.players:
            player.cards = [deck.pop(), deck.pop()]
        hero = next(player for player in self.players if player.name == HERO)
        self.lines.append("*** HOLE CARDS ***")
        self.lines.append(f"Dealt to {hero.name} [{hero.cards[0]} {hero.cards[1]}]")

        alive = self._run_street(BIG_BLIND, preflop=True)
        streets = (("FLOP", 3), ("TURN", 1), ("RIVER", 1))
        for street_index, (label, count) in enumerate(streets, start=1):
            if not alive:
                break
            self.street = street_index
            self.board.extend(deck.pop() for _ in range(count))
            for player in self.live:
                player.last_street_seen = street_index
            if label == "FLOP":
                self.lines.append(f"*** FLOP *** [{' '.join(self.board)}]")
            else:
                self.lines.append(f"*** {label} *** [{' '.join(self.board[:-1])}] [{self.board[-1]}]")
            alive = self._run_street(0.0, preflop=False)

        return "\n".join(self.lines + self._conclude(showdown=alive)) + "\n"

    def _conclude(self, *, showdown: bool) -> list[str]:
        """Showdown or fold-out, then the summary block. No flop, no drop."""
        lines: list[str] = []
        rake = min(round(self.pot * RAKE_RATE, 2), RAKE_CAP) if self.board else 0.0
        awarded = round(self.pot - rake, 2)

        shown: dict[str, tuple[int, ...]] = {}
        awards: dict[str, float] = {}
        if showdown and len(self.live) > 1:
            lines.append("*** SHOW DOWN ***")
            for player in self.live:
                shown[player.name] = hand_rank(player.cards + self.board)
            best_rank = max(shown.values())
            winners = [player for player in self.live if shown[player.name] == best_rank]
            for player in self.live:
                cards = " ".join(player.cards)
                lines.append(f"{player.name}: shows [{cards}] ({describe(player.cards + self.board)})")
        else:
            winners = [self.live[0]]

        share_cents, remainder = divmod(round(awarded * 100), len(winners))
        for index, winner in enumerate(winners):
            awards[winner.name] = (share_cents + (index < remainder)) / 100
            lines.append(f"{winner.name} collected {money(awards[winner.name])} from pot")

        lines.append("*** SUMMARY ***")
        lines.append(f"Total pot {money(self.pot)} | Rake {money(rake)}")
        if self.board:
            lines.append(f"Board [{' '.join(self.board)}]")
        winner_names = {winner.name for winner in winners}
        lines.extend(self._summary_line(player, winner_names, awards, shown) for player in self.players)
        return lines

    def _summary_line(
        self,
        player: Player,
        winner_names: set[str],
        awards: dict[str, float],
        shown: dict[str, tuple[int, ...]],
    ) -> str:
        prefix = f"Seat {player.seat}: {player.name}"
        if player is self.players[self.button]:
            prefix += " (button)"
        elif player is self.players[(self.button + 1) % len(self.players)]:
            prefix += " (small blind)"
        elif player is self.players[(self.button + 2) % len(self.players)]:
            prefix += " (big blind)"

        if player.name in shown:
            cards = " ".join(player.cards)
            category = describe(player.cards + self.board)
            if player.name in winner_names:
                return f"{prefix} showed [{cards}] and won ({money(awards[player.name])}) with {category}"
            return f"{prefix} showed [{cards}] and lost with {category}"
        if player.name in winner_names:
            return f"{prefix} collected ({money(awards[player.name])})"
        if player.folded:
            where = ("before Flop", "on the Flop", "on the Turn", "on the River")[player.last_street_seen]
            suffix = " (didn't bet)" if player.last_street_seen == 0 and player.committed == 0 else ""
            return f"{prefix} folded {where}{suffix}"
        return f"{prefix} mucked [{' '.join(player.cards)}]"


# --------------------------------------------------------------------------
# building the demo
# --------------------------------------------------------------------------

HANDS_PER_FILE = 120
SPAN_DAYS = 120


# The moment a seeded corpus is dated from. Fixed rather than "now": hand ids,
# every timestamp inside every hand and the session file names are derived from
# it, so a second build of the same seed would otherwise be a different corpus
# with different date-filtered numbers.
DEMO_ANCHOR: Final = datetime(2026, 6, 1, 19, 0, 0)


def generate(out_dir: Path, hand_count: int, seed: int, *, anchor: datetime | None = None) -> Path:
    """Write the invented hand histories, one file per simulated session.

    ``anchor`` is the day the corpus ends on; it defaults to ``DEMO_ANCHOR`` so
    two runs of one seed produce byte-identical files. Pass an explicit moment
    only for an ad-hoc corpus that is meant to end today.
    """
    rng = random.Random(seed)
    hands_dir = out_dir / "hands"
    if hands_dir.exists():
        shutil.rmtree(hands_dir)
    hands_dir.mkdir(parents=True, exist_ok=True)

    sessions = max(1, -(-hand_count // HANDS_PER_FILE))
    first_day = (anchor or DEMO_ANCHOR) - timedelta(days=SPAN_DAYS)
    hand_id = 240_000_000_000
    written = 0

    for session in range(sessions):
        # Sessions spread evenly across the span, so the graphs have a shape and
        # the date filters have something to filter.
        start = first_day + timedelta(
            days=session * SPAN_DAYS / sessions,
            hours=rng.randint(17, 22),
            minutes=rng.randint(0, 59),
        )
        table = rng.choice(TABLE_NAMES)
        opponents = rng.sample(ROSTER, MAX_SEATS - 1)
        button = rng.randrange(MAX_SEATS)
        chunk: list[str] = []

        for offset in range(min(HANDS_PER_FILE, hand_count - written)):
            hand_id += 1
            seats = [Player(HERO_STYLE, 1)]
            seats += [Player(style, index + 2) for index, style in enumerate(opponents)]
            writer = HandWriter(rng, seats, (button + offset) % MAX_SEATS, table)
            chunk.append(writer.play(new_deck(rng), hand_id, start + timedelta(minutes=offset)))
            written += 1

        filename = f"HH{start:%Y%m%d}-{session:03d} {table} NLHE 6max.txt"
        (hands_dir / filename).write_text("\n".join(chunk), encoding="utf-8")

    return hands_dir


def write_config(out_dir: Path) -> Path:
    """Copy the real HUD_config.xml and repoint its SQLite database at the demo.

    A copy, never the original: the reader's own configuration and their own
    database have to come out of this untouched.
    """
    from xml.etree.ElementTree import SubElement

    from defusedxml import ElementTree as DefusedElementTree

    source = REPO / "HUD_config.xml"
    if not source.is_file():
        source = REPO / "HUD_config.xml.example"
    destination = out_dir / "HUD_config.xml"
    shutil.copy(source, destination)

    tree = DefusedElementTree.parse(destination)
    for database in tree.getroot().iter("database"):
        database.set("default", "False")
        if database.get("db_server") == "sqlite":
            database.set("db_name", "demo.db3")
            database.set("db_path", str(out_dir))
            database.set("default", "True")
    for site in tree.getroot().iter("site"):
        is_demo_site = site.get("site_name") in {"PokerStars", "PokerStars.COM"}
        site.set("enabled", "True" if is_demo_site else "False")
        if is_demo_site:
            site.set("screen_name", HERO)
            site.set("HH_path", str(out_dir / "hands"))
            site.set("TS_path", "")

    # The source profile may leave the Hold'em rule sets disabled. Enable a
    # representative set in the disposable copy so the Auto Notes screenshot
    # demonstrates real matches instead of an empty workbench.
    root = tree.getroot()
    autonotes = next(iter(root.iter("autonotes")), None)
    if autonotes is None:
        autonotes = SubElement(root, "autonotes")
    enabled_rule_sets = {"holdem_cash_preflop", "flop_texture", "showdown_quality", "hero_relative"}
    ruleset_nodes = {node.get("name"): node for node in autonotes.iter("ruleset")}
    for rule_set_name in enabled_rule_sets:
        node = ruleset_nodes.get(rule_set_name)
        if node is None:
            node = SubElement(autonotes, "ruleset", name=rule_set_name)
        node.set("enabled", "True")
    tree.write(destination, encoding="utf-8", xml_declaration=True)
    return destination


def import_hands(config_path: Path, hands_dir: Path) -> int:
    """Create the demo database and bulk-import the generated hands into it."""
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    config = Config(file=str(config_path))
    database = Database(config)
    database.recreate_tables()

    importer = Importer(None, {"threads": 1}, config, sql=database.sql)
    importer.database = database
    importer.setCallHud(False)
    importer.setMode("bulk")
    importer.addBulkImportImportFileOrDir(str(hands_dir), site="PokerStars")
    importer.runImport()
    database.connection.commit()

    cursor = database.connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM Hands")
    total = cursor.fetchone()[0]
    database.disconnect()
    del importer  # its __del__ disconnects importer.database, which is `database`
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hands", type=int, default=2000, help="how many hands to invent")
    parser.add_argument("--out", type=Path, default=Path.home() / "fpdb-demo", help="where to build the demo")
    parser.add_argument("--seed", type=int, default=20260808, help="generator seed; same seed, same hands")
    parser.add_argument("--generate-only", action="store_true", help="write hand histories without importing them")
    args = parser.parse_args(argv)

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"inventing {args.hands} hands in {out_dir / 'hands'} ...")
    hands_dir = generate(out_dir, args.hands, args.seed)
    if args.generate_only:
        print("done (not imported)")
        return 0

    config_path = write_config(out_dir)
    print(f"importing into {out_dir / 'demo.db3'} ...")
    total = import_hands(config_path, hands_dir)
    print(f"\n{total} hands in the demo database.\n")
    print("Launch fpdb against it -- nothing on screen will need redacting:")
    print(f"    python fpdb_3_legacy/fpdb.pyw -c {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
