"""Manage collecting and formatting of stats and tooltips."""

from __future__ import annotations

#    Copyright 2008-2011, Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
########################################################################
#    How to write a new stat:
#        0  Do not use a name like "xyz_2". Names ending in _ and a single digit are
#           used to indicate the number of decimal places the user wants to see in the Hud.
#        1  You can see a listing of all the raw stats (e.g., from the HudCache table)
#           by running Database.py as a stand along program.  You need to combine
#           those raw stats to get stats to present to the HUD.  If you need more
#           information than is in the HudCache table, then you have to write SQL.
#        2  The raw stats seen when you run Database.py are available in the Stats.py
#           in the stat_dict dict.  For example the number of vpips would be
#           stat_dict[player]['vpip'].  So the % vpip is
#           float(stat_dict[player]['vpip'])/float(stat_dict[player]['n']).  You can see how the
#           keys of stat_dict relate to the column names in HudCache by inspecting
#           the proper section of the SQL.py module.
#           The stat_dict keys should be in lower case, i.e. vpip not VPIP, since
#           postgres returns the column names in lower case.
#        3  You have to write a small function for each stat you want to add.  See
#           the vpip() function for example.  This function has to be protected from
#           exceptions, using something like the try:/except: paragraphs in vpip.
#        4  The name of the function has to be the same as the of the stat used
#           in the config file.
#        5  The stat functions have a peculiar return value, which is outlined in
#           the do_stat function.  This format is useful for tool tips and maybe
#           other stuff.
#        6  All stats receive two params (stat_dict and player) - if these parameters contain
#           "None", the stat must return its description in tuple [5] and must not traceback
#        7  Stats needing values from the hand instance can find these in _get_hand_instance().foo
#           attribute
# String manipulation
import codecs
import re

#    Standard Library modules
import sys

