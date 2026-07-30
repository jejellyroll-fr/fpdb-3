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


def aof_observed(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the number of all-ins whose complete holding was captured."""
    description = "all-ins with complete hole cards and flop captured"
    try:
        observed = int(stat_dict[player]["aof_obs"])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("Obs", description)
    return (
        float(observed),
        str(observed),
        f"Obs={observed}",
        f"observed all-ins={observed}",
        f"({observed})",
        description,
    )


def _aof_observed_frequency(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    *,
    key: str,
    abbreviation: str,
    long_label: str,
    description: str,
) -> StatTuple:
    """Format a classified holding count over the observable all-in sample."""
    try:
        observed = int(stat_dict[player]["aof_obs"])
        count = int(stat_dict[player][key])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(abbreviation, description)
    if observed <= 0:
        return format_no_data_stat(abbreviation, description, count, observed)
    fraction = count / observed
    percent = 100.0 * fraction
    return (
        fraction,
        f"{percent:3.1f}",
        f"{abbreviation}={percent:3.1f}%",
        f"{long_label} {count}/{observed} {percent:3.1f}%",
        f"({count}/{observed})",
        description,
    )


def aof_no_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return observable all-ins with no made hand."""
    return _aof_observed_frequency(
        stat_dict,
        player,
        key="aof_no_made",
        abbreviation="NoMade",
        long_label="no made hand",
        description="% of observable all-ins with no made hand",
    )


def aof_made(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return observable all-ins with at least a pair."""
    return _aof_observed_frequency(
        stat_dict,
        player,
        key="aof_made",
        abbreviation="Made",
        long_label="made hand",
        description="% of observable all-ins with a made hand",
    )


def aof_nfd(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return observable all-ins holding the nut flush draw."""
    return _aof_observed_frequency(
        stat_dict,
        player,
        key="aof_nfd",
        abbreviation="NFD",
        long_label="nut flush draw",
        description="% of observable all-ins with the nut flush draw",
    )


def aof_non_nfd(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return observable all-ins holding a non-nut flush draw."""
    return _aof_observed_frequency(
        stat_dict,
        player,
        key="aof_non_nfd",
        abbreviation="nonNFD",
        long_label="non-nut flush draw",
        description="% of observable all-ins with a non-nut flush draw",
    )


def aof_wrap9(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return observable all-ins with at least nine straight outs."""
    return _aof_observed_frequency(
        stat_dict,
        player,
        key="aof_wrap9",
        abbreviation="W9+",
        long_label="wrap 9+",
        description="% of observable all-ins with at least nine straight outs",
    )


def aof_big_wrap13(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return observable all-ins with at least thirteen straight outs."""
    return _aof_observed_frequency(
        stat_dict,
        player,
        key="aof_big_wrap13",
        abbreviation="W13+",
        long_label="big wrap 13+",
        description="% of observable all-ins with at least thirteen straight outs",
    )


def _made_distribution_stat(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    *,
    key: str,
    abbreviation: str,
    label: str,
) -> StatTuple:
    return _aof_observed_frequency(
        stat_dict,
        player,
        key=key,
        abbreviation=abbreviation,
        long_label=label,
        description=f"% of observable all-ins classified as {label}",
    )


def aof_pair(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed one-pair distribution."""
    return _made_distribution_stat(stat_dict, player, key="aof_pair", abbreviation="Pair", label="pair")


def aof_two_pair(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed two-pair distribution."""
    return _made_distribution_stat(stat_dict, player, key="aof_two_pair", abbreviation="2P", label="two pair")


def aof_trips(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed trips distribution."""
    return _made_distribution_stat(stat_dict, player, key="aof_trips", abbreviation="Trips", label="trips")


def aof_straight(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed straight distribution."""
    return _made_distribution_stat(
        stat_dict,
        player,
        key="aof_straight",
        abbreviation="Str",
        label="straight",
    )


def aof_flush(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed flush distribution."""
    return _made_distribution_stat(stat_dict, player, key="aof_flush", abbreviation="Flush", label="flush")


def aof_full_house(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed full-house distribution."""
    return _made_distribution_stat(
        stat_dict,
        player,
        key="aof_full_house",
        abbreviation="Full",
        label="full house",
    )


def aof_quads(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed quads distribution."""
    return _made_distribution_stat(stat_dict, player, key="aof_quads", abbreviation="Quads", label="quads")


def aof_straight_flush(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed straight-flush distribution."""
    return _made_distribution_stat(
        stat_dict,
        player,
        key="aof_straight_flush",
        abbreviation="SF",
        label="straight flush",
    )


def aof_weak(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Frequency of all-ins whose upper 95% pre-rake EV bound is negative."""
    description = (
        "all-ins whose modeled pre-rake EV is negative even at the upper 95% confidence bound; "
        "uncertain and unmodeled decisions are not counted as weak"
    )
    try:
        modeled = int(stat_dict[player]["aof_decision_ev"])
        weak = int(stat_dict[player]["aof_weak"])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("W", description)
    if modeled <= 0:
        return format_no_data_stat("W", description)
    fraction = weak / modeled
    percent = fraction * 100
    return (
        fraction,
        f"{percent:3.1f}",
        f"W={percent:3.1f}%",
        f"Weak AI={percent:3.1f}%",
        f"({weak}/{modeled})",
        description,
    )


def aof_known_equity(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Average equity against fully known actual opponents."""
    description = "average flop equity against actual callers whose complete cards were captured"
    try:
        count = int(stat_dict[player]["aof_known"])
        equity_sum = int(stat_dict[player]["aof_known_equity_ppm"])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("EqK", description)
    if count <= 0:
        return format_no_data_stat("EqK", description)
    fraction = equity_sum / (count * 1_000_000)
    percent = fraction * 100
    return (
        fraction,
        f"{percent:3.1f}",
        f"EqK={percent:3.1f}%",
        f"known-card equity={percent:3.1f}%",
        f"({count} analyzed)",
        description,
    )


def aof_known_ev(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Average conditional EV in BB against the actual callers."""
    description = "average EV in BB conditional on the actual callers, using only fully known pockets"
    try:
        count = int(stat_dict[player]["aof_known"])
        ev_sum = int(stat_dict[player]["aof_known_ev_bb_ppm"])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("EVact", description)
    if count <= 0:
        return format_no_data_stat("EVact", description)
    ev_bb = ev_sum / (count * 1_000_000)
    return (
        ev_bb,
        f"{ev_bb:+.2f}",
        f"EVact={ev_bb:+.2f}bb",
        f"EV vs actual callers={ev_bb:+.2f}bb",
        f"({count} analyzed)",
        description,
    )


def aof_range_equity(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Average flop equity against the versioned observed population model."""
    description = (
        "average flop equity against the room/game/role population range; "
        "showdown-biased and trained only on earlier hands"
    )
    try:
        count = int(stat_dict[player]["aof_range"])
        equity_sum = int(stat_dict[player]["aof_range_equity_ppm"])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("EqR", description)
    if count <= 0:
        return format_no_data_stat("EqR", description)
    fraction = equity_sum / (count * 1_000_000)
    percent = fraction * 100
    return (
        fraction,
        f"{percent:3.1f}",
        f"EqR={percent:3.1f}%",
        f"population-range equity={percent:3.1f}%",
        f"({count} modeled)",
        description,
    )


def aof_decision_ev(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Average pre-rake EV of fully modeled all-in decisions."""
    description = (
        "average modeled decision EV in big blinds, including fold/call branches; "
        "pre-rake until the room supplies a verified rake schedule"
    )
    try:
        count = int(stat_dict[player]["aof_decision_ev"])
        ev_sum = int(stat_dict[player]["aof_decision_ev_bb_ppm"])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("EV", description)
    if count <= 0:
        return format_no_data_stat("EV", description)
    ev_bb = ev_sum / (count * 1_000_000)
    return (
        ev_bb,
        f"{ev_bb:+.2f}",
        f"EV={ev_bb:+.2f}bb",
        f"Decision EV={ev_bb:+.2f}bb",
        f"({count} modeled)",
        description,
    )


# What a shove is worth noticing for, most telling first. A nut flush draw and
# a big wrap are reasons to commit; a bare pair or nothing at all is a read.
_AOF_MARKERS = (
    ("aof_nfd", "NFD"),
    ("aof_big_wrap13", "W13"),
    ("aof_wrap9", "W9"),
    ("aof_non_nfd", "fd"),
    ("aof_trips", "3k"),
    ("aof_two_pair", "2p"),
    ("aof_pair", "1p"),
    ("aof_no_made", "air"),
)
_AOF_SUMMARY_MARKERS = 4


def aof_summary(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return what this player shows up with, as markers rather than prose.

    The same facts the automatic notes carry, in a form that can be read
    without stopping to read. A note saying "all-in with two pair, non-nut
    flush draw" is exact and useless mid-hand: it describes one hand, in a
    sentence, in a window that has to be opened. What a player needs at the
    table is the shape of a whole history at a glance -- ``NFD×10 W9×8 air×4``
    says this opponent gets it in with the nut flush draw ten times, a wrap
    eight, and nothing at all four, which is a read; the sentence is a story.

    Only markers actually seen are shown, most telling first, and the count of
    observed shoves travels with them: four out of six is a coincidence and
    four out of sixty is a habit, and the reader cannot tell them apart from
    the markers alone.
    """
    description = "what this player shows up with, over observed all-ins"
    try:
        observed = int(stat_dict[player]["aof_obs"])
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("Shows", description)
    if observed <= 0:
        return format_no_data_stat("Shows", description)

    marks = []
    for key, label in _AOF_MARKERS:
        try:
            count = int(stat_dict[player].get(key, 0) or 0)
        except (TypeError, ValueError):
            continue
        if count:
            marks.append(f"{label}×{count}")
    if not marks:
        return format_no_data_stat("Shows", description)

    shown = " ".join(marks[:_AOF_SUMMARY_MARKERS])
    return (
        float(observed),
        shown,
        f"Shows {shown}",
        f"{' '.join(marks)} over {observed} observed all-ins",
        f"({observed})",
        description,
    )


def aof_splash_won(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return what the player has taken out of splash pots.

    Money the room adds to the pot from outside it, so it is neither in
    ``winnings`` nor in ``totalProfit`` -- the sum of every player's profit on
    a splash hand comes to minus the rake, splash excluded. A player's real
    take at these tables is therefore their profit plus this, and the two have
    to be read together or the smaller number is mistaken for the whole.

    Shown in the table's own currency. The HUD can aggregate several blind
    levels, so presenting one big-blind conversion here would be misleading.
    """
    description = "amount collected from splash pots"
    try:
        cents = int(stat_dict[player].get("aof_splash_cents", 0) or 0)
        seen = int(stat_dict[player].get("aof_splash_seen", 0) or 0)
        hits = int(stat_dict[player].get("aof_splash_hit", 0) or 0)
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("Spl", description)
    if seen <= 0:
        return format_no_data_stat("Spl", description)
    amount = cents / 100.0
    return (
        amount,
        f"{amount:.2f}",
        f"Spl={amount:.2f}",
        f"splash collected={amount:.2f} over {hits} of {seen} splash hands",
        f"({hits}/{seen})",
        description,
    )


def aof_splash_freq(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return how often the player takes a share of the splash it is offered.

    The denominator is the splash hands the player sat in, not the hands they
    played: a splash is dropped on the table, not on a player, so everyone
    seated was offered the same thing and the ones who folded are part of the
    measure rather than absent from it.

    The room pays the splash to whoever wins the pot, so this tracks winning
    those hands. It is worth its own line anyway: a player who folds through
    every splash is turning down money the room has already put on the table,
    and that shows here before it shows anywhere else.
    """
    description = "% of splash hands where the player took a share"
    try:
        return _aof_frequency(
            stat_dict,
            player,
            float(stat_dict[player].get("aof_splash_seen", 0) or 0),
            float(stat_dict[player].get("aof_splash_hit", 0) or 0),
            "Spl%",
            "splash taken",
            description,
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("Spl%", description)
