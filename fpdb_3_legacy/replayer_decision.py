"""Decision arithmetic for the replayer, from the replay states already displayed (#826).

Qt-free and independent of card equity: effective stack-to-pot ratio at the
start of the street, the call and its pot odds (capped at what an all-in
caller can win), the size of the last bet in % of the pot, and the pure
heads-up minimum defence frequency / fold equity a bet needs.

Contributed by thecrawler1 (https://github.com/thecrawler1/fpdb-3, branch
``personal``, commits d8c09fe and ae139fd).
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

ZERO = Decimal(0)
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class HeroDecision:  # pylint: disable=too-many-instance-attributes  # one flat result record
    street: str = ""
    mode: str = "neutral"
    action: str = ""
    call_amount: Decimal = ZERO
    bet_amount: Decimal = ZERO
    bet_pct: Decimal | None = None
    pot_odds_pct: Decimal | None = None
    mdf_pct: Decimal | None = None
    fold_equity_pct: Decimal | None = None
    street_pot: Decimal = ZERO
    effective: tuple[tuple[str, Decimal], ...] = ()
    effective_pot: Decimal | None = None
    pot_before_call: Decimal | None = None
    uncalled_excess: Decimal | None = None

    @property
    def spr(self) -> tuple[Decimal, ...]:
        return tuple(stack / self.street_pot for _, stack in self.effective) if self.street_pot > 0 else ()

    @property
    def effective_pot_before(self) -> Decimal | None:
        if self.effective_pot is not None:
            return max(ZERO, self.effective_pot - self.call_amount)
        return None


def _live(player: Any) -> bool:
    return not getattr(player, "folded", False) and player.action != "folds"


def _room_money(state: Any) -> Decimal:
    """Money the room put in the pot (a Winamax/BetRivers splash): in no player's stack."""
    return getattr(state, "room_money", ZERO) or ZERO


def _pot(state: Any) -> Decimal:
    # startPhase may return an unmatched bet without updating newpot. Actual
    # contributions respect that return and include all folded dead money.
    # Room-added money is in the pot without coming out of any stack, so it is
    # added on top: leaving it out halved the pot odds of a call into a splash.
    if all(hasattr(p, "startStack") for p in state.players.values()):
        return sum((max(ZERO, p.startStack - p.stack) for p in state.players.values()), _room_money(state))
    return max(ZERO, getattr(state, "newpot", getattr(state, "pot", ZERO))) + _room_money(state)


def _usable(state: Any, player: Any) -> Decimal:
    """The chips a player can still put in: on a cap table, only the unused part of the cap.

    Mirrors ``action_events.cap_remaining``, which the stored action statistics
    use: a player who reached the cap keeps chips behind but cannot bet them.
    """
    cap = getattr(state, "cap", ZERO) or ZERO
    if cap <= 0 or not hasattr(player, "startStack"):
        return player.stack
    return max(ZERO, min(player.stack, cap - (player.startStack - player.stack)))


def _aggression(states: list[Any], index: int, start: int, names: set[str]) -> tuple[str, Any, Any] | None:
    """The latest bet or raise of the street by one of `names`: (name, state before, state after)."""
    for i in range(index, start, -1):
        previous = states[i - 1]
        for name, player in states[i].players.items():
            # Phase copies can retain justacted; require a real investment.
            if (
                name in names
                and player.justacted
                and player.action in {"bets", "raises"}
                and name in previous.players
                and player.chips > previous.players[name].chips
            ):
                return name, previous, states[i]
    return None


def _sizing(previous: Any, current: Any, name: str) -> tuple[Decimal, Decimal | None]:
    investment = current.players[name].chips - previous.players[name].chips
    pot = _pot(previous)
    return investment, investment / pot * HUNDRED if pot > 0 else None


def _call_pot_and_odds(state: Any, hero: Any, amount: Decimal) -> tuple[Decimal, Decimal | None]:
    players = state.players.values()
    displayed_pot = _pot(state)
    if amount < hero.stack or not all(hasattr(p, "startStack") for p in players):
        final_pot = displayed_pot + amount
    else:

        def antes(player: Any) -> Decimal:
            return getattr(player, "antes", ZERO) or ZERO

        cap = hero.startStack - hero.stack - antes(hero) + amount
        # Room money, like antes, is dead money the caller always contests.
        final_pot = (
            sum(
                (min(max(ZERO, p.startStack - p.stack - antes(p)), cap) + antes(p) for p in players),
                _room_money(state),
            )
            + amount
        )
    odds = amount / final_pot * HUNDRED if final_pot > 0 else None
    return final_pot, odds


def _call_odds(state: Any, hero: Any, amount: Decimal) -> Decimal | None:
    """The share of the pot after the call that the call is, counting only what it can win.

    Only an all-in call is capped: a caller with chips behind can match any
    later money. Capped, each player's betting counts up to the caller's total,
    while antes stay whole: they are dead money in the main pot, which the
    caller always contests.
    """
    return _call_pot_and_odds(state, hero, amount)[1]


def _street_start(states: list[Any], index: int) -> int:
    start = index
    while start > 0 and states[start - 1].street == states[index].street:
        start -= 1
    return start


