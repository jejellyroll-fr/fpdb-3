"""Postflop frequency statistics extracted from the legacy stat catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat


def postflop_ratio(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    opportunity_key: str,
    done_key: str,
    abbreviation: str,
    description: str,
) -> StatTuple:
    """Format a per-street postflop done/opportunity percentage."""
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(opportunity_key, 0))
        done = float(stat_dict[player].get(done_key, 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"{abbreviation}={percent:3.1f}%"
        return (
            stat,
            f"{percent:3.1f}",
            display,
            display,
            f"({int(done)}/{int(opportunities)})",
            description,
        )
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{abbreviation}=NA", "(0/0)", description


def three_B_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the flop 3-bet percentage."""
    return postflop_ratio(stat_dict, player, "fl3b_opp", "fl3b", "F3B", "% 3 bet flop")


def three_B_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the turn 3-bet percentage."""
    return postflop_ratio(stat_dict, player, "tn3b_opp", "tn3b", "T3B", "% 3 bet turn")


def three_B_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the river 3-bet percentage."""
    return postflop_ratio(stat_dict, player, "rv3b_opp", "rv3b", "R3B", "% 3 bet river")


def fold_to_three_B_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the fold-to-flop-3-bet percentage."""
    return postflop_ratio(stat_dict, player, "ff3b_opp", "ff3b", "FF3B", "% fold to flop 3bet")


def fold_to_three_B_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the fold-to-turn-3-bet percentage."""
    return postflop_ratio(stat_dict, player, "ft3b_opp", "ft3b", "FT3B", "% fold to turn 3bet")


def fold_to_three_B_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the fold-to-river-3-bet percentage."""
    return postflop_ratio(stat_dict, player, "fr3b_opp", "fr3b", "FR3B", "% fold to river 3bet")


def four_B_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the flop 4-bet percentage."""
    return postflop_ratio(stat_dict, player, "fl4b_opp", "fl4b", "F4B", "% 4 bet flop")


def four_B_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the turn 4-bet percentage."""
    return postflop_ratio(stat_dict, player, "tn4b_opp", "tn4b", "T4B", "% 4 bet turn")


def four_B_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the river 4-bet percentage."""
    return postflop_ratio(stat_dict, player, "rv4b_opp", "rv4b", "R4B", "% 4 bet river")


def open_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening an unopened flop."""
    return postflop_ratio(stat_dict, player, "flopen_opp", "flopen", "OPf", "% open flop")


def open_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening an unopened turn."""
    return postflop_ratio(stat_dict, player, "tnopen_opp", "tnopen", "OPt", "% open turn")


def open_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening an unopened river."""
    return postflop_ratio(stat_dict, player, "rvopen_opp", "rvopen", "OPr", "% open river")


def float_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the turn continuation frequency after floating the flop."""
    return postflop_ratio(stat_dict, player, "float_turn_chance", "float_turn_done", "FltT", "% float turn")


def float_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the river continuation frequency after floating the turn."""
    return postflop_ratio(stat_dict, player, "float_river_chance", "float_river_done", "FltR", "% float river")


def face_raise_preflop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of facing a preflop raise."""
    return postflop_ratio(stat_dict, player, "n", "p_face_raise", "FvRp", "% face raise preflop")


def face_raise_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of facing a flop raise."""
    return postflop_ratio(stat_dict, player, "saw_1", "f_face_raise", "FvRf", "% face raise flop")


def face_raise_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of facing a turn raise."""
    return postflop_ratio(stat_dict, player, "saw_2", "t_face_raise", "FvRt", "% face raise turn")


def face_raise_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of facing a river raise."""
    return postflop_ratio(stat_dict, player, "saw_3", "r_face_raise", "FvRr", "% face raise river")


def first_raise_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of making the first flop raise."""
    return postflop_ratio(stat_dict, player, "saw_1", "f_first_raise", "1Rf", "% first raise flop")


