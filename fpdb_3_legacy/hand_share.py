"""Readable hand renderers for sharing on forums, chats and in notes.

``Hand.writeHand()`` reproduces a room hand history and PHH is the structured
interchange format. Neither reads well pasted into GitHub, Discord or a forum
post, so this module renders a canonical :class:`Hand` into short,
room-neutral text meant for people:

* ``text`` -- plain normalized lines;
* ``markdown`` -- lightweight Markdown that GitHub, Discord and most modern
  forums render (bold and lists only, no tables);
* ``bbcode`` -- the ``[b]``/``[i]`` subset that classic forums accept.

This is presentation only. It never parses ``writeHand()`` output and it does
not define another structured hand format: the three formats share one
document model built straight from the hand's streets, actions and cards.

Privacy comes first by default: every player is renamed (``Hero``,
``Villain 1`` ...) and the site, table, hand number and time are left out
unless asked for.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Final

FORMATS: Final = ("text", "markdown", "bbcode")
ANONYMIZE_MODES: Final = ("all", "opponents", "none")
AMOUNT_MODES: Final = ("native", "bb")

_GAME_NAMES: Final = {
    "holdem": "Hold'em",
    "6_holdem": "Short Deck Hold'em",
    "2_holdem": "Double Hold'em",
    "irish": "Irish",
    "cour_hi": "Courchevel",
    "cour_hilo": "Courchevel Hi/Lo",
    "6_omaha8": "6 Card Omaha Hi/Lo",
    "27_razz": "2-7 Razz",
    "a5_1draw": "A-5 Single Draw",
    "badacey": "Badacey",
    "badeucey": "Badeucey",
    "drawmaha": "2-7 Drawmaha",
    "omahahi": "Omaha",
    "omahahilo": "Omaha Hi/Lo",
    "5_omahahi": "5 Card Omaha",
    "5_omaha8": "5 Card Omaha Hi/Lo",
    "6_omahahi": "6 Card Omaha",
    "fusion": "Fusion",
    "aof_holdem": "All-in or Fold Hold'em",
    "aof_omaha": "All-in or Fold Omaha",
    "razz": "Razz",
    "studhi": "7 Card Stud",
    "studhilo": "7 Card Stud Hi/Lo",
    "5_studhi": "5 Card Stud",
    "fivedraw": "5 Card Draw",
    "27_1draw": "2-7 Single Draw",
    "27_3draw": "2-7 Triple Draw",
    "a5_3draw": "A-5 Triple Draw",
    "badugi": "Badugi",
}
_LIMIT_NAMES: Final = {
    "nl": "NL",
    "pl": "PL",
    "fl": "FL",
    "cn": "Cap NL",
    "cp": "Cap PL",
}
_STREET_NAMES: Final = {
    "PREFLOP": "Preflop",
    "FLOP": "Flop",
    "TURN": "Turn",
    "RIVER": "River",
    "DEAL": "Deal",
    "DRAWONE": "First draw",
    "DRAWTWO": "Second draw",
    "DRAWTHREE": "Third draw",
    "SECOND": "2nd street",
    "THIRD": "3rd street",
    "FOURTH": "4th street",
    "FIFTH": "5th street",
    "SIXTH": "6th street",
    "SEVENTH": "7th street",
}
# Seats between the big blind and the button, named from the button backwards.
# Seats between the big blind and the button: the three latest are named from
# the button backwards, the rest from UTG forwards.
_LATE_POSITIONS: Final = ("LJ", "HJ", "CO")
_EARLY_POSITIONS: Final = ("UTG", "UTG+1", "UTG+2")
_BLIND_VERBS: Final = {
    "small blind": "posts SB",
    "secondsb": "posts SB",
    "big blind": "posts BB",
    "both": "posts SB + BB",
    "straddle": "posts straddle",
    "button blind": "posts button blind",
    "ante": "posts ante",
}


@dataclass(frozen=True)
class ShareOptions:
    """What to render and what to reveal.

    The defaults are the privacy-minded ones: everybody renamed, no site,
    table, hand number or timestamp.
    """

    format: str = "text"
    anonymize: str = "all"
    amounts: str = "native"
    site: bool = False
    table: bool = False
    hand_id: bool = False
    timestamp: bool = False
    stacks: bool = True
    results: bool = True
    rake: bool = False
    cashout: bool = False

    def __post_init__(self) -> None:
        for name, value, allowed in (
            ("format", self.format, FORMATS),
            ("anonymize", self.anonymize, ANONYMIZE_MODES),
            ("amounts", self.amounts, AMOUNT_MODES),
        ):
            if value not in allowed:
                msg = f"Unknown {name} {value!r}; expected one of {', '.join(allowed)}"
                raise ValueError(msg)


@dataclass
class _Street:
    title: str
    board: list[list[str]] = field(default_factory=list)
    pot: str | None = None
    lines: list[str] = field(default_factory=list)


@dataclass
class _Document:
    title: str
    meta: list[str]
    seats: list[str]
    hero_cards: str | None
    streets: list[_Street]
    summary: list[str]


def _is_fixed_limit_tournament(hand: Any) -> bool:
    # Fixed-limit tournaments store their bets (300/600) where ring games
    # store their blinds (0.05/0.10 for a 0.10/0.20 game).
    return hand.gametype.get("limitType") == "fl" and hand.gametype.get("type") == "tour"


def big_blind(hand: Any) -> Decimal:
    """The big blind actually posted, which BB amounts are counted in."""
    return Decimal(str(hand.sb if _is_fixed_limit_tournament(hand) else hand.bb))


def supports_bb_amounts(hand: Any) -> bool:
    """Whether amounts can be expressed in big blinds for this hand.

    Stud has no blinds to convert from, so it is gated rather than rendered
    against a number that is not a big blind.
    """
    if hand.gametype.get("base") == "stud":
        return False
    try:
        return big_blind(hand) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def render_hand(hand: Any, options: ShareOptions | None = None, **overrides: Any) -> str:
    """Render *hand* for sharing.

    ``render_hand(hand, format="markdown", anonymize="opponents", amounts="bb")``
    is the same as passing a :class:`ShareOptions` with those fields.
    """
    options = replace(options or ShareOptions(), **overrides)
    if options.amounts == "bb" and not supports_bb_amounts(hand):
        msg = "This hand has no big blind to express amounts in"
        raise ValueError(msg)
    document = _Builder(hand, options).build()
    return _FORMATTERS[options.format](document)


class _Builder:
    def __init__(self, hand: Any, options: ShareOptions) -> None:
        self.hand = hand
        self.options = options
        self.players = [p for p in hand.players if p[1] not in getattr(hand, "sitout", set())]
        self.positions = self._positions()
        self.names = self._names()
        self.bb = big_blind(hand) if options.amounts == "bb" else None
        self.chips = self._plays_for_chips()

    # -- identity -------------------------------------------------------------
    def _action_order(self) -> list[Any]:
        """Seated players from the first seat after the button round to it."""
        seats = sorted(self.players, key=lambda p: int(p[0]))
        button = self.hand.buttonpos
        if self.hand.gametype.get("base") == "stud" or not button:
            return seats
        after = [p for p in seats if int(p[0]) > int(button)]
        return after + [p for p in seats if int(p[0]) <= int(button)]

    def _positions(self) -> dict[str, str]:
        if self.hand.gametype.get("base") == "stud" or not self.hand.buttonpos:
            return {}
        order = self._action_order()
        if not order or int(order[-1][0]) != int(self.hand.buttonpos):
            return {}
        count = len(order)
        if count == 2:
            # Heads-up the button posts the small blind and acts first preflop.
            return {order[-1][1]: "BTN", order[0][1]: "BB"}
        middle_count = count - 3
        late = list(_LATE_POSITIONS[len(_LATE_POSITIONS) - min(middle_count, len(_LATE_POSITIONS)) :])
        early_count = middle_count - len(late)
        early = [*_EARLY_POSITIONS, *(f"MP{i}" for i in range(1, early_count))][:early_count]
        middle = [*early, *late]
        labels = ["SB", "BB", *middle, "BTN"]
        return {player[1]: label for player, label in zip(order, labels, strict=True)}

    def _names(self) -> dict[str, str]:
        hero = self.hand.hero or ""
        mode = self.options.anonymize
        names: dict[str, str] = {}
        villain = 0
        for player in self._action_order():
            name = player[1]
            if mode == "none":
                names[name] = name
            elif name == hero:
                names[name] = name if mode == "opponents" else "Hero"
            else:
                villain += 1
                names[name] = f"Villain {villain}"
        return names

    def name(self, player: str) -> str:
        return self.names.get(player, player if self.options.anonymize == "none" else "Unknown")

    # -- amounts --------------------------------------------------------------
    def _plays_for_chips(self) -> bool:
        gametype = self.hand.gametype
        return gametype.get("type") == "tour" or gametype.get("currency") in ("play", "T$") or not self.hand.sym

    def money(self, amount: Any) -> str:
        value = Decimal(str(amount))
        if self.bb is not None:
            ratio = (value / self.bb).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
            return f"{ratio:f} BB"
        if self.chips:
            if value == value.to_integral_value():
                return f"{int(value):,}"
            return f"{value:,.2f}"
        return f"{self.hand.sym}{value:,.2f}"

    def stakes(self) -> str:
        """The stakes as the room advertises them, always in the hand's money.

        They are what BB amounts are measured against, so they stay in money
        even when the rest is in big blinds. Fixed-limit games are sold by
        their bet sizes, not their blinds: the small bet is the big blind (for
        stud the stored blinds both hold it) and the big bet doubles it.
        """
        saved, self.bb = self.bb, None
        try:
            if _is_fixed_limit_tournament(self.hand):
                return f"{self.money(self.hand.sb)}/{self.money(self.hand.bb)}"
            if self.hand.gametype.get("limitType") == "fl":
                small = Decimal(str(self.hand.bb))
                return f"{self.money(small)}/{self.money(small * 2)}"
            return f"{self.money(self.hand.sb)}/{self.money(self.hand.bb)}"
        finally:
            self.bb = saved

    # -- document -------------------------------------------------------------
    def build(self) -> _Document:
        return _Document(
            title=self._title(),
            meta=self._meta(),
            seats=self._seats(),
            hero_cards=self._hero_cards(),
            streets=self._streets(),
            summary=self._summary(),
        )

    def _title(self) -> str:
        gametype = self.hand.gametype
        game = _GAME_NAMES.get(gametype.get("category"), str(gametype.get("category", "")))
        limit = _LIMIT_NAMES.get(gametype.get("limitType"), "")
        name = f"{limit} {game}".strip()
        # A hand rebuilt from the database has no history text and a
        # placeholder table size (always 10), so only a parsed hand says it.
        if self.hand.maxseats and getattr(self.hand, "handText", None):
            name += f" {self.hand.maxseats}-max"
        if gametype.get("type") == "tour":
            name += " tournament"
        title = f"{name} - {self.stakes()}"
        if self.bb is not None:
            title += " (amounts in BB)"
        return title

    def _meta(self) -> list[str]:
        meta = []
        if self.options.site and self.hand.sitename:
            meta.append(str(self.hand.sitename))
        if self.options.table and self.hand.tablename:
            meta.append(f"Table {self.hand.tablename}")
        if self.options.hand_id and self.hand.handid:
            meta.append(f"Hand #{self.hand.handid}")
        if self.options.timestamp and hasattr(self.hand.startTime, "strftime"):
            meta.append(self.hand.startTime.strftime("%Y-%m-%d %H:%M"))
        return meta

    def _seats(self) -> list[str]:
        lines = []
        for player in self._action_order():
            label = self.name(player[1])
            where = self.positions.get(player[1])
            parts = [where] if where else []
            if self.options.stacks and player[2] is not None:
                parts.append(self.money(player[2]))
            lines.append(f"{label}: {' - '.join(parts)}" if parts else label)
        return lines

    def _known(self, cards: list[str]) -> bool:
        return bool(cards) and all(card and card != "0x" for card in cards)

    def _hero_cards(self) -> str | None:
        hero = self.hand.hero
        if not hero or hero not in self.names:
            return None
        cards = self._starting_cards(hero)
        return f"{self.name(hero)} [{' '.join(cards)}]" if self._known(cards) else None

    def _starting_cards(self, player: str) -> list[str]:
        base = self.hand.gametype.get("base")
        streets = list(getattr(self.hand, "holeStreets", []) or [])
        if not streets:
            return []
        if base == "hold" and self.hand.gametype.get("category") != "fusion":
            return list(self.hand.join_holecards(player, asList=True))
        # Fusion deals its third and fourth hole cards on the flop and turn;
        # they are shown there, not before the preflop action.
        held = self.hand.holecards.get(streets[0], {}).get(player)
        if not held:
            return []
        if base == "stud":
            return [*held[1], *held[0]]
        return list(held[1])

    def _streets(self) -> list[_Street]:
        hand = self.hand
        streets = []
        pot = Decimal(0)
        for action in hand.actions.get("BLINDSANTES", []):
            pot += self._paid(action)
        blinds = [self._action_line(action) for action in hand.actions.get("BLINDSANTES", [])]
        first = True
        for street in hand.allStreets:
            if street == "BLINDSANTES":
                continue
            actions = hand.actions.get(street, [])
            board = list(hand.board.get(street, []) or [])
            dealt = self._stud_upcards(street)
            if not actions and not board and not dealt and not (first and blinds):
                continue
            section = _Street(title=self._street_title(street))
            if board:
                section.board = [cards for cards in (self._board_before(street), board) if cards]
            if not first:
                section.pot = self.money(self._pot_at(pot))
            if first:
                section.lines.extend(blinds)
            section.lines.extend(dealt)
            section.lines.extend(self._hero_new_cards(street))
            section.lines.extend(self._compress_folds([(a, self._action_line(a, street)) for a in actions]))
            for action in actions:
                pot += self._paid(action)
            streets.append(section)
            first = False
        return streets

    def _pot_at(self, running: Decimal) -> Decimal:
        """The pot as a street starts.

        An uncalled bet only goes back once nobody can put in more money, so
        once the running total passes the final pot the difference is that
        returned bet and the final pot is what is really in the middle.
        """
        total = self.hand.totalpot
        if total is None:
            return running
        return min(running, Decimal(str(total)))

    @staticmethod
    def _street_title(street: str) -> str:
        base = street.rstrip("0123456789")
        run = street[len(base) :]
        title = _STREET_NAMES.get(base, base.capitalize())
        return f"{title} (run {run})" if run else title

    def _board_before(self, street: str) -> list[str]:
        """Community cards already out when *street*'s cards arrive."""
        base = street.rstrip("0123456789")
        run = street[len(base) :]
        order = ("FLOP", "TURN", "RIVER")
        if base not in order:
            return []
        cards: list[str] = []
        for earlier in order[: order.index(base)]:
            cards.extend(self.hand.board.get(f"{earlier}{run}") or self.hand.board.get(earlier) or [])
        return cards

    def _stud_upcards(self, street: str) -> list[str]:
        if self.hand.gametype.get("base") != "stud":
            return []
        lines = []
        for player in self._action_order():
            held = self.hand.holecards.get(street, {}).get(player[1])
            if not held:
                continue
            if player[1] == self.hand.hero and street == self.hand.holeStreets[0]:
                cards = [*held[1], *held[0]]
            else:
                cards = list(held[0])
            if self._known(cards):
                lines.append(f"{self.name(player[1])} [{' '.join(cards)}]")
        return lines

    def _hero_new_cards(self, street: str) -> list[str]:
        """The hero's cards that change on a later street.

        A draw game shows the hand after the draw; Fusion shows the hole card
        dealt on the flop or the turn.
        """
        hand = self.hand
        base = hand.gametype.get("base")
        if base not in ("draw", "hold") or not hand.hero:
            return []
        streets = list(getattr(hand, "holeStreets", []) or [])
        if street not in streets[1:]:
            return []
        held = hand.holecards.get(street, {}).get(hand.hero)
        if not held:
            return []
        if base == "hold":
            dealt = list(held[0])
            return [f"{self.name(hand.hero)} is dealt [{' '.join(dealt)}]"] if self._known(dealt) else []
        if not self._known(list(held[1])):
            return []
        return [f"{self.name(hand.hero)} [{' '.join(held[1])}]"]

    @staticmethod
    def _paid(action: tuple) -> Decimal:
        kind = action[1]
        if kind in ("raises", "completes"):
            return Decimal(str(action[2])) + Decimal(str(action[4]))
        if kind in ("calls", "bets", "bringin", "ante", *_BLIND_VERBS):
            return Decimal(str(action[2]))
        return Decimal(0)

    def _compress_folds(self, actions: list[tuple[tuple, str]]) -> list[str]:
        """Collapse a run of folds into one line so preflop stays readable."""
        lines: list[str] = []
        run: list[str] = []

        def flush() -> None:
            if len(run) == 1:
                lines.append(f"{run[0]} folds")
            elif run:
                lines.append(f"{', '.join(run[:-1])} and {run[-1]} fold")
            run.clear()

        for action, line in actions:
            if action[1] == "folds":
                run.append(self.name(action[0]))
                continue
            flush()
            lines.append(line)
        flush()
        return lines

    def _action_line(self, action: tuple, street: str | None = None) -> str:
        who = self.name(action[0])
        kind = action[1]
        if kind in ("folds", "checks"):
            return f"{who} {kind}"
        if kind == "cashout":
            return f"{who} cashes out"
        if kind == "stands pat":
            return f"{who} stands pat"
        if kind == "discards":
            count = int(action[2])
            text = f"{who} discards {count} {'card' if count == 1 else 'cards'}"
            cards = action[3] if len(action) > 3 else None
            if cards and action[0] == self.hand.hero:
                shown = cards if isinstance(cards, str) else " ".join(cards)
                text += f" [{shown}]"
            return text
        if kind in ("raises", "completes"):
            verb = "raises to" if kind == "raises" else "completes to"
            return f"{who} {verb} {self.money(action[3])}{self._all_in(action[5])}"
        if kind == "bringin":
            return f"{who} brings in for {self.money(action[2])}{self._all_in(action[3])}"
        if kind in ("calls", "bets"):
            return f"{who} {kind} {self.money(action[2])}{self._all_in(action[3])}"
        verb = _BLIND_VERBS.get(kind, kind)
        amount = f" {self.money(action[2])}" if len(action) > 2 else ""
        all_in = self._all_in(action[3]) if len(action) > 3 else ""
        return f"{who} {verb}{amount}{all_in}"

    @staticmethod
    def _all_in(flag: Any) -> str:
        return " (all-in)" if flag is True else ""

    # -- summary --------------------------------------------------------------
    def _summary(self) -> list[str]:
        hand = self.hand
        lines = []
        for player, amount in hand.pot.returned.items():
            lines.append(f"Uncalled {self.money(amount)} returned to {self.name(player)}")
        if not self.options.results:
            return lines
        lines.extend(self._showdown())
        for player, amount in self._winnings().items():
            lines.append(f"{self.name(player)} wins {self.money(amount)}")
        if self.options.cashout:
            for player, amount in getattr(hand, "cashOutAmounts", {}).items():
                fee = getattr(hand, "cashOutFees", {}).get(player)
                fee_text = f" (fee {self.money(fee)})" if fee else ""
                lines.append(f"{self.name(player)} cashes out {self.money(amount)}{fee_text}")
        total = hand.totalpot
        if total is not None:
            pot_line = f"Total pot {self.money(total)}"
            if self.options.rake and hand.rake is not None:
                pot_line += f" | Rake {self.money(hand.rake)}"
            lines.append(pot_line)
        return lines

    def _showdown(self) -> list[str]:
        hand = self.hand
        revealed = (set(hand.shown) | set(hand.mucked)) - set(hand.folded)
        # A hand read back from the database does not record what the hero
        # showed; when an opponent's cards were revealed at a showdown the
        # hero still in the hand was part of it.
        showdown = bool(revealed - {hand.hero})
        if hand.hero and hand.hero not in hand.folded and showdown:
            revealed.add(hand.hero)
        lines = []
        for player in self._action_order():
            name = player[1]
            if name not in revealed:
                continue
            if name == hand.hero and name not in hand.shown and not showdown:
                continue
            cards = self._final_cards(name)
            if not self._known(cards):
                continue
            description = hand.showdownStrings.get(name)
            suffix = f" ({description})" if description else ""
            lines.append(f"{self.name(name)} shows [{' '.join(cards)}]{suffix}")
        return lines

    def _final_cards(self, player: str) -> list[str]:
        hand = self.hand
        base = hand.gametype.get("base")
        if base == "hold":
            return list(hand.join_holecards(player, asList=True))
        if base == "stud":
            return [card for card in hand.join_holecards(player, asList=True) if card]
        for street in reversed(list(getattr(hand, "holeStreets", []) or [])):
            held = hand.holecards.get(street, {}).get(player)
            if held and held[1]:
                return list(held[1])
        return []

    def _winnings(self) -> dict[str, Decimal]:
        """What each player won from the pot.

        A cash-out is recorded among the collections too, but it is the room's
        insurance payout, not pot winnings: it is taken back out here and only
        shown by the cash-out option.
        """
        totals: dict[str, Decimal] = {}
        if self.hand.collectees:
            for player, amount in self.hand.collectees.items():
                totals[player] = Decimal(str(amount))
        else:
            for player, amount in self.hand.collected:
                totals[player] = totals.get(player, Decimal(0)) + Decimal(str(amount))
        for player, amount in getattr(self.hand, "cashOutAmounts", {}).items():
            if player in totals:
                totals[player] -= Decimal(str(amount))
        return {player: amount for player, amount in totals.items() if amount > 0}