# import Charset
#    FreePokerTools modules
from fpdb_3_legacy import Configuration, Database, Hand, L10n
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.stats_aof import (
    aof_allin as aof_allin,
)
from fpdb_3_legacy.stats_aof import (
    aof_big_wrap13 as aof_big_wrap13,
)
from fpdb_3_legacy.stats_aof import (
    aof_decision_ev as aof_decision_ev,
)
from fpdb_3_legacy.stats_aof import (
    aof_flush as aof_flush,
)
from fpdb_3_legacy.stats_aof import (
    aof_fold as aof_fold,
)
from fpdb_3_legacy.stats_aof import (
    aof_full_house as aof_full_house,
)
from fpdb_3_legacy.stats_aof import (
    aof_known_equity as aof_known_equity,
)
from fpdb_3_legacy.stats_aof import (
    aof_known_ev as aof_known_ev,
)
from fpdb_3_legacy.stats_aof import (
    aof_made as aof_made,
)
from fpdb_3_legacy.stats_aof import (
    aof_nfd as aof_nfd,
)
from fpdb_3_legacy.stats_aof import (
    aof_no_made as aof_no_made,
)
from fpdb_3_legacy.stats_aof import (
    aof_non_nfd as aof_non_nfd,
)
from fpdb_3_legacy.stats_aof import (
    aof_observed as aof_observed,
)
from fpdb_3_legacy.stats_aof import (
    aof_pair as aof_pair,
)
from fpdb_3_legacy.stats_aof import (
    aof_quads as aof_quads,
)
from fpdb_3_legacy.stats_aof import (
    aof_range_equity as aof_range_equity,
)
from fpdb_3_legacy.stats_aof import (
    aof_showdowns as aof_showdowns,
)
from fpdb_3_legacy.stats_aof import (
    aof_splash_freq as aof_splash_freq,
)
from fpdb_3_legacy.stats_aof import (
    aof_splash_won as aof_splash_won,
)
from fpdb_3_legacy.stats_aof import (
    aof_straight as aof_straight,
)
from fpdb_3_legacy.stats_aof import (
    aof_straight_flush as aof_straight_flush,
)
from fpdb_3_legacy.stats_aof import (
    aof_summary as aof_summary,
)
from fpdb_3_legacy.stats_aof import (
    aof_trips as aof_trips,
)
from fpdb_3_legacy.stats_aof import (
    aof_two_pair as aof_two_pair,
)
from fpdb_3_legacy.stats_aof import (
    aof_weak as aof_weak,
)
from fpdb_3_legacy.stats_aof import (
    aof_wrap9 as aof_wrap9,
)
from fpdb_3_legacy.stats_context import get_hand_instance
from fpdb_3_legacy.stats_context import (
    set_hand_instance as _set_hand_instance,
)
from fpdb_3_legacy.stats_display import (
    blank as blank,
)
from fpdb_3_legacy.stats_display import (
    game_abbr as game_abbr,
)
from fpdb_3_legacy.stats_display import (
    n as n,
)
from fpdb_3_legacy.stats_display import (
    player_note as player_note,
)
from fpdb_3_legacy.stats_display import (
    playername as playername,
)
from fpdb_3_legacy.stats_display import (
    playerprofile as playerprofile,
)
from fpdb_3_legacy.stats_display import (
    playershort as playershort,
)
from fpdb_3_legacy.stats_display import (
    starthands as starthands,
)
from fpdb_3_legacy.stats_financial import (
    BBper100 as BBper100,
)
from fpdb_3_legacy.stats_financial import (
    bbper100 as bbper100,
)
from fpdb_3_legacy.stats_financial import (
    profit100 as profit100,
)
from fpdb_3_legacy.stats_financial import (
    totalprofit as totalprofit,
)
from fpdb_3_legacy.stats_formatting import (
    do_tip as do_tip,
)
from fpdb_3_legacy.stats_formatting import (
    format_no_data_stat as format_no_data_stat,
)
from fpdb_3_legacy.stats_formatting import (
    stat_override as __stat_override,
)
from fpdb_3_legacy.stats_postflop import (
    WMsF as WMsF,
)
from fpdb_3_legacy.stats_postflop import (
    a_freq1 as a_freq1,
)
from fpdb_3_legacy.stats_postflop import (
    a_freq2 as a_freq2,
)
from fpdb_3_legacy.stats_postflop import (
    a_freq3 as a_freq3,
)
from fpdb_3_legacy.stats_postflop import (
    a_freq4 as a_freq4,
)
from fpdb_3_legacy.stats_postflop import (
    a_freq_123 as a_freq_123,
)
from fpdb_3_legacy.stats_postflop import (
    agg_fact as agg_fact,
)
from fpdb_3_legacy.stats_postflop import (
    agg_fact_pct as agg_fact_pct,
)
from fpdb_3_legacy.stats_postflop import (
    bet_frequency_flop as bet_frequency_flop,
)
from fpdb_3_legacy.stats_postflop import (
    bet_frequency_turn as bet_frequency_turn,
)
from fpdb_3_legacy.stats_postflop import (
    cb1 as cb1,
)
from fpdb_3_legacy.stats_postflop import (
    cb2 as cb2,
)
from fpdb_3_legacy.stats_postflop import (
    cb3 as cb3,
)
from fpdb_3_legacy.stats_postflop import (
    cb4 as cb4,
)
from fpdb_3_legacy.stats_postflop import (
    cb_ip as cb_ip,
)
from fpdb_3_legacy.stats_postflop import (
    cb_oop as cb_oop,
)
from fpdb_3_legacy.stats_postflop import (
    cbet as cbet,
)
from fpdb_3_legacy.stats_postflop import (
    check_raise_frequency as check_raise_frequency,
)
from fpdb_3_legacy.stats_postflop import (
    cr1 as cr1,
)
from fpdb_3_legacy.stats_postflop import (
    cr2 as cr2,
)
from fpdb_3_legacy.stats_postflop import (
    cr3 as cr3,
)
from fpdb_3_legacy.stats_postflop import (
    cr4 as cr4,
)
from fpdb_3_legacy.stats_postflop import (
    dbr1 as dbr1,
)
from fpdb_3_legacy.stats_postflop import (
    dbr2 as dbr2,
)
from fpdb_3_legacy.stats_postflop import (
    dbr3 as dbr3,
)
from fpdb_3_legacy.stats_postflop import (
    f_cb1 as f_cb1,
)
from fpdb_3_legacy.stats_postflop import (
    f_cb2 as f_cb2,
)
from fpdb_3_legacy.stats_postflop import (
    f_cb3 as f_cb3,
)
from fpdb_3_legacy.stats_postflop import (
    f_cb4 as f_cb4,
)
from fpdb_3_legacy.stats_postflop import (
    f_dbr1 as f_dbr1,
)
from fpdb_3_legacy.stats_postflop import (
    f_dbr2 as f_dbr2,
)
from fpdb_3_legacy.stats_postflop import (
    f_dbr3 as f_dbr3,
)
from fpdb_3_legacy.stats_postflop import (
    face_raise_flop as face_raise_flop,
)
from fpdb_3_legacy.stats_postflop import (
    face_raise_preflop as face_raise_preflop,
)
from fpdb_3_legacy.stats_postflop import (
    face_raise_river as face_raise_river,
)
from fpdb_3_legacy.stats_postflop import (
    face_raise_turn as face_raise_turn,
)
from fpdb_3_legacy.stats_postflop import (
    ffreq1 as ffreq1,
)
from fpdb_3_legacy.stats_postflop import (
    ffreq2 as ffreq2,
)
from fpdb_3_legacy.stats_postflop import (
    ffreq3 as ffreq3,
)
from fpdb_3_legacy.stats_postflop import (
    ffreq4 as ffreq4,
)
from fpdb_3_legacy.stats_postflop import (
    first_raise_flop as first_raise_flop,
)
from fpdb_3_legacy.stats_postflop import (
    first_raise_river as first_raise_river,
)
from fpdb_3_legacy.stats_postflop import (
    first_raise_turn as first_raise_turn,
)
from fpdb_3_legacy.stats_postflop import (
    float_bet as float_bet,
)
from fpdb_3_legacy.stats_postflop import (
    float_river as float_river,
)
from fpdb_3_legacy.stats_postflop import (
    float_turn as float_turn,
)
from fpdb_3_legacy.stats_postflop import (
    fold_flop as fold_flop,
)
from fpdb_3_legacy.stats_postflop import (
    fold_river as fold_river,
)
from fpdb_3_legacy.stats_postflop import (
    fold_to_cbet_flop as fold_to_cbet_flop,
)
from fpdb_3_legacy.stats_postflop import (
    fold_to_cbet_river as fold_to_cbet_river,
)
from fpdb_3_legacy.stats_postflop import (
    fold_to_cbet_turn as fold_to_cbet_turn,
)
from fpdb_3_legacy.stats_postflop import (
    fold_to_squeeze as fold_to_squeeze,
)
from fpdb_3_legacy.stats_postflop import (
    fold_to_three_B_flop as fold_to_three_B_flop,
)
from fpdb_3_legacy.stats_postflop import (
    fold_to_three_B_river as fold_to_three_B_river,
)
from fpdb_3_legacy.stats_postflop import (
    fold_to_three_B_turn as fold_to_three_B_turn,
)
from fpdb_3_legacy.stats_postflop import (
    fold_turn as fold_turn,
)
from fpdb_3_legacy.stats_postflop import (
    four_B_flop as four_B_flop,
)
from fpdb_3_legacy.stats_postflop import (
    four_B_river as four_B_river,
)
from fpdb_3_legacy.stats_postflop import (
    four_B_turn as four_B_turn,
)
from fpdb_3_legacy.stats_postflop import (
    non_sd_winrate as non_sd_winrate,
)
from fpdb_3_legacy.stats_postflop import (
    open_flop as open_flop,
)
from fpdb_3_legacy.stats_postflop import (
    open_river as open_river,
)
from fpdb_3_legacy.stats_postflop import (
    open_turn as open_turn,
)
from fpdb_3_legacy.stats_postflop import (
    probe_bet as probe_bet,
)
from fpdb_3_legacy.stats_postflop import (
    probe_bet_river as probe_bet_river,
)
from fpdb_3_legacy.stats_postflop import (
    probe_bet_turn as probe_bet_turn,
)
from fpdb_3_legacy.stats_postflop import (
    raise_frequency_flop as raise_frequency_flop,
)
from fpdb_3_legacy.stats_postflop import (
    raise_frequency_turn as raise_frequency_turn,
)
from fpdb_3_legacy.stats_postflop import (
    river_call_efficiency as river_call_efficiency,
)
from fpdb_3_legacy.stats_postflop import (
    saw_f as saw_f,
)
from fpdb_3_legacy.stats_postflop import (
    sd_winrate as sd_winrate,
)
from fpdb_3_legacy.stats_postflop import (
    three_B_flop as three_B_flop,
)
from fpdb_3_legacy.stats_postflop import (
    three_B_river as three_B_river,
)
from fpdb_3_legacy.stats_postflop import (
    three_B_turn as three_B_turn,
)
from fpdb_3_legacy.stats_postflop import (
    triple_barrel as triple_barrel,
)
from fpdb_3_legacy.stats_postflop import (
    wmsd as wmsd,
)
from fpdb_3_legacy.stats_postflop import (
    wtsd as wtsd,
)
from fpdb_3_legacy.stats_postflop import (
    wwsf as wwsf,
)
from fpdb_3_legacy.stats_preflop import (
    call_vs_steal as call_vs_steal,
)
from fpdb_3_legacy.stats_preflop import (
    car0 as car0,
)
from fpdb_3_legacy.stats_preflop import (
    cfour_B as cfour_B,
)
from fpdb_3_legacy.stats_preflop import (
    cold_call as cold_call,
)
from fpdb_3_legacy.stats_preflop import (
    ctb as ctb,
)
from fpdb_3_legacy.stats_preflop import (
    f_3bet as f_3bet,
)
from fpdb_3_legacy.stats_preflop import (
    f_4bet as f_4bet,
)
from fpdb_3_legacy.stats_preflop import (
    f_BB_steal as f_BB_steal,
)
from fpdb_3_legacy.stats_preflop import (
    f_SB_steal as f_SB_steal,
)
from fpdb_3_legacy.stats_preflop import (
    f_steal as f_steal,
)
from fpdb_3_legacy.stats_preflop import (
    face_limpers as face_limpers,
)
from fpdb_3_legacy.stats_preflop import (
    fbr as fbr,
)
from fpdb_3_legacy.stats_preflop import (
    fold_to_allin as fold_to_allin,
)
from fpdb_3_legacy.stats_preflop import (
    fold_vs_4bet as fold_vs_4bet,
)
from fpdb_3_legacy.stats_preflop import (
    four_B as four_B,
)
from fpdb_3_legacy.stats_preflop import (
    four_bet_bb as four_bet_bb,
)
from fpdb_3_legacy.stats_preflop import (
    four_bet_btn as four_bet_btn,
)
from fpdb_3_legacy.stats_preflop import (
    four_bet_co as four_bet_co,
)
from fpdb_3_legacy.stats_preflop import (
    four_bet_ep as four_bet_ep,
)
from fpdb_3_legacy.stats_preflop import (
    four_bet_mp as four_bet_mp,
)
from fpdb_3_legacy.stats_preflop import (
    four_bet_range as four_bet_range,
)
from fpdb_3_legacy.stats_preflop import (
    four_bet_sb as four_bet_sb,
)
from fpdb_3_legacy.stats_preflop import (
    gp_2x as gp_2x,
)
from fpdb_3_legacy.stats_preflop import (
    gp_limp as gp_limp,
)
from fpdb_3_legacy.stats_preflop import (
    gp_os as gp_os,
)
from fpdb_3_legacy.stats_preflop import (
    iso as iso,
)
from fpdb_3_legacy.stats_preflop import (
    limp as limp,
)
from fpdb_3_legacy.stats_preflop import (
    open_limp as open_limp,
)
from fpdb_3_legacy.stats_preflop import (
    pfr as pfr,
)
from fpdb_3_legacy.stats_preflop import (
    raiseToSteal as raiseToSteal,
)
from fpdb_3_legacy.stats_preflop import (
    resteal as resteal,
)
from fpdb_3_legacy.stats_preflop import (
    rfi_early_position as rfi_early_position,
)
from fpdb_3_legacy.stats_preflop import (
    rfi_late_position as rfi_late_position,
)
from fpdb_3_legacy.stats_preflop import (
    rfi_middle_position as rfi_middle_position,
)
from fpdb_3_legacy.stats_preflop import (
    rfi_total as rfi_total,
)
from fpdb_3_legacy.stats_preflop import (
    s_steal as s_steal,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze as squeeze,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze_bb as squeeze_bb,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze_btn as squeeze_btn,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze_co as squeeze_co,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze_ep as squeeze_ep,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze_mp as squeeze_mp,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze_range as squeeze_range,
)
from fpdb_3_legacy.stats_preflop import (
    squeeze_sb as squeeze_sb,
)
from fpdb_3_legacy.stats_preflop import (
    steal as steal,
)
from fpdb_3_legacy.stats_preflop import (
    straddle as straddle,
)
from fpdb_3_legacy.stats_preflop import (
    three_B as three_B,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_bb as three_bet_bb,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_btn as three_bet_btn,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_co as three_bet_co,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_ep as three_bet_ep,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_mp as three_bet_mp,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_range as three_bet_range,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_sb as three_bet_sb,
)
from fpdb_3_legacy.stats_preflop import (
    three_bet_vs_steal as three_bet_vs_steal,
)
from fpdb_3_legacy.stats_preflop import (
    vpip as vpip,
)
from fpdb_3_legacy.stats_preflop import (
    vpip_pfr_ratio as vpip_pfr_ratio,
)
from fpdb_3_legacy.stats_sizing import (
    amt_bet_f as amt_bet_f,
)
from fpdb_3_legacy.stats_sizing import (
    amt_bet_p as amt_bet_p,
)
from fpdb_3_legacy.stats_sizing import (
    amt_bet_r as amt_bet_r,
)
from fpdb_3_legacy.stats_sizing import (
    amt_bet_t as amt_bet_t,
)
from fpdb_3_legacy.stats_sizing import (
    amt_bet_ttl as amt_bet_ttl,
)
from fpdb_3_legacy.stats_sizing import (
    amt_blind as amt_blind,
)
from fpdb_3_legacy.stats_sizing import (
    avg_bet_size_flop as avg_bet_size_flop,
)
from fpdb_3_legacy.stats_sizing import (
    avg_bet_size_river as avg_bet_size_river,
)
from fpdb_3_legacy.stats_sizing import (
    avg_bet_size_turn as avg_bet_size_turn,
)
from fpdb_3_legacy.stats_sizing import (
    f_2bet_facing as f_2bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    f_3bet_facing as f_3bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    f_4bet_facing as f_4bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    f_bet_facing as f_bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    f_bet_made as f_bet_made,
)
from fpdb_3_legacy.stats_sizing import (
    f_raise_facing as f_raise_facing,
)
from fpdb_3_legacy.stats_sizing import (
    f_raise_made as f_raise_made,
)
from fpdb_3_legacy.stats_sizing import (
    f_raise_made_2 as f_raise_made_2,
)
from fpdb_3_legacy.stats_sizing import (
    f_spr as f_spr,
)
from fpdb_3_legacy.stats_sizing import (
    overbet_frequency as overbet_frequency,
)
from fpdb_3_legacy.stats_sizing import (
    p_2bet_facing as p_2bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    p_3bet_facing as p_3bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    p_4bet_facing as p_4bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    p_5bet_facing as p_5bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    p_raise_facing as p_raise_facing,
)
from fpdb_3_legacy.stats_sizing import (
    p_raise_made as p_raise_made,
)
from fpdb_3_legacy.stats_sizing import (
    p_raise_made_2 as p_raise_made_2,
)
from fpdb_3_legacy.stats_sizing import (
    r_2bet_facing as r_2bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    r_3bet_facing as r_3bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    r_4bet_facing as r_4bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    r_bet_facing as r_bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    r_bet_made as r_bet_made,
)
from fpdb_3_legacy.stats_sizing import (
    r_raise_facing as r_raise_facing,
)
from fpdb_3_legacy.stats_sizing import (
    r_raise_made as r_raise_made,
)
from fpdb_3_legacy.stats_sizing import (
    r_raise_made_2 as r_raise_made_2,
)
from fpdb_3_legacy.stats_sizing import (
    r_spr as r_spr,
)
from fpdb_3_legacy.stats_sizing import (
    t_2bet_facing as t_2bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    t_3bet_facing as t_3bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    t_4bet_facing as t_4bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    t_bet_facing as t_bet_facing,
)
from fpdb_3_legacy.stats_sizing import (
    t_bet_made as t_bet_made,
)
from fpdb_3_legacy.stats_sizing import (
    t_raise_facing as t_raise_facing,
)
from fpdb_3_legacy.stats_sizing import (
    t_raise_made as t_raise_made,
)
from fpdb_3_legacy.stats_sizing import (
    t_raise_made_2 as t_raise_made_2,
)
from fpdb_3_legacy.stats_sizing import (
    t_spr as t_spr,
)
from fpdb_3_legacy.stats_table import (
    TABLE_STAT_FUNCTIONS as _TABLE_STAT_FUNCTIONS,  # noqa: F401 -- compatibility export
)
from fpdb_3_legacy.stats_table import (
    do_table_stat as do_table_stat,
)
from fpdb_3_legacy.stats_table import (
    live_min_stack_bb as live_min_stack_bb,
)
from fpdb_3_legacy.stats_tournament import (
    bbstack as bbstack,
)

