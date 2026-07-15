"""Preflop frequency statistics extracted from the legacy stat catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat
from fpdb_3_legacy.stats_postflop import postflop_ratio


def face_limpers(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the average number of limpers faced before acting preflop."""
    try:
        hands = float(stat_dict[player].get("n", 0))
        total = float(stat_dict[player].get("face_limpers", 0))
        if hands == 0:
            return format_no_data_stat("FLmp", "avg limpers faced preflop")
        stat = total / hands
        return (
            stat,
            f"{stat:3.1f}",
            f"FLmp={stat:3.1f}",
            f"FLmp={stat:3.1f}",
            f"({int(total)}/{int(hands)})",
            "avg limpers faced preflop",
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("FLmp", "avg limpers faced preflop")


def straddle(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of voluntarily posting a straddle."""
    return postflop_ratio(stat_dict, player, "n", "straddle_done", "Str", "% straddle")


def gp_2x(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening for less than 40 percent of the stack."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_2x", "2X", "% open-raise (<40% stack)")


def gp_os(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of open-shoving at least 40 percent of the stack."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_os", "OS", "% open-shove (>=40% stack)")


def gp_limp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of open-limping."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_limp", "Limp", "% open-limp")


def fold_to_allin(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding when facing an all-in."""
    return postflop_ratio(stat_dict, player, "faced_allin", "fold_allin", "FvAI", "% fold to all-in")


def preflop_action_by_position(stat_dict: Mapping[int, Mapping[str, Any]], player: int, prefix: str, position: str, label: str) -> StatTuple:
    """Format a preflop action frequency in one HUD position bucket."""
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(f"{prefix}_opp_{position}", 0))
        done = float(stat_dict[player].get(f"{prefix}_{position}", 0))
        if opportunities == 0:
            return format_no_data_stat(label, f"% {label} preflop")
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"{label}={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({done:.0f}/{opportunities:.0f})", f"% {label} preflop"
    except (AttributeError, KeyError, TypeError, ValueError):
        return stat, "NA", f"{label}=NA", f"{label}=NA", "(0/0)", f"% {label} preflop"


def three_bet_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "bb", "3B BB")
def three_bet_sb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "sb", "3B SB")
def three_bet_btn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "btn", "3B BTN")
def three_bet_co(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "co", "3B CO")
def three_bet_mp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "mp", "3B MP")
def three_bet_ep(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "tb", "ep", "3B EP")
def four_bet_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "bb", "4B BB")
def four_bet_sb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "sb", "4B SB")
def four_bet_btn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "btn", "4B BTN")
def four_bet_co(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "co", "4B CO")
def four_bet_mp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "mp", "4B MP")
def four_bet_ep(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "fb", "ep", "4B EP")
def squeeze_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "bb", "SQZ BB")
def squeeze_sb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "sb", "SQZ SB")
def squeeze_btn(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "btn", "SQZ BTN")
def squeeze_co(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "co", "SQZ CO")
def squeeze_mp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "mp", "SQZ MP")
def squeeze_ep(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return preflop_action_by_position(stat_dict, player, "sqz", "ep", "SQZ EP")


def preflop_range(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    action_key: str,
    label: str,
    description: str,
) -> StatTuple:
    """Format the observed starting-hand range for a preflop action."""
    stat = 0.0
    try:
        hands = float(stat_dict[player].get("n", 0))
        actions = float(stat_dict[player].get(action_key, 0))
        if hands == 0:
            return format_no_data_stat(label, description)
        stat = actions / hands
        percent = 100.0 * stat
        display = f"{label}={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({actions:.0f}/{hands:.0f})", description
    except (AttributeError, KeyError, TypeError, ValueError):
        return stat, "NA", f"{label}=NA", f"{label}=NA", "(0/0)", description


def three_bet_range(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed percentage of dealt hands that were 3-bet."""
    return preflop_range(stat_dict, player, "tb_0", "3BR", "3-bet range")


def four_bet_range(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed percentage of dealt hands that were 4-bet."""
    return preflop_range(stat_dict, player, "fb_0", "4BR", "4-bet range")


def squeeze_range(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the observed percentage of dealt hands that were squeezed."""
    return preflop_range(stat_dict, player, "sqz_0", "SQZR", "squeeze range")


def rfi_total(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the estimated total raise-first-in frequency."""
    try:
        opportunities = float(stat_dict[player].get("pfr_opp", 0))
        raises = float(stat_dict[player].get("pfr", 0))
        three_bets = float(stat_dict[player].get("3bet", 0))
        if opportunities == 0:
            return format_no_data_stat("rfi", "% raise first in")
        done = max(0.0, raises - three_bets)
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"rfi={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% raise first in"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("rfi", "% raise first in")


def rfi_position(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    position: str,
    long_name: str,
    description: str,
) -> StatTuple:
    """Format raise-first-in frequency for an aggregated position bucket."""
    label = f"rfi_{position}"
    try:
        opportunities = float(stat_dict[player].get(f"rfi_opp_{position}", 0))
        done = float(stat_dict[player].get(label, 0))
        if opportunities == 0:
            return format_no_data_stat(label, description)
        stat = done / opportunities
        percent = 100.0 * stat
        return (
            stat,
            f"{percent:3.1f}",
            f"{label}={percent:3.1f}%",
            f"{long_name}={percent:3.1f}%",
            f"({int(done)}/{int(opportunities)})",
            description,
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat(label, description)


def rfi_early_position(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return rfi_position(stat_dict, player, "ep", "rfi_early_pos", "% RFI early position")


def rfi_middle_position(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return rfi_position(stat_dict, player, "mp", "rfi_middle_pos", "% RFI middle position")


def rfi_late_position(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    return rfi_position(stat_dict, player, "lp", "rfi_late_pos", "% RFI late position")


def iso(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return no data for isolation raises, which HudCache cannot aggregate."""
    return format_no_data_stat("iso", "% isolation raise (deprecated)")


def three_bet_vs_steal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return no data for 3-bet versus steal without cross-player context."""
    return format_no_data_stat("3bvs", "% 3bet vs steal (deprecated)")


def call_vs_steal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return no data for call versus steal without cross-player context."""
    return format_no_data_stat("cvs", "% call vs steal (deprecated)")


def cold_call(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the preflop cold-call frequency."""
    try:
        opportunities = float(stat_dict[player].get("CAR_opp_0", 0))
        done = float(stat_dict[player].get("CAR_0", 0))
        if opportunities == 0:
            return format_no_data_stat("cc", "% cold call preflop")
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"cc={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% cold call preflop"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("cc", "% cold call preflop")


def limp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the estimated limp frequency as VPIP actions minus raises."""
    try:
        opportunities = float(stat_dict[player].get("vpip_opp", 0))
        done = float(stat_dict[player].get("vpip", 0)) - float(stat_dict[player].get("pfr", 0))
        if opportunities == 0:
            return format_no_data_stat("limp", "% limp preflop")
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"limp={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% limp preflop"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("limp", "% limp preflop")


def open_limp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of being first into the pot with a limp."""
    try:
        opportunities = float(stat_dict[player].get("open_limp_opp", 0))
        done = float(stat_dict[player].get("open_limp", 0))
        if opportunities == 0:
            return format_no_data_stat("open_limp", "% open limp preflop")
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"openlimp={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% open limp preflop"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("open_limp", "% open limp preflop")


def vpip_pfr_ratio(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the ratio between VPIP and preflop-raise frequencies."""
    try:
        player_stats = stat_dict[player]
        vpip_opp = float(player_stats.get("vpip_opp", 0))
        pfr_opp = float(player_stats.get("pfr_opp", 0))
        vpip_count = float(player_stats.get("vpip", 0))
        pfr_count = float(player_stats.get("pfr", 0))
        if vpip_opp == 0 or pfr_opp == 0:
            return format_no_data_stat("v/p", "VPIP/PFR ratio")
        vpip = vpip_count / vpip_opp
        pfr = pfr_count / pfr_opp
        stat = vpip / pfr if pfr > 0 else float("inf")
        return (
            stat,
            f"{stat:2.2f}",
            f"v/p={stat:2.2f}",
            f"vpip/pfr={stat:2.2f}",
            f"({int(vpip_count)}/{int(vpip_opp)})/({int(pfr_count)}/{int(pfr_opp)})",
            "VPIP/PFR ratio",
        )
    except (KeyError, TypeError, ValueError):
        return float("inf"), "NA", "v/p=NA", "vpip/pfr=NA", "(0/0)/(0/0)", "VPIP/PFR ratio"


def fold_vs_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding when facing a preflop 4-bet."""
    try:
        opportunities = float(stat_dict[player].get("F4B_opp_0", 0))
        done = float(stat_dict[player].get("F4B_0", 0))
        if opportunities == 0:
            return format_no_data_stat("f4b", "% fold vs 4bet")
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"f4b={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% fold vs 4bet"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("f4b", "% fold vs 4bet")


def resteal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical resteal estimate from aggregate 3-bet counters."""
    try:
        opportunities = float(stat_dict[player].get("tb_opp_0", 0)) * 0.6
        if opportunities == 0:
            return format_no_data_stat("resteal", "% resteal")
        done = float(stat_dict[player].get("tb_0", 0)) * 0.7
        stat = done / opportunities
        percent = 100.0 * stat
        display = f"resteal={percent:3.1f}%"
        return stat, f"{percent:3.1f}", display, display, f"({int(done)}/{int(opportunities)})", "% resteal"
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("resteal", "% resteal")


def _preflop_response(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    opportunity_key: str,
    action_key: str,
    abbreviation: str,
    long_label: str,
    description: str,
) -> StatTuple:
    """Format a historical preflop response action and opportunity pair."""
    stat = 0.0
    try:
        player_stats = stat_dict[player]
        opportunities = float(player_stats.get(opportunity_key, 0))
        action = player_stats[action_key]
        if opportunities != 0:
            stat = float(action) / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(action)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{long_label}=NA", "(0/0)", description


def car0(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of calling a preflop raise."""
    return _preflop_response(stat_dict, player, "car_opp_0", "car_0", "CAR0", "CAR_pf", "% called a raise preflop")


def f_3bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return fold-to-3-bet frequency preflop or on third street."""
    return _preflop_response(stat_dict, player, "f3b_opp_0", "f3b_0", "F3B", "F3B_pf", "% fold to 3 bet preflop/3rd street")


def f_4bet(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return fold-to-4-bet frequency preflop or on third street."""
    return _preflop_response(stat_dict, player, "f4b_opp_0", "f4b_0", "F4B", "F4B_pf", "% fold to 4 bet preflop/3rd street")


def _preflop_opportunity_frequency(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    opportunity_key: str,
    action_key: str,
    abbreviation: str,
    long_label: str,
    description: str,
) -> StatTuple:
    """Format a preflop frequency whose zero-opportunity state means no data."""
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(opportunity_key, 0))
        action = float(stat_dict[player].get(action_key, 0))
        if opportunities == 0:
            return format_no_data_stat(abbreviation, description)
        stat = action / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(action)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{long_label}=NA", "(0/0)", description


def squeeze(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return preflop squeeze frequency."""
    return _preflop_opportunity_frequency(stat_dict, player, "sqz_opp_0", "sqz_0", "SQZ", "SQZ_pf", "% squeeze preflop")


def raiseToSteal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return raise-to-steal frequency."""
    return _preflop_opportunity_frequency(stat_dict, player, "rts_opp", "rts", "RST", "RST_pf", "% raise to steal")


def three_B(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return 3-bet frequency preflop or on third street."""
    return _preflop_opportunity_frequency(stat_dict, player, "tb_opp_0", "tb_0", "3B", "3B_pf", "% 3 bet preflop/3rd street")


def four_B(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return 4-bet frequency preflop or on third street."""
    return _preflop_opportunity_frequency(stat_dict, player, "fb_opp_0", "fb_0", "4B", "4B", "% 4 bet preflop/3rd street")


def cfour_B(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return cold-4-bet frequency preflop or on third street."""
    return _preflop_opportunity_frequency(stat_dict, player, "cfb_opp_0", "cfb_0", "C4B", "C4B_pf", "% cold 4 bet preflop/3rd street")


def fbr(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical four-bet range estimate."""
    stat = 0.0
    try:
        player_stats = stat_dict[player]
        four_bet_opportunities = float(player_stats.get("fb_opp_0", 0))
        pfr_opportunities = float(player_stats.get("n", 0))
        if four_bet_opportunities != 0 and pfr_opportunities != 0:
            stat = (float(player_stats["fb_0"]) / four_bet_opportunities) * (float(player_stats["pfr"]) / pfr_opportunities)
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"fbr={percent:3.1f}%", f"4Brange={percent:3.1f}%", "(pfr*four_B)", "4 bet range"
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "fbr=NA", "fbr=NA", "(pfr*four_B)", "4 bet range"


def ctb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the historical call-three-bet estimate."""
    stat = 0.0
    try:
        player_stats = stat_dict[player]
        opportunities = float(player_stats.get("f3b_opp_0", 0))
        if opportunities != 0:
            stat = (float(player_stats["f3b_opp_0"]) - float(player_stats["f3b_0"]) - float(player_stats["fb_0"])) / opportunities
        calls = float(player_stats["f3b_opp_0"]) - player_stats["fb_0"] - player_stats["f3b_0"]
        displayed_opportunities = player_stats["fb_opp_0"]
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"ctb={percent:3.1f}%", f"call3B={percent:3.1f}%", f"({int(calls)}/{int(displayed_opportunities)})", "% call 3 bet"
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "ctb=NA", "ctb=NA", "(0/0)", "% call 3 bet"


def f_SB_steal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return small-blind fold-to-steal frequency."""
    return _preflop_opportunity_frequency(stat_dict, player, "sbstolen", "sbnotdef", "fSB", "fSB_s", "% folded SB to steal")


def f_BB_steal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return big-blind fold-to-steal frequency."""
    return _preflop_opportunity_frequency(stat_dict, player, "bbstolen", "bbnotdef", "fBB", "fBB_s", "% folded BB to steal")


def f_steal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return aggregate blind fold-to-steal frequency."""
    stat = 0.0
    try:
        player_stats = stat_dict[player]
        folded = player_stats.get("sbnotdef", 0) + player_stats.get("bbnotdef", 0)
        opportunities = player_stats.get("sbstolen", 0) + player_stats.get("bbstolen", 0)
        if opportunities == 0:
            return format_no_data_stat("fB", "% folded blind to steal")
        stat = float(folded) / float(opportunities)
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"fB={percent:3.1f}%", f"fB_s={percent:3.1f}%", f"({int(folded)}/{int(opportunities)})", "% folded blind to steal"
    except (KeyError, TypeError, ValueError):
        return stat, "NA", "fB=NA", "fB_s=NA", "(0/0)", "% folded blind to steal"


def _labeled_preflop_frequency(
    stat_dict: Mapping[int, Mapping[str, Any]],
    player: int,
    opportunity_key: str,
    action_key: str,
    no_data_label: str,
    abbreviation: str,
    long_label: str,
    description: str,
) -> StatTuple:
    """Format a frequency while preserving its historical no-data label."""
    stat = 0.0
    try:
        opportunities = float(stat_dict[player].get(opportunity_key, 0))
        action = float(stat_dict[player].get(action_key, 0))
        if opportunities == 0:
            return format_no_data_stat(no_data_label, description)
        stat = action / opportunities
        percent = 100.0 * stat
        return stat, f"{percent:3.1f}", f"{abbreviation}={percent:3.1f}%", f"{long_label}={percent:3.1f}%", f"({int(action)}/{int(opportunities)})", description
    except (KeyError, TypeError, ValueError):
        return stat, "NA", f"{abbreviation}=NA", f"{long_label}=NA", "(0/0)", description


def steal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return attempted-steal frequency."""
    return _labeled_preflop_frequency(stat_dict, player, "steal_opp", "steal", "steal", "st", "steal", "% steal attempted")


def s_steal(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return successful-steal frequency."""
    return _labeled_preflop_frequency(stat_dict, player, "steal", "suc_st", "s_st", "s_st", "s_steal", "% steal success")


def vpip(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return voluntarily-put-money-in-pot frequency."""
    return _labeled_preflop_frequency(stat_dict, player, "vpip_opp", "vpip", "vpip", "v", "vpip", "Voluntarily put in preflop/3rd street %")


def pfr(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return preflop or third-street raise frequency."""
    return _labeled_preflop_frequency(stat_dict, player, "pfr_opp", "pfr", "pfr", "p", "pfr", "Preflop/3rd street raise %")