def _effective(initial: Any, hero_name: str) -> tuple[tuple[str, Decimal], ...]:
    """Each live opponent's effective stack against the hero at the start of the street."""
    hero = initial.players.get(hero_name)
    if not hero or not _live(hero):
        return ()
    return tuple(
        (name, min(_usable(initial, hero), _usable(initial, player)))
        for name, player in initial.players.items()
        if name != hero_name and _live(player)
    )


def _call_decision(states: list[Any], index: int, start: int, hero_name: str, highest: Decimal) -> dict[str, Any]:
    state = states[index]
    hero = state.players[hero_name]
    call = min(hero.stack, max(ZERO, highest - hero.chips))
    # The bet to call is the street's latest aggression by an opponent, not
    # whichever opponent happens to hold as many chips (a caller may).
    opponents = {name for name, player in state.players.items() if name != hero_name and _live(player)}
    event = _aggression(states, index, start, opponents)
    sizing = None
    if event and event[2].players[event[0]].chips == highest:
        sizing = _sizing(event[1], event[2], event[0])[1]
    final_pot, odds = _call_pot_and_odds(state, hero, call)
    displayed_pot = _pot(state)
    excess = max(ZERO, (displayed_pot + call) - final_pot)
    return {
        "mode": "call",
        "call_amount": call,
        "pot_odds_pct": odds,
        "bet_pct": sizing,
        "effective_pot": final_pot,
        "pot_before_call": displayed_pot,
        "uncalled_excess": excess,
    }


def _bet_decision(states: list[Any], index: int, start: int, hero_name: str) -> dict[str, Any] | None:
    event = _aggression(states, index, start, {hero_name})
    if event is None:
        return None
    _name, previous, current = event
    amount, sizing = _sizing(previous, current, hero_name)
    prior_opponents = [p for name, p in previous.players.items() if name != hero_name and _live(p)]
    mdf = fe = None
    if len(prior_opponents) == 1:
        opponent = prior_opponents[0]
        risk = max(
            ZERO,
            min(current.players[hero_name].chips, opponent.stack + opponent.chips) - previous.players[hero_name].chips,
        )
        pot = _pot(previous)
        if risk > 0 and pot > 0:
            mdf, fe = pot / (pot + risk) * HUNDRED, risk / (pot + risk) * HUNDRED
    return {
        "mode": "bet",
        "action": current.players[hero_name].action,
        "bet_amount": amount,
        "bet_pct": sizing,
        "mdf_pct": mdf,
        "fold_equity_pct": fe,
    }


def hero_decision(states: list[Any], index: int, hero_name: str) -> HeroDecision:
    """Street-start SPR, current call odds and pure HU defence/bluff thresholds.

    Multiway SPR is a per-opponent range. MDF is not assigned to individual
    opponents in multiway. A raise risks the new investment in that action,
    measured against the pot immediately before it; uncallable excess is capped.
    """
    if not states or not 0 <= index < len(states):
        return HeroDecision()
    state = states[index]
    start = _street_start(states, index)
    initial = states[start]
    base = HeroDecision(street=state.street or "", street_pot=_pot(initial), effective=_effective(initial, hero_name))
    hero = state.players.get(hero_name)
    opponents = [p for name, p in state.players.items() if name != hero_name and _live(p)]
    if hero is None or not _live(hero) or getattr(state, "ended", False) or not opponents:
        return base
    highest = max(p.chips for p in opponents)
    if min(hero.stack, highest - hero.chips) > 0:
        return replace(base, **_call_decision(states, index, start, hero_name, highest))
    if hero.chips <= 0 or hero.action not in {"bets", "raises"} or highest > hero.chips:
        return base
    bet = _bet_decision(states, index, start, hero_name)
    return replace(base, **bet) if bet else base


def _decides(player: Any) -> bool:
    action = player.action or ""
    return player.justacted and (
        action in {"checks", "calls", "bets", "raises", "folds", "stands pat"} or action.startswith("discards")
    )


def next_decision_actor(states: list[Any], index: int) -> str | None:
    """Use the replay sequence only to identify whose turn is next, not its size."""
    if not states or not 0 <= index < len(states) or getattr(states[index], "ended", False):
        return None
    current = states[index]
    for following in states[index + 1 :]:
        if following.street != current.street or getattr(following, "ended", False):
            return None
        name = next((name for name, player in following.players.items() if _decides(player)), None)
        if name is not None:
            present = current.players.get(name)
            return name if present and _live(present) and present.stack > 0 else None
    return None


def action_decision(states: list[Any], index: int, hero_name: str) -> tuple[str | None, HeroDecision]:
    """The player about to act and their decision metrics (the hero's when nobody is)."""
    actor = next_decision_actor(states, index)
    metrics = hero_decision(states, index, actor or hero_name)
    if actor is None:
        metrics = replace(
            metrics,
            mode="neutral",
            call_amount=ZERO,
            pot_odds_pct=None,
            effective_pot=None,
            pot_before_call=None,
            uncalled_excess=None,
        )
    return actor, metrics