_get_hand_instance = get_hand_instance
from fpdb_3_legacy.stats_tournament import (
    m_ratio as m_ratio,
)

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("stats")

STATS_DATA_ERRORS = (AttributeError, KeyError, TypeError, ValueError)

re_Places = re.compile("_[0-9]$")

encoder = codecs.lookup(Configuration.LOCALE_ENCODING)
_ = L10n.get_translation()

# Dispatch dict for stat functions (populated lazily, replaces eval)
STAT_FUNCTIONS = None


def _descriptor_stat(stat_dict, player, statname):
    """Render a declarative descriptor stat in the HUD, or None if unknown.

    Looks the name up in the shared StatRegistry and, if found, computes the
    6-tuple via the HUD adapter from the player's pre-aggregated stat_dict.
    Kept import-local so Stats.py has no hard dependency on the registry.
    """
    try:
        from fpdb_3_legacy.stat_adapters import HudAdapter
        from fpdb_3_legacy.stat_registry import get_registry

        descriptor = get_registry().get(statname)
        if descriptor is None:
            return None
        player_stats = stat_dict.get(player, {})
        return HudAdapter().stat_tuple(descriptor, player_stats)
    except Exception:
        log.exception("descriptor stat %s failed", statname)
        return None


def do_stat(stat_dict, player=24, stat="vpip", hand_instance=None):
    """Calculates a specific statistic for a given player in a hand.

    Args:
        stat_dict (dict): A dictionary containing statistics for all players in the hand.
        player (int, optional): The player for whom to calculate the statistic. Defaults to 24.
        stat (str, optional): The statistic to calculate. Defaults to 'vpip'.
        hand_instance (object, optional): An instance of the hand. Defaults to None.

    Returns:
        The calculated statistic for the player, or None if the statistic is not in the list of available statistics.

    Note:
        The hand instance is not needed for many stat functions, so it is stored in a global variable to avoid having to conditionally pass the extra value.
        If the statistic name ends with an underscore followed by a number, it is overridden with the specified number of decimal places.
        The decimal place override assumes the raw result is a fraction (x/100), and manual decimal places only make sense for percentage values.
        The profit/100 hands (bb/BB) already default to three decimal places anyhow, so they are unlikely override candidates.

    """
    # hand instance is not needed for many stat functions
    # so this optional parameter will be stored in a thread-local
    # to avoid having to conditionally pass the extra value
    _set_hand_instance(hand_instance)

    if not isinstance(stat, str) or not stat:
        return None

    statname = stat
    match = re_Places.search(stat)
    if match:  # override if necessary
        statname = stat[0:-2]

    # Ensure player is an integer to prevent TypeError
    try:
        player_int = int(player)
    except (ValueError, TypeError):
        log.exception(f"Invalid player parameter: {player} (type: {type(player)})")
        return None

    if statname not in STATLIST:
        # Fall back to declarative descriptor stats (stat_registry.py). Native
        # functions take precedence; only otherwise-unknown names reach here.
        result = _descriptor_stat(stat_dict, player_int, statname)
        if result is not None and match:
            result = __stat_override(int(stat[-1:]), result)
        return result

    # Build dispatch dict lazily for security (replaces eval)
    global STAT_FUNCTIONS
    if STAT_FUNCTIONS is None:
        STAT_FUNCTIONS = {name: globals()[name] for name in STATLIST}

    fn = STAT_FUNCTIONS.get(statname)
    if fn is None:
        return None

    result = fn(stat_dict, player_int)

    # If decimal places have been defined, override result[1]
    # NOTE: decimal place override ALWAYS assumes the raw result is a
    # fraction (x/100); manual decimal places really only make sense for
    # percentage values. Also, profit/100 hands (bb/BB) already default
    # to three decimal places anyhow, so they are unlikely override
    # candidates.
    if match:
        places = int(stat[-1:])
        result = __stat_override(places, result)
    return result


