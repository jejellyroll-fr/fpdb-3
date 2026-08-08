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
HERO_STYLE = (0.25, 0.20, 0.60)
ROSTER = (
    # (name, vpip, pfr, postflop aggression) -- invented players with invented
    # tendencies, spread out so a HUD screenshot shows contrast rather than
    # fifteen shades of the same regular.
    ("NitPickerNed", 0.13, 0.11, 0.35),
    ("CallingStation", 0.58, 0.04, 0.10),
    ("MonsieurRegular", 0.24, 0.19, 0.55),
    ("LoosePassivePat", 0.46, 0.09, 0.20),
    ("TripleBarrelTom", 0.29, 0.25, 0.80),
    ("ManiacMarcel", 0.67, 0.44, 0.72),
    ("SolidSam", 0.21, 0.17, 0.50),
    ("FishyFrancis", 0.52, 0.07, 0.15),
    ("SqueezeQueen", 0.26, 0.22, 0.66),
    ("RockRoland", 0.15, 0.12, 0.40),
    ("SplashySteve", 0.61, 0.31, 0.58),
    ("GrindGaston", 0.23, 0.18, 0.52),
)
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


@dataclass
class Player:
    """One seat for the duration of one hand."""

    name: str
    seat: int
    vpip: float
    pfr: float
    aggression: float
    stack: float = STARTING_STACK
    cards: list[str] = field(default_factory=list)
    street_bet: float = 0.0
    committed: float = 0.0
    folded: bool = False
    last_street_seen: int = 0
    """0 preflop, 1 flop, 2 turn, 3 river -- what the summary line reports."""


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

    # -- betting ---------------------------------------------------------

    @property
    def live(self) -> list[Player]:
        return [player for player in self.players if not player.folded]

    def _order(self, *, preflop: bool) -> list[Player]:
        """Players in acting order: UTG first preflop, small blind first after."""
        offset = 3 if preflop else 1
        start = (self.button + offset) % len(self.players)
        return [self.players[(start + step) % len(self.players)] for step in range(len(self.players))]

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

        while pending and len(self.live) > 1:
            index = pending.pop(0)
            player = order[index]
            if player.folded:
                continue

            to_call = round(current_bet - player.street_bet, 2)
            action, target = self._decide(player, to_call, raises, preflop=preflop)

            if action == "fold":
                player.folded = True
                self.lines.append(f"{player.name}: folds")
            elif action == "check":
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
        """Pick an action from the player's style and the price of continuing."""
        roll = self.rng.random()
        if preflop:
            return self._decide_preflop(player, to_call, raises, roll)
        return self._decide_postflop(player, to_call, raises, roll)

    def _decide_preflop(self, player: Player, to_call: float, raises: int, roll: float) -> tuple[str, float]:
        """Open, three-bet, call or fold, on the player's VPIP and PFR."""
        if roll > player.vpip:
            return ("fold", 0.0) if to_call > 0 else ("check", 0.0)
        if roll < player.pfr and raises < 3:
            factor = 3.0 if raises == 1 else 2.6
            current_bet = player.street_bet + to_call
            target = self._legal_raise(player, current_bet * factor, current_bet)
            if target is not None:
                return "raise", target
        return ("call", 0.0) if to_call > 0 else ("check", 0.0)

    def _decide_postflop(self, player: Player, to_call: float, raises: int, roll: float) -> tuple[str, float]:
        """Bet, raise, call or fold, on the player's aggression."""
        if to_call <= 0:
            if roll < player.aggression * 0.55 and raises < 2:
                target = self._legal_raise(player, max(self.pot * 0.6, BIG_BLIND), 0.0)
                if target is not None:
                    return "raise", target
            return "check", 0.0

        current_bet = player.street_bet + to_call
        if roll < player.aggression * 0.18 and raises < 3:
            target = self._legal_raise(player, current_bet * 2.8, current_bet)
            if target is not None:
                return "raise", target
        if roll < player.vpip * 0.8 + player.aggression * 0.2:
            return "call", 0.0
        return "fold", 0.0

    def _legal_raise(self, player: Player, wanted: float, current_bet: float) -> float | None:
        """``wanted`` clamped to a raise the player can make, or None if they can't.

        The ceiling keeps every bet well short of the stack: the generator does
        not model all-ins, so it must never produce one.
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
        if showdown and len(self.live) > 1:
            lines.append("*** SHOW DOWN ***")
            for player in self.live:
                shown[player.name] = hand_rank(player.cards + self.board)
            winner = max(self.live, key=lambda player: shown[player.name])
            for player in self.live:
                cards = " ".join(player.cards)
                lines.append(f"{player.name}: shows [{cards}] ({describe(player.cards + self.board)})")
        else:
            winner = self.live[0]
        lines.append(f"{winner.name} collected {money(awarded)} from pot")

        lines.append("*** SUMMARY ***")
        lines.append(f"Total pot {money(self.pot)} | Rake {money(rake)}")
        if self.board:
            lines.append(f"Board [{' '.join(self.board)}]")
        lines.extend(self._summary_line(player, winner, awarded, shown) for player in self.players)
        return lines

    def _summary_line(
        self,
        player: Player,
        winner: Player,
        awarded: float,
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
            if player is winner:
                return f"{prefix} showed [{cards}] and won ({money(awarded)}) with {category}"
            return f"{prefix} showed [{cards}] and lost with {category}"
        if player is winner:
            return f"{prefix} collected ({money(awarded)})"
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


def generate(out_dir: Path, hand_count: int, seed: int) -> Path:
    """Write the invented hand histories, one file per simulated session."""
    rng = random.Random(seed)
    hands_dir = out_dir / "hands"
    hands_dir.mkdir(parents=True, exist_ok=True)

    sessions = max(1, -(-hand_count // HANDS_PER_FILE))
    first_day = datetime.now() - timedelta(days=SPAN_DAYS)
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
            seats = [Player(HERO, 1, *HERO_STYLE)]
            seats += [
                Player(name, index + 2, vpip, pfr, aggression)
                for index, (name, vpip, pfr, aggression) in enumerate(opponents)
            ]
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
    from defusedxml import ElementTree as DefusedElementTree

    source = REPO / "HUD_config.xml"
    if not source.is_file():
        source = REPO / "HUD_config.xml.example"
    destination = out_dir / "HUD_config.xml"
    shutil.copy(source, destination)

    tree = DefusedElementTree.parse(destination)
    for database in tree.getroot().iter("database"):
        if database.get("db_server") == "sqlite":
            database.set("db_name", "demo.db3")
            database.set("db_path", str(out_dir))
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