# -- formatters ---------------------------------------------------------------
def _board_text(board: list[list[str]]) -> str:
    return " ".join(f"[{' '.join(cards)}]" for cards in board)


def _street_heading(street: _Street) -> str:
    heading = street.title
    if street.board:
        heading += f" {_board_text(street.board)}"
    if street.pot is not None:
        heading += f" - Pot {street.pot}"
    return heading


def _format_text(doc: _Document) -> str:
    out = [doc.title]
    if doc.meta:
        out.append(" | ".join(doc.meta))
    out.append("")
    out.extend(doc.seats)
    if doc.hero_cards:
        out += ["", doc.hero_cards]
    for street in doc.streets:
        out += ["", _street_heading(street), *street.lines]
    if doc.summary:
        out += ["", "Summary", *doc.summary]
    return "\n".join(out) + "\n"


def _md_escape(text: str) -> str:
    # Player names are the only free text; keep them from turning into markup.
    for char in ("\\", "*", "_", "`", "~", "|", ">", "#"):
        text = text.replace(char, f"\\{char}")
    return text


def _format_markdown(doc: _Document) -> str:
    out = [f"**{_md_escape(doc.title)}**"]
    if doc.meta:
        out.append(f"*{_md_escape(' | '.join(doc.meta))}*")
    out.append("")
    out.extend(f"- {_md_escape(seat)}" for seat in doc.seats)
    if doc.hero_cards:
        out += ["", f"**{_md_escape(doc.hero_cards)}**"]
    for street in doc.streets:
        out += ["", f"**{_md_escape(_street_heading(street))}**"]
        out.extend(f"- {_md_escape(line)}" for line in street.lines)
    if doc.summary:
        out += ["", "**Summary**"]
        out.extend(f"- {_md_escape(line)}" for line in doc.summary)
    return "\n".join(out) + "\n"


def _bb_escape(text: str) -> str:
    return text.replace("[", "&#91;").replace("]", "&#93;") if "[/" in text else text


def _format_bbcode(doc: _Document) -> str:
    out = [f"[b]{_bb_escape(doc.title)}[/b]"]
    if doc.meta:
        out.append(f"[i]{_bb_escape(' | '.join(doc.meta))}[/i]")
    out.append("")
    out.extend(_bb_escape(seat) for seat in doc.seats)
    if doc.hero_cards:
        out += ["", f"[b]{_bb_escape(doc.hero_cards)}[/b]"]
    for street in doc.streets:
        out += ["", f"[b]{_bb_escape(_street_heading(street))}[/b]"]
        out.extend(_bb_escape(line) for line in street.lines)
    if doc.summary:
        out += ["", "[b]Summary[/b]"]
        out.extend(_bb_escape(line) for line in doc.summary)
    return "\n".join(out) + "\n"


_FORMATTERS: Final = {
    "text": _format_text,
    "markdown": _format_markdown,
    "bbcode": _format_bbcode,
}