def first_raise_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of making the first turn raise."""
    return postflop_ratio(stat_dict, player, "saw_2", "t_first_raise", "1Rt", "% first raise turn")


def first_raise_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of making the first river raise."""
    return postflop_ratio(stat_dict, player, "saw_3", "r_first_raise", "1Rr", "% first raise river")


def fold_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding on the flop."""
    return postflop_ratio(stat_dict, player, "saw_1", "f_fold", "Fldf", "% fold flop")


def fold_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding on the turn."""
    return postflop_ratio(stat_dict, player, "saw_2", "t_fold", "Fldt", "% fold turn")


def fold_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding on the river."""
    return postflop_ratio(stat_dict, player, "saw_3", "r_fold", "Fldr", "% fold river")


def fold_to_squeeze(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding when facing a preflop squeeze."""
    return postflop_ratio(stat_dict, player, "sqzdef_opp", "sqzdef_fold", "FvSq", "% fold to squeeze")


def check_raise_frequency(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the combined check-raise frequency across postflop streets."""
    try:
        player_stats = stat_dict[player]
        total = float(player_stats.get("cr_1", 0) + player_stats.get("cr_2", 0) + player_stats.get("cr_3", 0))
        opportunities = float(
            player_stats.get("ccr_opp_1", 0)
            + player_stats.get("ccr_opp_2", 0)
            + player_stats.get("ccr_opp_3", 0)
        )
        stat = total / opportunities if opportunities else 0.0
        percent = 100.0 * stat
        return (
            stat,
            f"{percent:3.1f}",
            f"CRF={percent:3.1f}%",
            f"CheckRaiseFreq={percent:3.1f}%",
            f"({int(total)}/{int(opportunities)})",
            "Check-Raise Frequency",
        )
    except (KeyError, TypeError, ValueError):
        return 0.0, "NA", "CRF=NA", "CheckRaiseFreq=NA", "(0/0)", "Check-Raise Frequency"


def river_call_efficiency(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return showdowns won per river call."""
    try:
        river_calls = float(stat_dict[player].get("call_3", 0))
        showdowns_won = float(stat_dict[player].get("wmsd", 0))
        stat = showdowns_won / river_calls if river_calls > 0 else 0.0
        percent = 100.0 * stat
        return (
            stat,
            f"{percent:3.1f}",
            f"RCE={percent:3.1f}%",
            f"RiverCallEff={percent:3.1f}%",
            f"({int(showdowns_won)}/{int(river_calls)})",
            "River Call Efficiency",
        )
    except (KeyError, TypeError, ValueError):
        return 0.0, "NA", "RCE=NA", "RiverCallEff=NA", "(0/0)", "River Call Efficiency"


def street_frequency(
    stat_dict: Mapping[int, Mapping[str, Any]], player: int, opportunity_key: str, done_key: str,
    abbreviation: str, long_label: str, description: str,
) -> StatTuple:
    """Format a direct action frequency for one postflop street."""
    try:
        opportunities = float(stat_dict[player].get(opportunity_key, 0))
        done = float(stat_dict[player].get(done_key, 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = done / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(done)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(abbreviation, description)


def bet_frequency_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "saw_f", "street1Bets", "bet_f", "bet_freq_flop", "% bet frequency flop")


def bet_frequency_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "saw_t", "street2Bets", "bet_t", "bet_freq_turn", "% bet frequency turn")


def raise_frequency_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "saw_f", "street1Raises", "raise_f", "raise_freq_flop", "% raise frequency flop")


def raise_frequency_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "saw_t", "street2Raises", "raise_t", "raise_freq_turn", "% raise frequency turn")


