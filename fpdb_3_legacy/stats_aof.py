"""Statistics for All-in or Fold, which is not the game the others describe.

There is no preflop in All-in or Fold: the room deals the flop, and then each
player has exactly one decision to make, once, for their whole stack. fpdb
models this (``aof_omaha`` in ``Card.py``) by making the flop street zero, so
the columns the engine fills for "preflop" are in fact filled from that single
decision -- ``DerivedStats.vpip`` reads ``actionStreets[1]``, whatever street
that turns out to be.

They come from the right street, then. What they are called is another
matter: a HUD box reading "VPIP 62 / PFR 58" in a game with no preflop invites
the reader to compare it against ranges from a game that has one, and to read
the gap between the two as limping -- a thing that cannot happen here.

And a couple of conventions built around a preflop round had to be undone
before the figures were true as well as well-named. Aggression counted only
the shover and not whoever called for the same stack; and folding from a
blind, which is not giving up a preflop here but taking the one decision of
the hand, was excluded from having been a decision at all. Both are handled
where they are computed -- the second in ``DerivedStats.vpip`` -- so what
reaches here is what these names claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat


def _aof_frequency(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    opportunities: float,
    action: float,
    abbreviation: str,
    long_label: str,
    description: str,
) -> StatTuple:
    """Format one All-in or Fold frequency, keeping the sample visible.

    The sample is worth as much as the frequency here. One decision per hand
    means a player's whole record is a handful of numbers, and a shove
    percentage over six hands says nothing at all -- so the count is carried
    in the detail line the popup shows, as the other frequencies do.
    """
    if opportunities <= 0:
        return format_no_data_stat(abbreviation, description)
    fraction = action / opportunities
    percent = 100.0 * fraction
    return (
        fraction,
        f"{percent:3.1f}",
        f"{abbreviation}={percent:3.1f}%",
        f"{long_label}={percent:3.1f}%",
        f"({int(action)}/{int(opportunities)})",
        description,
    )


def aof_allin(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player commits rather than folding.

    Read from the money going in, not from who was the aggressor. Whoever
    calls a shove is all in exactly as much as whoever made it -- the stacks
    are equal and there is no later street to bet -- so counting aggression
    reported nothing at all for the caller. On the captured hand villain1
    shoved and hero called: aggression gave hero 0%, with their whole stack in
    the middle.

    The denominator is every hand in which the player had this decision to
    take, folding from a blind included -- ``DerivedStats.vpip`` counts that
    as an opportunity for this game, where elsewhere it does not.
    """
    description = "% all-in on the single All-in or Fold decision"
    try:
        return _aof_frequency(
            stat_dict,
            player,
            float(stat_dict[player].get("vpip_opp", 0)),
            float(stat_dict[player].get("vpip", 0)),
            "AI",
            "all-in",
            description,
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("AI", description)


def aof_fold(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player folds instead of moving all in.

    Read from the money going in rather than from a fold being recorded: of
    the two options only one costs anything, so whoever was asked and put
    nothing in has folded.

    Being asked is the condition. A hand that ended before the decision
    reached the player is not a fold and is not counted -- it is not in the
    denominator either, so the two figures still add up.
    """
    description = "% folded on the single All-in or Fold decision"
    try:
        opportunities = float(stat_dict[player].get("vpip_opp", 0))
        return _aof_frequency(
            stat_dict,
            player,
            opportunities,
            opportunities - float(stat_dict[player].get("vpip", 0)),
            "F",
            "fold",
            description,
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("F", description)


def aof_showdowns(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how many of the player's hands reached showdown.

    Not how many were *read*. Reaching showdown does not mean the cards were
    captured: on the recorded hand villain1 reached one holding four unknown
    cards, so a box promising a seen sample would have promised a hand nobody
    can look at. The count of shoves whose four cards were actually captured
    is the number worth having, and it is not in the aggregate the HUD reads
    -- so this says what it does measure, and is named for it.

    Reported as a count rather than a frequency because that is the question
    being asked of it: twelve showdowns is a sample, and 30% of forty is not,
    until you have done the multiplication yourself.
    """
    description = "hands of this player that reached showdown"
    try:
        shown = int(float(stat_dict[player].get("sd", 0)))
        hands = int(float(stat_dict[player].get("n", 0)))
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("SD", description)
    if hands <= 0:
        return format_no_data_stat("SD", description)
    return (
        float(shown),
        f"{shown}",
        f"SD={shown}",
        f"showdowns={shown}",
        f"({shown}/{hands})",
        description,
    )