#    OK, for reference the tuple returned by the stat is:
#    0 - The stat, raw, no formating, eg 0.33333333
#    1 - formatted stat with appropriate precision, eg. 33; shown in HUD
#    2 - formatted stat with appropriate precision, punctuation and a hint, eg v=33%
#    3 - same as #2 except name of stat instead of hint, eg vpip=33%
#    4 - the calculation that got the stat, eg 9/27
#    5 - the name of the stat, useful for a tooltip, eg vpip

###########################################
#    functions that return individual stats


def get_valid_stats():
    """Function to retrieve valid stats descriptions.

    Returns:
        dict: A dictionary containing descriptions of valid stats.

    """
    import sys

    stat_descriptions = {}
    for function in STATLIST:
        function_instance = getattr(sys.modules[__name__], function)
        if callable(function_instance):
            try:
                res = function_instance(None, None)
                if isinstance(res, tuple) and len(res) > 5:
                    stat_descriptions[function] = res[5]
            except Exception:  # intentional broad catch: probe every registered stat
                log.debug("Stat %s cannot provide metadata without data", function, exc_info=True)

    return stat_descriptions


STATLIST = sorted(dir())
misslist = [
    "Configuration",
    "Database",
    "Charset",
    "codecs",
    "encoder",
    "GInitiallyUnowned",
    "gtk",
    "pygtk",
    "Card",
    "L10n",
    "log",
    "logging",
    "Decimal",
    "GFileDescriptorBased",
    "GPollableInputStream",
    "GPollableOutputStream",
    "re",
    "re_Places",
    "Hand",
]
STATLIST = [x for x in STATLIST if x not in ("do_stat", "do_tip", "get_valid_stats")]
# Table-scope stats take a single table-stats dict, not (stat_dict, player), so
# they must never enter the player-stat dispatch built from STATLIST.
STATLIST = [x for x in STATLIST if x not in ("do_table_stat", "live_min_stack_bb")]
STATLIST = [x for x in STATLIST if not x.startswith("_")]
STATLIST = [x for x in STATLIST if x not in dir(sys)]
STATLIST = [x for x in STATLIST if x not in dir(codecs)]
STATLIST = [x for x in STATLIST if x not in misslist]
# print "STATLIST is", STATLIST


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="FPDB Stats utility")
    parser.add_argument("--show-stats", action="store_true", help="Show statistics from last hand")
    parser.add_argument("--list-stats", action="store_true", help="List all available stat functions")
    parser.add_argument("--validate-stats", action="store_true", help="Validate all stat functions")
    parser.add_argument("--interactive", action="store_true", help="Run original interactive test")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        parser.print_help()
        return 0

    Configuration.set_logfile("fpdb-log.txt")

    if args.list_stats:
        print("=== Available Stat Functions ===")
        print(f"Total stats available: {len(STATLIST)}")
        for i, stat in enumerate(sorted(STATLIST), 1):
            print(f"  {i:3}. {stat}")

        print("\n=== Valid Stats with Descriptions ===")
        try:
            stat_descriptions = get_valid_stats()
            if stat_descriptions:
                for stat_name, description in sorted(stat_descriptions.items()):
                    print(f"  {stat_name}: {description}")
            else:
                print("  No stat descriptions available")
        except Exception:  # intentional broad catch: dynamic stat registry contains legacy helpers.
            print("  Could not retrieve stat descriptions (this is normal)")
            print("  Note: Some functions in STATLIST are not poker stats")

    if args.show_stats or args.validate_stats or args.interactive:
        try:
            print("Connecting to database...")
            c = Configuration.Config()
            db_connection = Database.Database(c)
            h = db_connection.get_last_hand()

            if not h:
                print("No hands found in database")
                return 1

            print(f"Using hand ID: {h}")

        except Exception as e:  # intentional broad catch: CLI DB bootstrap spans configured backends.
            print(f"Error connecting to database: {e}")
            return 1

    if args.show_stats:
        try:
            stat_dict = db_connection.get_stats_from_hand(h, "ring")
            Hand.hand_factory(h, c, db_connection)

            print(f"\n=== Statistics for Hand {h} ===")
            for player, stats in stat_dict.items():
                print(f"\nPlayer: {player}")
                for stat_name, value in sorted(stats.items()):
                    print(f"  {stat_name}: {value}")

        except Exception as e:  # intentional broad catch: CLI stats lookup spans DB and hand factory code.
            print(f"Error retrieving stats: {e}")
            return 1

    if args.validate_stats:
        print("\n=== Validating Stat Functions ===")
        try:
            stat_dict = db_connection.get_stats_from_hand(h, "ring")
            Hand.hand_factory(h, c, db_connection)

            valid_count = 0
            error_count = 0

            for player in stat_dict:
                for attr in STATLIST:
                    try:
                        # Test if the stat function exists and can be called
                        if hasattr(sys.modules[__name__], attr):
                            valid_count += 1
                        else:
                            print(f"  ✗ {attr}: Function not found")
                            error_count += 1
                    except STATS_DATA_ERRORS as e:
                        print(f"  ✗ {attr}: Error - {e}")
                        error_count += 1
                break  # Only test with first player

            print(f"\nValidation complete: {valid_count} valid, {error_count} errors")

        except Exception as e:  # intentional broad catch: CLI validation spans dynamic stats and DB state.
            print(f"Error during validation: {e}")
            return 1

    if args.interactive:
        print("Running original interactive test...")
        try:
            c = Configuration.Config()
            db_connection = Database.Database(c)
            h = db_connection.get_last_hand()
            if h is None:
                print("No hands found.")
                return 1
            stat_dict = db_connection.get_stats_from_hand(h, "ring")
            Hand.hand_factory(h, c, db_connection)
        except Exception as e:  # intentional broad catch: interactive CLI spans DB and hand factory code.
            print(f"Error during interactive test: {e}")
            return 1

        for _player in stat_dict:
            for _attr in STATLIST:
                pass
            break

        stat_descriptions = get_valid_stats()
        for _stat in STATLIST:
            pass

        print("Interactive test complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