def sd_winrate(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of winning after reaching showdown."""
    return street_frequency(stat_dict, player, "sd", "wmsd", "sd_wr", "showdown_winrate", "% showdown winrate")


def non_sd_winrate(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical derived non-showdown winrate."""
    try:
        player_stats = stat_dict[player]
        opportunities = float(player_stats.get("saw_f", 0)) - float(player_stats.get("sd", 0))
        wins = float(player_stats.get("w_w_s_1", 0)) - float(player_stats.get("wmsd", 0))
        if opportunities == 0:
            return format_no_data_stat("nsd_wr", "% non-showdown winrate")
        stat = wins / opportunities
        percent = 100.0 * stat
        return (
            stat,
            f"{percent:3.1f}",
            f"nsd_wr={percent:3.1f}%",
            f"non_showdown_winrate={percent:3.1f}%",
            f"({int(wins)}/{int(opportunities)})",
            "% non-showdown winrate",
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("nsd_wr", "% non-showdown winrate")


def float_bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical float-bet estimate from aggregate counters."""
    try:
        player_stats = stat_dict[player]
        opportunities = min(
            float(player_stats.get("street1InPosition", 0)),
            float(player_stats.get("street1Calls", 0)),
            float(player_stats.get("saw_t", 0)),
        )
        if opportunities == 0:
            return format_no_data_stat("float", "% float bet turn")
        done = min(float(player_stats.get("street2Bets", 0)), opportunities)
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"float={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% float bet turn"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("float", "% float bet turn")


def probe_bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical flop probe-bet estimate from aggregate counters."""
    try:
        player_stats = stat_dict[player]
        opportunities = float(player_stats.get("saw_f", 0)) - float(player_stats.get("cb_1", 0))
        if opportunities <= 0:
            return format_no_data_stat("probe", "% probe bet flop")
        done = min(float(player_stats.get("street1Bets", 0)), opportunities)
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"probe={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% probe bet flop"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("probe", "% probe bet flop")


def probe_bet_street(
    stat_dict: Mapping[int, Mapping[str, Any]], player: int, street: int, seen_key: str,
    abbreviation: str, long_label: str, description: str,
) -> StatTuple:
    """Return the historical probe estimate for a postflop street."""
    try:
        player_stats = stat_dict[player]
        opportunities = float(player_stats.get(seen_key, 0)) - float(player_stats.get(f"cb_{street}", 0))
        if opportunities <= 0:
            return format_no_data_stat(abbreviation, description)
        done = min(float(player_stats.get(f"street{street}Bets", 0)), opportunities)
        stat = done / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(done)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(abbreviation, description)


def probe_bet_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return probe_bet_street(stat_dict, player, 2, "saw_t", "probe_t", "probe_turn", "% probe bet turn")


def probe_bet_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return probe_bet_street(stat_dict, player, 3, "saw_r", "probe_r", "probe_river", "% probe bet river")


def cbet_by_position(
    stat_dict: Mapping[int, Mapping[str, Any]], player: int, *, in_position: bool,
) -> StatTuple:
    """Return the historical flop c-bet estimate for IP or OOP hands."""
    abbreviation = "cb_ip" if in_position else "cb_oop"
    long_label = "cbet_in_position" if in_position else "cbet_out_of_position"
    description = "% c-bet in position" if in_position else "% c-bet out of position"
    try:
        player_stats = stat_dict[player]
        seen = float(player_stats.get("saw_f", 0))
        if seen == 0:
            return format_no_data_stat(abbreviation, description)
        ip_hands = float(player_stats.get("street1InPosition", 0))
        ratio = ip_hands / seen if in_position else (seen - ip_hands) / seen
        opportunities = float(player_stats.get("cb_opp_1", 0)) * ratio
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        done = float(player_stats.get("cb_1", 0)) * ratio
        stat = done / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(done)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(abbreviation, description)


def cb_ip(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return cbet_by_position(stat_dict, player, in_position=True)


def cb_oop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return cbet_by_position(stat_dict, player, in_position=False)


def fold_to_cbet_street(
    stat_dict: Mapping[int, Mapping[str, Any]], player: int, street: int, description: str,
) -> StatTuple:
    """Format fold-to-continuation-bet frequency for one street."""
    abbreviation = f"f_cb{street}"
    long_label = f"f_cb_{street}"
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(f"f_cb_opp_{street}", 0))
        done = float(stat_dict[player].get(long_label, 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = done / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(done)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{long_label}=NA", "(0/0)", description


def f_cb1(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_to_cbet_street(stat_dict, player, 1, "% fold to continuation bet flop/4th street")
def f_cb2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_to_cbet_street(stat_dict, player, 2, "% fold to continuation bet turn/5th street")
def f_cb3(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_to_cbet_street(stat_dict, player, 3, "% fold to continuation bet river/6th street")
def f_cb4(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_to_cbet_street(stat_dict, player, 4, "% fold to continuation bet 7th street")
def fold_to_cbet_flop(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return f_cb1(stat_dict, player)
def fold_to_cbet_turn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return f_cb2(stat_dict, player)
def fold_to_cbet_river(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return f_cb3(stat_dict, player)


def check_raise_street(
    stat_dict: Mapping[int, Mapping[str, Any]], player: int, street: int, description: str,
) -> StatTuple:
    """Format check-raise frequency for one street."""
    abbreviation = f"cr{street}"
    long_label = f"cr_{street}"
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(f"ccr_opp_{street}", 0))
        done = float(stat_dict[player].get(long_label, 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = done / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(done)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{long_label}=NA", "(0/0)", description


def cr1(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return check_raise_street(stat_dict, player, 1, "% check-raise flop/4th street")
def cr2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return check_raise_street(stat_dict, player, 2, "% check-raise turn/5th street")
def cr3(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return check_raise_street(stat_dict, player, 3, "% check-raise river/6th street")
def cr4(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return check_raise_street(stat_dict, player, 4, "% check-raise 7th street")


def fold_frequency_street(
    stat_dict: Mapping[int, Mapping[str, Any]], player: int, street: int, description: str,
) -> StatTuple:
    """Format fold frequency after facing a raise on one street."""
    abbreviation = f"ff{street}"
    long_label = f"ff_{street}"
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(f"was_raised_{street}", 0))
        done = float(stat_dict[player].get(f"f_freq_{street}", 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = done / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(done)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{long_label}=NA", "(0/0)", description


def ffreq1(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_frequency_street(stat_dict, player, 1, "% fold frequency flop/4th street")
def ffreq2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_frequency_street(stat_dict, player, 2, "% fold frequency turn/5th street")
def ffreq3(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_frequency_street(stat_dict, player, 3, "% fold frequency river/6th street")
def ffreq4(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return fold_frequency_street(stat_dict, player, 4, "% fold frequency 7th street")


def cb1(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "cb_opp_1", "cb_1", "cb1", "cb_1", "% continuation bet flop/4th street")
def cb2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "cb_opp_2", "cb_2", "cb2", "cb_2", "% continuation bet turn/5th street")
def cb3(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "cb_opp_3", "cb_3", "cb3", "cb_3", "% continuation bet river/6th street")
def cb4(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return street_frequency(stat_dict, player, "cb_opp_4", "cb_4", "cb4", "cb_4", "% continuation bet 7th street")


def cbet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return aggregate continuation-bet frequency across all four streets."""
    stat = 0.0
    try:
        player_stats = stat_dict[player]
        done = sum(float(player_stats.get(f"cb_{street}", 0)) for street in range(1, 5))
        opportunities = sum(float(player_stats.get(f"cb_opp_{street}", 0)) for street in range(1, 5))
        if opportunities == 0:
            return format_no_data_stat("cbet", "% continuation bet")
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"cbet={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% continuation bet"
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "cbet=NA", "cbet=NA", "(0/0)", "% continuation bet"


def aggression_frequency_street(
    stat_dict: Mapping[int, Mapping[str, Any]], player: int, street: int, description: str,
) -> StatTuple:
    """Format aggression frequency for one postflop street."""
    abbreviation = f"a{street}"
    long_label = f"a_fq_{street}"
    stat = 0.0
    try:
        seen_key = "saw_f" if street == 1 else f"saw_{street}"
        opportunities = float(stat_dict[player].get(seen_key, 0))
        done = float(stat_dict[player].get(f"aggr_{street}", 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = done / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(done)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{long_label}=NA", "(0/0)", description


def a_freq1(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return aggression_frequency_street(stat_dict, player, 1, "Aggression frequency flop/4th street")


def a_freq2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return aggression_frequency_street(stat_dict, player, 2, "Aggression frequency turn/5th street")


def a_freq3(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return aggression_frequency_street(stat_dict, player, 3, "Aggression frequency river/6th street")


def a_freq4(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return aggression_frequency_street(stat_dict, player, 4, "Aggression frequency 7th street")


def _postflop_action_totals(player_stats: Mapping[str, Any]) -> tuple[Any, Any]:
    """Return the historical aggregate aggression and call counters."""
    aggression = sum(player_stats.get(f"aggr_{street}", 0) for street in range(1, 5))
    calls = sum(player_stats.get(f"call_{street}", 0) for street in range(1, 5))
    return aggression, calls


def a_freq_123(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return aggregate aggression frequency over the first three postflop streets."""
    stat = 0.0
    try:
        player_stats = stat_dict[player]
        total_aggression = sum(player_stats.get(f"aggr_{street}", 0) for street in range(1, 4))
        total_seen = sum(player_stats.get(f"saw_{street}", 0) for street in range(1, 4))
        if total_seen != 0:
            stat = float(total_aggression) / float(total_seen)
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"afq={percent:3.1f}%", f"post_a_fq={percent:3.1f}%", f"({int(total_aggression)}/{int(total_seen)})", "Post-flop aggression frequency"
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "afq=NA", "post_a_fq=NA", "(0/0)", "Post-flop aggression frequency"


def agg_fact(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical postflop aggression factor."""
    stat = 0.0
    try:
        aggression, calls = _postflop_action_totals(stat_dict[player])
        if aggression == 0 and calls == 0:
            return format_no_data_stat("afa", "Aggression factor", aggression, calls)
        stat = float(aggression) / float(calls) if calls > 0 else float(aggression)
        return stat / 100.0, f"{stat:2.2f}", f"afa={stat:2.2f}", f"agg_fa={stat:2.2f}", f"({int(aggression)}/{int(calls)})", "Aggression factor"
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "afa=NA", "agg_fa=NA", "(0/0)", "Aggression factor"


def agg_fact_pct(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical percentage-style postflop aggression factor."""
    stat = 0.0
    try:
        aggression, calls = _postflop_action_totals(stat_dict[player])
        if aggression == 0 and calls == 0:
            return format_no_data_stat("afap", "Aggression factor pct", aggression, calls)
        if float(calls + aggression) > 0.0:
            stat = float(aggression) / float(calls + aggression)
        return stat / 100.0, f"{stat:2.2f}", f"afap={stat:2.2f}", f"agg_fa_pct={stat:2.2f}", f"({int(aggression)}/{int(calls)})", "Aggression factor pct"
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "afap=NA", "agg_fa_pct=NA", "(0/0)", "Aggression factor pct"


def WMsF(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical won-money-when-seeing-flop statistic."""
    stat = 0.0
    description = "% won money when seen flop/4th street"
    try:
        saw_street = float(stat_dict[player].get("saw_1", 0))
        saw_flop = float(stat_dict[player].get("saw_f", 0))
        won = float(stat_dict[player].get("w_w_s_1", 0))
        if saw_flop == 0:
            return format_no_data_stat("WMsF", description)
        stat = won / saw_street if saw_street != 0 else 0
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"wf={percent:3.1f}%", f"w_w_f={percent:3.1f}%", f"({int(won)}/{int(saw_flop)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "wf=NA", "w_w_f=NA", "(0/0)", description


def wwsf(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Expose WMsF under the standard tracker name."""
    return WMsF(stat_dict, player)


def _adjusted_street_frequency(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    street: int,
    numerator_keys: tuple[str, str],
    denominator_keys: tuple[str, str],
    abbreviation: str,
    description: str,
    *,
    zero_is_no_data: bool = False,
    error_is_no_data: bool = False,
    error_description: str | None = None,
) -> StatTuple:
    """Format a street frequency built from differences of two counter pairs."""
    stat = 0.0
    try:
        player_stats = stat_dict[player]
        numerator = float(player_stats.get(numerator_keys[0], 0)) - float(player_stats.get(numerator_keys[1], 0))
        denominator = float(player_stats.get(denominator_keys[0], 0)) - float(player_stats.get(denominator_keys[1], 0))
        if denominator == 0 and zero_is_no_data:
            return format_no_data_stat(abbreviation, description)
        if denominator != 0:
            stat = numerator / denominator
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{abbreviation}={percent:3.1f}%", f"({int(numerator)}/{int(denominator)})", description
    except (KeyError, TypeError, ValueError):
        if error_is_no_data:
            return format_no_data_stat(abbreviation, description)
        return stat, "NA", f"{abbreviation}=NA", f"{abbreviation}=NA", "(0/0)", error_description or description


def dbr1(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return _adjusted_street_frequency(stat_dict, player, 1, ("aggr_1", "cb_1"), ("saw_f", "cb_opp_1"), "dbr1", "% DonkBetAndRaise flop/4th street", zero_is_no_data=True, error_is_no_data=True)


def dbr2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return _adjusted_street_frequency(stat_dict, player, 2, ("aggr_2", "cb_2"), ("saw_2", "cb_opp_2"), "dbr2", "% DonkBetAndRaise turn/5th street", zero_is_no_data=True, error_is_no_data=True)


def dbr3(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return _adjusted_street_frequency(stat_dict, player, 3, ("aggr_3", "cb_3"), ("saw_3", "cb_opp_3"), "dbr3", "% DonkBetAndRaise river/6th street")


def f_dbr1(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return _adjusted_street_frequency(stat_dict, player, 1, ("f_freq_1", "f_cb_1"), ("was_raised_1", "f_cb_opp_1"), "f_dbr1", "% Fold to DonkBetAndRaise flop/4th street", error_description="% Fold DonkBetAndRaise flop/4th street")


def f_dbr2(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return _adjusted_street_frequency(stat_dict, player, 2, ("f_freq_2", "f_cb_2"), ("was_raised_2", "f_cb_opp_2"), "f_dbr2", "% Fold to DonkBetAndRaise turn", error_description="% Fold DonkBetAndRaise turn")


def f_dbr3(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return _adjusted_street_frequency(stat_dict, player, 3, ("f_freq_3", "f_cb_3"), ("was_raised_3", "f_cb_opp_3"), "f_dbr3", "% Fold to DonkBetAndRaise river", error_description="% Fold DonkBetAndRaise river")


def triple_barrel(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical triple-barrel estimate from street c-bet rates."""
    try:
        player_stats = stat_dict[player]
        opportunities = [float(player_stats.get(f"cb_opp_{street}", 0)) for street in (1, 2, 3)]
        done = [float(player_stats.get(f"cb_{street}", 0)) for street in (1, 2, 3)]
        total_opportunities = min(opportunities)
        if total_opportunities == 0:
            return format_no_data_stat("3barrel", "% triple barrel")
        estimated_count = total_opportunities
        for count, opportunity in zip(done, opportunities, strict=True):
            estimated_count *= count / opportunity
        stat = estimated_count / total_opportunities
        percent = 100.0 * stat
        return (
            stat,
            f"{percent:3.1f}",
            f"3barrel={percent:3.1f}%",
            f"triple_barrel={percent:3.1f}%",
            f"({int(estimated_count)}/{int(total_opportunities)})",
            "% triple barrel",
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("3barrel", "% triple barrel")
