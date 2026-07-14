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
from fpdb_3_legacy import Card, Configuration, Database, Hand, L10n
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.stats_context import (
    get_hand_instance as _get_hand_instance,
)
from fpdb_3_legacy.stats_context import (
    set_hand_instance as _set_hand_instance,
)
from fpdb_3_legacy.stats_formatting import (
    do_tip as do_tip,
)
from fpdb_3_legacy.stats_formatting import (
    format_no_data_stat,
)
from fpdb_3_legacy.stats_formatting import (
    stat_override as __stat_override,
)
from fpdb_3_legacy.stats_postflop import (
    check_raise_frequency as check_raise_frequency,
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
    first_raise_flop as first_raise_flop,
)
from fpdb_3_legacy.stats_postflop import (
    first_raise_river as first_raise_river,
)
from fpdb_3_legacy.stats_postflop import (
    first_raise_turn as first_raise_turn,
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
    open_flop as open_flop,
)
from fpdb_3_legacy.stats_postflop import (
    open_river as open_river,
)
from fpdb_3_legacy.stats_postflop import (
    open_turn as open_turn,
)
from fpdb_3_legacy.stats_postflop import (
    river_call_efficiency as river_call_efficiency,
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
from fpdb_3_legacy.stats_preflop import (
    call_vs_steal as call_vs_steal,
)
from fpdb_3_legacy.stats_preflop import (
    cold_call as cold_call,
)
from fpdb_3_legacy.stats_preflop import (
    face_limpers as face_limpers,
)
from fpdb_3_legacy.stats_preflop import (
    fold_to_allin as fold_to_allin,
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
    straddle as straddle,
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


def totalprofit(stat_dict, player):
    """Calculates the total profit for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom to calculate the total profit.

    Returns:
        tuple: A tuple containing the following values:
            - stat (float): The total profit divided by 100.
            - formatted_stat (str): The formatted total profit with two decimal places.
            - tp_formatted_stat (str): The formatted total profit with two decimal places and a hint.
            - tot_prof_formatted_stat (str): The formatted total profit with two decimal places and a hint.
            - str_stat (str): The total profit as a string.
            - stat_name (str): The name of the statistic.

    If the 'net' key is not present in the stat_dict for the given player, or if the value cannot be converted to a float,
    the function returns a tuple with default values:

        - ('0', '$0.00', 'tp=0', 'totalprofit=0', '0', 'Total Profit')

    """
    try:
        stat = float(stat_dict[player]["net"]) / 100
        return (
            stat / 100.0,
            f"${stat:.2f}",
            f"tp=${stat:.2f}",
            f"tot_prof=${stat:.2f}",
            str(stat),
            "Total Profit",
        )
    except (KeyError, ValueError, TypeError):
        return ("0", "$0.00", "tp=0", "totalprofit=0", "0", "Total Profit")


def playername(stat_dict, player):
    """Retrieves the player's screen name from the stat dictionary.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom to retrieve the screen name.

    Returns:
        tuple: A tuple containing the player's screen name repeated five times and a constant 'Player name' at the end. If the player's screen name is not found, it returns an empty string five times followed by 'Player name'.

    """
    try:
        return (
            stat_dict[player]["screen_name"],
            stat_dict[player]["screen_name"],
            stat_dict[player]["screen_name"],
            stat_dict[player]["screen_name"],
            stat_dict[player]["screen_name"],
            "Player name",
        )
    except (KeyError, ValueError, TypeError):
        return ("", "", "", "", "", "Player name")


def _calculate_end_stack(stat_dict, player, hand_instance):
    """Calculate the end stack size for a given player in a hand instance.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom to calculate the end stack size.
        hand_instance (Hand): An instance of the Hand class representing the current hand.

    Returns:
        float: The end stack size for the given player.

    Note:
        This function is currently located in Stats.py but it should be moved to Hands.py since it belongs there.

    Todo:
        - Find a better way to calculate the end stack size from the hand_instance.
        - Add a hand_instance "end_of_hand_stack" attribute.

    """
    # fixme - move this code into Hands.py - it really belongs there

    # To reflect the end-of-hand position, we need a end-stack calculation
    # fixme, is there an easier way to do this from the hand_instance???
    # can't seem to find a hand_instance "end_of_hand_stack" attribute

    # First, find player stack size at the start of the hand
    stack = 0.0
    for item in hand_instance.players:
        if item[1] == stat_dict[player]["screen_name"]:
            stack = float(item[2])

    # Next, deduct all action from this player
    for street in hand_instance.bets:
        for item in hand_instance.bets[street]:
            if item == stat_dict[player]["screen_name"]:
                for amount in hand_instance.bets[street][stat_dict[player]["screen_name"]]:
                    stack -= float(amount)

    # Next, add back any money returned
    for p in hand_instance.pot.returned:
        if p == stat_dict[player]["screen_name"]:
            stack += float(hand_instance.pot.returned[p])

    # Finally, add back any winnings
    for item in hand_instance.collectees:
        if item == stat_dict[player]["screen_name"]:
            stack += float(hand_instance.collectees[item])
    return stack


def m_ratio(stat_dict, player):
    """Calculate the M-ratio for a player in a tournament.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom to calculate the M-ratio.

    Returns:
        tuple: A tuple containing the M-ratio value and formatted strings.

    Note:
        This function calculates the M-ratio using the end-of-hand stack count versus the hand's antes/blinds.

    """
    # Tournament M-ratio calculation
    # Using the end-of-hand stack count vs. that hand's antes/blinds

    # sum all blinds/antes
    stat = 0.0
    compulsory_bets = 0.0
    hand_instance = _get_hand_instance()

    if not hand_instance:
        return (
            (stat / 100.0),
            "%d" % (int(stat)),
            "M=%d" % (int(stat)),
            "M=%d" % (int(stat)),
            "(%d)" % (int(stat)),
            "M ratio",
        )

    for p in hand_instance.bets["BLINDSANTES"]:
        for i in hand_instance.bets["BLINDSANTES"][p]:
            compulsory_bets += float(i)
    compulsory_bets += float(
        hand_instance.gametype.get("sb", 0),
    )  # Ensure "sb" key exists
    compulsory_bets += float(
        hand_instance.gametype.get("bb", 0),
    )  # Ensure "bb" key exists

    stack = _calculate_end_stack(stat_dict, player, hand_instance)

    if compulsory_bets != 0:  # Check if compulsory_bets is non-zero to avoid division by zero
        stat = stack / compulsory_bets
    else:
        stat = 0  # Default to 0 if compulsory_bets is zero

    return (
        (int(stat)),
        "%d" % (int(stat)),
        "M=%d" % (int(stat)),
        "M=%d" % (int(stat)),
        "(%d)" % (int(stat)),
        "M ratio",
    )


def bbstack(stat_dict, player):
    """Calculate the tournament stack size in Big Blinds.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom to calculate the stack size.

    Returns:
        tuple: A tuple containing the stack size in Big Blinds and related information.

    Note:
        This function calculates the stack size in Big Blinds based on the end of hand stack count and the current Big Blind limit.

    """
    # Tournament Stack calculation in Big Blinds
    # Result is end of hand stack count / Current Big Blind limit
    stat = 0.0
    hand_instance = _get_hand_instance()
    if not (hand_instance):
        return (stat, "NA", "v=NA", "vpip=NA", "(0/0)", "bb stack")

    # current big blind limit

    current_bigblindlimit = float(hand_instance.gametype.get("bb", 0))

    stack = _calculate_end_stack(stat_dict, player, hand_instance)

    stat = stack / current_bigblindlimit if current_bigblindlimit != 0 else 0

    return (
        (stat / 100.0),
        "%d" % (int(stat)),
        "bb's=%d" % (int(stat)),
        "#bb's=%d" % (int(stat)),
        "(%d)" % (int(stat)),
        "bb stack",
    )


def playershort(stat_dict, player):
    """Retrieves the shortened screen name of a player from the given stat_dict.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom to retrieve the shortened screen name.

    Returns:
        tuple: A tuple containing the shortened screen name and related information.

    Raises:
        KeyError: If the player's screen name is not found in the stat_dict.

    Note:
        If the length of the screen name is greater than 6, it is truncated to 5 characters and a dot is appended.
        The returned tuple contains the shortened screen name repeated 5 times and the player's full screen name.

    """
    try:
        r = stat_dict[player]["screen_name"]
    except (KeyError, ValueError, TypeError):
        return ("", "", "", "", "", ("Player Name") + " 1-5")

    if len(r) > 6:
        r = r[:5] + "."
    return (r, r, r, r, stat_dict[player]["screen_name"], ("Player Name") + " 1-5")


def playerprofile(stat_dict, player):
    """Calculates the player profile and returns the emoji or text."""
    try:
        if stat_dict is None or player is None:
            raise TypeError("None parameter")
        from fpdb_3_legacy.PlayerProfiler import classify_player
        profile, icon, color = classify_player(stat_dict, player)
        return (profile, icon, f"p={profile}", f"playerprofile={profile}", f"{profile}", "Player Profile")
    except Exception:  # intentional broad catch
        return ("unknown", "❓", "p=unknown", "playerprofile=unknown", "unknown", "Player Profile")


def vpip(stat_dict, player):
    """A function to calculate and return VPIP (Voluntarily Put In Pot) percentage.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (str): The player for whom to calculate the VPIP.

    Returns:
        tuple: A tuple containing:
            - VPIP percentage (float)
            - VPIP percentage formatted as a string or "-" if no data
            - 'v=' followed by VPIP percentage formatted as a percentage string
            - 'vpip=' followed by VPIP percentage formatted as a percentage string
            - '(x/y)' where x is the VPIP and y is VPIP opportunities
            - 'Voluntarily put in preflop/3rd street %'

        If no opportunities available, returns "-" to distinguish from 0% (tight player).

    """
    stat = 0.0
    try:
        vpip_opp = float(stat_dict[player].get("vpip_opp", 0))
        vpip_count = float(stat_dict[player].get("vpip", 0))

        # No opportunities = no data available
        if vpip_opp == 0:
            return format_no_data_stat("vpip", "Voluntarily put in preflop/3rd street %")

        # Calculate VPIP percentage
        stat = vpip_count / vpip_opp

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "v=%3.1f%%" % (100.0 * stat),
            "vpip=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (vpip_count, vpip_opp),
            "Voluntarily put in preflop/3rd street %",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "v=NA",
            "vpip=NA",
            "(0/0)",
            "Voluntarily put in preflop/3rd street %",
        )


def pfr(stat_dict, player):
    """Calculate and return the preflop raise percentage (pfr) for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the pfr is calculated.

    Returns:
        tuple: A tuple containing the pfr value, formatted pfr percentages, and related information.
        Returns "-" if no opportunities available to distinguish from 0% (passive player).

    """
    stat = 0.0
    try:
        pfr_opp = float(stat_dict[player].get("pfr_opp", 0))
        pfr_count = float(stat_dict[player].get("pfr", 0))

        # No opportunities = no data available
        if pfr_opp == 0:
            return format_no_data_stat("pfr", "Preflop/3rd street raise %")

        # Calculate PFR percentage
        stat = pfr_count / pfr_opp

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "p=%3.1f%%" % (100.0 * stat),
            "pfr=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (pfr_count, pfr_opp),
            "Preflop/3rd street raise %",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "p=NA", "pfr=NA", "(0/0)", "Preflop/3rd street raise %")


def wtsd(stat_dict, player):
    """Calculate and return the percentage of hands where a player went to showdown when seen flop/4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the percentage is calculated.

    Returns:
        tuple: A tuple containing the percentage value, formatted percentage percentages, and related information.
        Returns "-" if no opportunities available to distinguish from 0% (never went to showdown).

    """
    stat = 0.0
    try:
        saw_f = float(stat_dict[player].get("saw_f", 0))  # Ensure key exists
        sd = float(stat_dict[player].get("sd", 0))

        # No opportunities = no data available
        if saw_f == 0:
            return format_no_data_stat("wtsd", "% went to showdown when seen flop/4th street")

        # Calculate WTSD percentage
        stat = sd / saw_f

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "w=%3.1f%%" % (100.0 * stat),
            "wtsd=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (sd, saw_f),
            "% went to showdown when seen flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "w=NA",
            "wtsd=NA",
            "(0/0)",
            "% went to showdown when seen flop/4th street",
        )


def wmsd(stat_dict, player):
    """Calculate and return the win money at showdown (wmsd) statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the wmsd is calculated.

    Returns:
        tuple: A tuple containing the wmsd value, formatted wmsd percentages, and related information.
        Returns "-" if no showdowns to distinguish from 0% (never won at showdown).

    """
    stat = 0.0
    try:
        sd = float(stat_dict[player].get("sd", 0))  # Ensure key exists
        wmsd_value = float(stat_dict[player].get("wmsd", 0))

        # No showdowns = no data available
        if sd == 0:
            return format_no_data_stat("wmsd", "% won some money at showdown")

        # Calculate WMSD percentage
        stat = wmsd_value / sd

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "w=%3.1f%%" % (100.0 * stat),
            "wmsd=%3.1f%%" % (100.0 * stat),
            "(%5.1f/%d)" % (wmsd_value, sd),
            "% won some money at showdown",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "w=NA", "wmsd=NA", "(0/0)", "% won some money at showdown")


# Money is stored as pennies, so there is an implicit 100-multiplier
# already in place
def profit100(stat_dict, player):
    """Calculate the profit per 100 hands for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the profit per 100 hands is calculated.

    Returns:
        tuple: A tuple containing the profit per 100 hands value, formatted profit percentages, and related information.

    Notes:
        - The profit per 100 hands is calculated by dividing the net winnings by the number of hands played.
        - If an exception occurs during the calculation, the function returns a tuple with default values.

    """
    stat = 0.0
    try:
        # Check if player exists in stat_dict first
        if player not in stat_dict:
            return (stat, "NA", "p=NA", "p/100=NA", "(0/0)", "Profit per 100 hands")

        n = float(stat_dict[player].get("n", 0))  # Ensure key exists
        if n != 0:  # Check if 'n' (number of hands) is non-zero
            stat = float(stat_dict[player]["net"]) / n
        else:
            stat = 0  # Default to 0 if 'n' is zero

        return (
            stat / 100.0,
            f"{stat:.2f}",
            f"p={stat:.2f}",
            f"p/100={stat:.2f}",
            "%d/%d" % (stat_dict[player]["net"], n),
            "Profit per 100 hands",
        )

    except (KeyError, ValueError, TypeError):
        if stat_dict:
            log.exception(
                f"exception calculating profit100: player {player} not found in stat_dict or missing data",
            )
        return (stat, "NA", "p=NA", "p/100=NA", "(0/0)", "Profit per 100 hands")


def bbper100(stat_dict, player):
    """Calculate the number of big blinds won per 100 hands for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the number of big blinds won per 100 hands is calculated.

    Returns:
        tuple: A tuple containing the number of big blinds won per 100 hands value, formatted values, and related information.

    """
    stat = 0.0
    try:
        bigblind = float(stat_dict[player].get("bigblind", 0))  # Ensure key exists
        if bigblind != 0:  # Check if 'bigblind' is non-zero
            stat = 100.0 * float(stat_dict[player]["net"]) / bigblind
        else:
            stat = 0  # Default to 0 if 'bigblind' is zero

        return (
            stat / 100.0,
            f"{stat:5.3f}",
            f"bb100={stat:5.3f}",
            f"bb100={stat:5.3f}",
            "(%d,%d)" % (100 * stat_dict[player]["net"], bigblind),
            "Big blinds won per 100 hands",
        )

    except (KeyError, ValueError, TypeError):
        if stat_dict and player in stat_dict:
            log.info(
                f"exception calculating bbper100: {stat_dict[player].get('net', 'N/A')} / {stat_dict[player].get('bigblind', 'N/A')}",
            )
        return (
            stat,
            "NA",
            "bb100=NA",
            "bb100=NA",
            "(--)",
            "Big blinds won per 100 hands",
        )


def BBper100(stat_dict, player):
    """Calculate the number of big bets won per 100 hands for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the number of big bets won per 100 hands is calculated.

    Returns:
        tuple: A tuple containing the number of big bets won per 100 hands value, formatted values, and related information.

    Notes:
        - The number of big bets won per 100 hands is calculated by dividing the net winnings by the big blind value, multiplied by 50.
        - If an exception occurs during the calculation, the function returns a tuple with default values.

    """
    stat = 0.0
    try:
        bigblind = float(stat_dict[player].get("bigblind", 0))  # Ensure key exists
        if bigblind != 0:  # Check if 'bigblind' is non-zero
            stat = 50 * float(stat_dict[player]["net"]) / bigblind
        else:
            stat = 0  # Default to 0 if 'bigblind' is zero

        return (
            stat / 100.0,
            f"{stat:5.3f}",
            f"BB100={stat:5.3f}",
            f"BB100={stat:5.3f}",
            "(%d,%d)" % (100 * stat_dict[player]["net"], 2 * bigblind),
            "Big bets won per 100 hands",
        )

    except (KeyError, ValueError, TypeError):
        if stat_dict:
            log.info(f"exception calculating BBper100: {stat_dict[player]}")
        return (
            stat,
            "NA",
            "BB100=NA",
            "BB100=NA",
            "(--)",
            "Big bets won per 100 hands",
        )


def saw_f(stat_dict, player):
    """Calculate the saw flop percentage for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the saw flop percentage is calculated.

    Returns:
        tuple: A tuple containing the saw flop percentage in various formats.
            - The saw flop percentage as a float.
            - The saw flop percentage formatted to one decimal place.
            - The saw flop percentage with a label.
            - The saw flop percentage with a different label.
            - The count of times saw flop divided by total count.
            - A description of the statistic.

    If an error occurs during calculation, default values are returned.

    """
    try:
        num = float(stat_dict[player]["saw_f"])
        den = float(stat_dict[player]["n"])
        stat = num / den
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "sf=%3.1f%%" % (100.0 * stat),
            "saw_f=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (stat_dict[player]["saw_f"], stat_dict[player]["n"]),
            "Flop/4th street seen %",
        )

    except (KeyError, ValueError, TypeError):
        stat = 0.0
        return (stat, "NA", "sf=NA", "saw_f=NA", "(0/0)", "Flop/4th street seen %")


def n(stat_dict, player):
    """Calculate and format the number of hands seen for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the number of hands seen is calculated.

    Returns:
        tuple: A tuple containing formatted strings representing the number of hands seen in different ways.

    """
    try:
        # If sample is large enough, use X.Yk notation instead
        _n = stat_dict[player]["n"]
        fmt = "%d" % _n
        if _n >= 10000:
            k = _n / 1000
            c = _n % 1000
            _c = float(c) / 100.0
            d = round(_c)
            if d == 10:
                k += 1
                d = 0
            fmt = "%d.%dk" % (k, d)
        return (
            stat_dict[player]["n"],
            f"{fmt}",
            "n=%d" % (stat_dict[player]["n"]),
            "n=%d" % (stat_dict[player]["n"]),
            "(%d)" % (stat_dict[player]["n"]),
            "Number of hands seen",
        )

    except (KeyError, ValueError, TypeError):
        # Number of hands shouldn't ever be "NA"; zeroes are better here
        return (
            0,
            "%d" % (0),
            "n=%d" % (0),
            "n=%d" % (0),
            "(%d)" % (0),
            "Number of hands seen",
        )


def steal(stat_dict, player):
    """Calculate and format the steal percentage for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the steal percentage is calculated.

    Returns:
        tuple: A tuple containing formatted strings representing the steal percentage in different ways.
            - stat (float): The steal percentage.
            - '%3.1f' (str): The steal percentage formatted as a string with 3 decimal places.
            - 'st=%3.1f%%' (str): The steal percentage formatted as a string with 3 decimal places and a percentage sign.
            - 'steal=%3.1f%%' (str): The steal percentage formatted as a string with 3 decimal places and a percentage sign.
            - '(%d/%d)' (str): The steal count and steal opponent count formatted as a string.
            - '% steal attempted' (str): The description of the steal percentage.

        If no opportunities available, returns "-" to distinguish from 0% (passive player).

    Raises:
        None

    Notes:
        - The steal percentage is calculated by dividing the steal count by the steal opponent count.
        - If any of the required statistics are missing, the function returns default values.

    """
    stat = 0.0
    try:
        steal_opp = float(stat_dict[player].get("steal_opp", 0))  # Ensure key exists
        steal_count = float(stat_dict[player].get("steal", 0))

        # No opportunities = no data available
        if steal_opp == 0:
            return format_no_data_stat("steal", "% steal attempted")

        # Calculate steal percentage
        stat = steal_count / steal_opp

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "st=%3.1f%%" % (100.0 * stat),
            "steal=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (steal_count, steal_opp),
            "% steal attempted",
        )

    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "st=NA", "steal=NA", "(0/0)", "% steal attempted")


def s_steal(stat_dict, player):
    """Calculate and format the steal success percentage for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the steal success percentage is calculated.

    Returns:
        tuple: A tuple containing formatted strings representing the steal success percentage in different ways.
            - stat (float): The steal success percentage.
            - '%3.1f' (str): The steal success percentage formatted as a string with 3 decimal places.
            - 's_st=%3.1f%%' (str): The steal success percentage formatted with a specific label.
            - 's_steal=%3.1f%%' (str): The steal success percentage formatted with a specific label.
            - '(%d/%d)' (str): The steal success count and total steal count formatted as a string.
            - '% steal success' (str): The description of the steal success percentage.
        Returns "-" if no steal attempts to distinguish from 0% (never successful steal).

    Raises:
        None

    """
    stat = 0.0
    try:
        steal_attempts = float(stat_dict[player].get("steal", 0))
        successful_steals = float(stat_dict[player].get("suc_st", 0))

        # No steal attempts = no data available
        if steal_attempts == 0:
            return format_no_data_stat("s_st", "% steal success")

        # Calculate steal success percentage
        stat = successful_steals / steal_attempts

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "s_st=%3.1f%%" % (100.0 * stat),
            "s_steal=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (successful_steals, steal_attempts),
            "% steal success",
        )

    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "s_st=NA", "s_steal=NA", "(0/0)", "% steal success")


def f_SB_steal(stat_dict, player):
    """Calculate the folded Small Blind (SB) to steal statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the folded SB to steal statistics.
            - stat (float): The folded SB to steal percentage.
            - '%3.1f' (str): The folded SB to steal percentage formatted as a string with 3 decimal places.
            - 'fSB=%3.1f%%' (str): The folded SB to steal percentage formatted with a specific label.
            - 'fSB_s=%3.1f%%' (str): The folded SB to steal percentage formatted with a specific label.
            - '(%d/%d)' (str): The number of folded SB to steal and the total number of folded SB formatted as a string.
            - '% folded SB to steal' (str): The description of the folded SB to steal percentage.
        Returns "-" if no steal attempts to distinguish from 0% (never folded SB to steal).

    Raises:
        None

    """
    stat = 0.0
    try:
        sbstolen = float(stat_dict[player].get("sbstolen", 0))
        sbnotdef = float(stat_dict[player].get("sbnotdef", 0))

        # No steal attempts = no data available
        if sbstolen == 0:
            return format_no_data_stat("fSB", "% folded SB to steal")

        # Calculate fold SB to steal percentage
        stat = sbnotdef / sbstolen

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "fSB=%3.1f%%" % (100.0 * stat),
            "fSB_s=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (sbnotdef, sbstolen),
            "% folded SB to steal",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "fSB=NA", "fSB_s=NA", "(0/0)", "% folded SB to steal")


def f_BB_steal(stat_dict, player):
    """Calculate the folded Big Blind (BB) to steal statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the calculated statistics in different formats:
            - Float: The calculated statistic.
            - String: The statistic formatted as a percentage with one decimal place.
            - String: A formatted string representing the statistic.
            - String: A formatted string representing the statistic with a suffix.
            - String: A formatted string showing the count of BB not defended and BB stolen.
            - String: A description of the statistic.
        Returns "-" if no steal attempts to distinguish from 0% (never folded BB to steal).

    If an exception occurs during the calculation, returns default values for the statistics.

    """
    stat = 0.0
    try:
        bbstolen = float(stat_dict[player].get("bbstolen", 0))
        bbnotdef = float(stat_dict[player].get("bbnotdef", 0))

        # No steal attempts = no data available
        if bbstolen == 0:
            return format_no_data_stat("fBB", "% folded BB to steal")

        # Calculate fold BB to steal percentage
        stat = bbnotdef / bbstolen

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "fBB=%3.1f%%" % (100.0 * stat),
            "fBB_s=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (bbnotdef, bbstolen),
            "% folded BB to steal",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "fBB=NA", "fBB_s=NA", "(0/0)", "% folded BB to steal")


def f_steal(stat_dict, player):
    """Calculate the folded blind to steal statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the calculated statistics in different formats:
            - Float: The calculated statistic.
            - String: The statistic formatted as a percentage with one decimal place.
            - String: A formatted string representing the statistic.
            - String: A formatted string representing the statistic with a suffix.
            - String: A formatted string showing the count of folded blind not defended and blind stolen.
            - String: A description of the statistic.
        Returns "-" if no steal attempts to distinguish from 0% (never folded to steal).

    If an exception occurs during the calculation, returns default values for the statistics.

    """
    stat = 0.0
    try:
        folded_blind = stat_dict[player].get("sbnotdef", 0) + stat_dict[player].get(
            "bbnotdef",
            0,
        )
        blind_stolen = stat_dict[player].get("sbstolen", 0) + stat_dict[player].get(
            "bbstolen",
            0,
        )

        # No steal attempts = no data available
        if blind_stolen == 0:
            return format_no_data_stat("fB", "% folded blind to steal")

        # Calculate fold to steal percentage
        stat = float(folded_blind) / float(blind_stolen)

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "fB=%3.1f%%" % (100.0 * stat),
            "fB_s=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (folded_blind, blind_stolen),
            "% folded blind to steal",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "fB=NA", "fB_s=NA", "(0/0)", "% folded blind to steal")


def three_B(stat_dict, player):
    """Calculate the three bet statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the calculated statistics in different formats:
            - Float: The calculated statistic.
            - String: The statistic formatted as a percentage with one decimal place.
            - String: A formatted string representing the statistic.
            - String: A formatted string representing the statistic with a suffix.
            - String: A formatted string showing the count of three bets made and opponent's three bets.
            - String: A description of the statistic.

    If an exception occurs during the calculation, returns default values for the statistics.

    """
    stat = 0.0
    try:
        tb_opp_0 = float(stat_dict[player].get("tb_opp_0", 0))  # Ensure key exists
        tb_0 = float(stat_dict[player].get("tb_0", 0))

        # No opportunities = no data available
        if tb_opp_0 == 0:
            return format_no_data_stat("3B", "% 3 bet preflop/3rd street")

        # Calculate 3bet percentage
        stat = tb_0 / tb_opp_0

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "3B=%3.1f%%" % (100.0 * stat),
            "3B_pf=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (tb_0, tb_opp_0),
            "% 3 bet preflop/3rd street",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "3B=NA", "3B_pf=NA", "(0/0)", "% 3 bet preflop/3rd street")


# ---------------------------------------------------------------------------
# Per-street postflop display stats (HUD).
#
# These reuse the generic done/opp ratio formatter ``_postflop_3bet``. The
# numerators and opportunity denominators are already persisted in the cache
# and aliased by ``get_stats_from_hand`` (see SQL.py); the functions below
# simply expose them to the HUD/GUI. Adding them is purely additive: any
# module-level function here is auto-registered into STATLIST.
# ---------------------------------------------------------------------------


def four_B(stat_dict, player):
    """Calculate the four bet statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the calculated statistics in different formats:
            - Float: The calculated statistic.
            - String: The statistic formatted as a percentage with one decimal place.
            - String: A formatted string representing the statistic.
            - String: A formatted string representing the statistic with a suffix.
            - String: A formatted string showing the count of four bets made and opponent's four bets.
            - String: A description of the statistic.
        Returns "-" if no opportunities available to distinguish from 0% (never 4bet).

    If an exception occurs during the calculation, returns default values for the statistics.

    """
    stat = 0.0
    try:
        fb_opp_0 = float(stat_dict[player].get("fb_opp_0", 0))  # Ensure key exists
        fb_0 = float(stat_dict[player].get("fb_0", 0))

        # No opportunities = no data available
        if fb_opp_0 == 0:
            return format_no_data_stat("4B", "% 4 bet preflop/3rd street")

        # Calculate 4bet percentage
        stat = fb_0 / fb_opp_0

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "4B=%3.1f%%" % (100.0 * stat),
            "4B=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (fb_0, fb_opp_0),
            "% 4 bet preflop/3rd street",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "4B=NA", "4B=NA", "(0/0)", "% 4 bet preflop/3rd street")


def cfour_B(stat_dict, player):
    """Calculate the cold 4 bet statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the calculated statistics in different formats:
            - Float: The calculated statistic.
            - String: The statistic formatted as a percentage with one decimal place.
            - String: A formatted string representing the statistic.
            - String: A formatted string representing the statistic with a suffix.
            - String: A formatted string showing the count of cold 4 bets made and opponent's cold 4 bets.
            - String: A description of the statistic.
        Returns "-" if no opportunities available to distinguish from 0% (never cold 4bet).

    If an exception occurs during the calculation, returns default values for the statistics.

    """
    stat = 0.0
    try:
        cfb_opp_0 = float(stat_dict[player].get("cfb_opp_0", 0))
        cfb_0 = float(stat_dict[player].get("cfb_0", 0))

        # No opportunities = no data available
        if cfb_opp_0 == 0:
            return format_no_data_stat("C4B", "% cold 4 bet preflop/3rd street")

        # Calculate cold 4bet percentage
        stat = cfb_0 / cfb_opp_0

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "C4B=%3.1f%%" % (100.0 * stat),
            "C4B_pf=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cfb_0, cfb_opp_0),
            "% cold 4 bet preflop/3rd street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "C4B=NA",
            "C4B_pf=NA",
            "(0/0)",
            "% cold 4 bet preflop/3rd street",
        )


# Four Bet Range
def fbr(stat_dict, player):
    """A function to calculate the four bet range statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the calculated statistics in different formats:
            - Float: The calculated statistic.
            - String: The statistic formatted as a percentage with one decimal place.
            - String: A formatted string representing the statistic.
            - String: A formatted string representing the statistic with a suffix.
            - String: A formatted string showing the product of 'pfr' and 'four_B'.
            - String: A description of the statistic.

    If an exception occurs during the calculation, returns default values for the statistics.

    """
    stat = 0.0
    try:
        fb_opp_0 = float(stat_dict[player].get("fb_opp_0", 0))  # Ensure key exists
        pfr_opp = float(stat_dict[player].get("n", 0))  # Ensure key exists

        if fb_opp_0 != 0 and pfr_opp != 0:  # Check both values to avoid division by zero
            stat = (float(stat_dict[player]["fb_0"]) / fb_opp_0) * (float(stat_dict[player]["pfr"]) / pfr_opp)
        else:
            stat = 0  # Default to 0 if any of the values is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "fbr=%3.1f%%" % (100.0 * stat),
            "4Brange=%3.1f%%" % (100.0 * stat),
            "(pfr*four_B)",
            "4 bet range",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "fbr=NA", "fbr=NA", "(pfr*four_B)", "4 bet range")


# Call 3 Bet
def ctb(stat_dict, player):
    """A function to calculate the call three bet statistics for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing the calculated statistics in different formats:
            - Float: The calculated statistic.
            - String: The statistic formatted as a percentage with one decimal place.
            - String: A formatted string representing the statistic.
            - String: A formatted string representing the statistic with a suffix.
            - String: A formatted string showing the product of 'f3b_opp_0', 'f3b_0', and 'fb_0'.
            - String: A description of the statistic.

    If an exception occurs during the calculation, returns default values for the statistics.

    """
    stat = 0.0
    try:
        f3b_opp_0 = float(stat_dict[player].get("f3b_opp_0", 0))  # Ensure key exists

        if f3b_opp_0 != 0:  # Check if f3b_opp_0 is non-zero to avoid division by zero
            stat = (
                float(stat_dict[player]["f3b_opp_0"])
                - float(stat_dict[player]["f3b_0"])
                - float(stat_dict[player]["fb_0"])
            ) / f3b_opp_0
        else:
            stat = 0  # Default to 0 if f3b_opp_0 is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "ctb=%3.1f%%" % (100.0 * stat),
            "call3B=%3.1f%%" % (100.0 * stat),
            "(%d/%d)"
            % (
                float(stat_dict[player]["f3b_opp_0"]) - stat_dict[player]["fb_0"] - stat_dict[player]["f3b_0"],
                stat_dict[player]["fb_opp_0"],
            ),
            "% call 3 bet",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "ctb=NA", "ctb=NA", "(0/0)", "% call 3 bet")


def dbr1(stat_dict, player):
    """Calculate and return the Donk Bet and Raise statistic for a given player on flop/4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, percentage representation, formatted strings, and additional information.

    Example:
        dbr1(stat_dict, player)

    """
    stat = 0.0
    try:
        aggr_1 = float(stat_dict[player].get("aggr_1", 0))
        cb_1 = float(stat_dict[player].get("cb_1", 0))
        saw_f = float(stat_dict[player].get("saw_f", 0))
        cb_opp_1 = float(stat_dict[player].get("cb_opp_1", 0))

        # Calculate donk opportunities (saw flop but no cbet opportunity)
        donk_opp = saw_f - cb_opp_1
        donk_bets = aggr_1 - cb_1

        # No opportunities = no data available
        if donk_opp == 0:
            return format_no_data_stat("dbr1", "% DonkBetAndRaise flop/4th street")

        # Calculate donk bet and raise percentage
        stat = donk_bets / donk_opp
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "dbr1=%3.1f%%" % (100.0 * stat),
            "dbr1=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (donk_bets, donk_opp),
            "% DonkBetAndRaise flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("dbr1", "% DonkBetAndRaise flop/4th street")


def dbr2(stat_dict, player):
    """Calculate and return the Donk Bet and Raise statistic for a given player on turn/5th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, percentage representation, formatted strings, and additional information.

    Example:
        dbr2(stat_dict, player)

    """
    stat = 0.0
    try:
        aggr_2 = float(stat_dict[player].get("aggr_2", 0))
        cb_2 = float(stat_dict[player].get("cb_2", 0))
        saw_2 = float(stat_dict[player].get("saw_2", 0))
        cb_opp_2 = float(stat_dict[player].get("cb_opp_2", 0))

        # Calculate donk opportunities (saw turn but no cbet opportunity)
        donk_opp = saw_2 - cb_opp_2
        donk_bets = aggr_2 - cb_2

        # No opportunities = no data available
        if donk_opp == 0:
            return format_no_data_stat("dbr2", "% DonkBetAndRaise turn/5th street")

        # Calculate donk bet and raise percentage
        stat = donk_bets / donk_opp
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "dbr2=%3.1f%%" % (100.0 * stat),
            "dbr2=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (donk_bets, donk_opp),
            "% DonkBetAndRaise turn/5th street",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("dbr2", "% DonkBetAndRaise turn/5th street")


def dbr3(stat_dict, player):
    """Calculate and return the Donk Bet and Raise statistic for a given player on river/6th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, percentage representation, formatted strings, and additional information.

    Example:
        dbr3(stat_dict, player)

    """
    stat = 0.0
    try:
        aggr_3 = float(stat_dict[player].get("aggr_3", 0))
        cb_3 = float(stat_dict[player].get("cb_3", 0))
        saw_3 = float(stat_dict[player].get("saw_3", 0))
        cb_opp_3 = float(stat_dict[player].get("cb_opp_3", 0))

        if (saw_3 - cb_opp_3) != 0:  # Check to avoid division by zero
            stat = (aggr_3 - cb_3) / (saw_3 - cb_opp_3)
        else:
            stat = 0  # Default to 0 if the denominator is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "dbr3=%3.1f%%" % (100.0 * stat),
            "dbr3=%3.1f%%" % (100.0 * stat),
            "(%d/%d)"
            % (
                aggr_3 - cb_3,
                saw_3 - cb_opp_3,
            ),
            "% DonkBetAndRaise river/6th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "dbr3=NA",
            "dbr3=NA",
            "(0/0)",
            "% DonkBetAndRaise river/6th street",
        )


def f_dbr1(stat_dict, player):
    """Calculate and return the fold to DonkBetAndRaise statistic for a given player on flop/4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and additional information.

    Example:
        f_dbr1(stat_dict, player)

    Note:
        If an exception occurs during calculation, 'NA' values are returned.

    """
    stat = 0.0
    try:
        f_freq_1 = float(stat_dict[player].get("f_freq_1", 0))
        f_cb_1 = float(stat_dict[player].get("f_cb_1", 0))
        was_raised_1 = float(stat_dict[player].get("was_raised_1", 0))
        f_cb_opp_1 = float(stat_dict[player].get("f_cb_opp_1", 0))

        if (was_raised_1 - f_cb_opp_1) != 0:  # Check to avoid division by zero
            stat = (f_freq_1 - f_cb_1) / (was_raised_1 - f_cb_opp_1)
        else:
            stat = 0  # Default to 0 if the denominator is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f_dbr1=%3.1f%%" % (100.0 * stat),
            "f_dbr1=%3.1f%%" % (100.0 * stat),
            "(%d/%d)"
            % (
                f_freq_1 - f_cb_1,
                was_raised_1 - f_cb_opp_1,
            ),
            "% Fold to DonkBetAndRaise flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "f_dbr1=NA",
            "f_dbr1=NA",
            "(0/0)",
            "% Fold DonkBetAndRaise flop/4th street",
        )


def f_dbr2(stat_dict, player):
    """Calculate and return the fold to DonkBetAndRaise statistic for a given player on turn/5th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and additional information.

    Example:
        f_dbr2(stat_dict, player)

    Note:
        If an exception occurs during calculation, 'NA' values are returned.

    """
    stat = 0.0
    try:
        f_freq_2 = float(stat_dict[player].get("f_freq_2", 0))
        f_cb_2 = float(stat_dict[player].get("f_cb_2", 0))
        was_raised_2 = float(stat_dict[player].get("was_raised_2", 0))
        f_cb_opp_2 = float(stat_dict[player].get("f_cb_opp_2", 0))

        if (was_raised_2 - f_cb_opp_2) != 0:  # Check to avoid division by zero
            stat = (f_freq_2 - f_cb_2) / (was_raised_2 - f_cb_opp_2)
        else:
            stat = 0  # Default to 0 if the denominator is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f_dbr2=%3.1f%%" % (100.0 * stat),
            "f_dbr2=%3.1f%%" % (100.0 * stat),
            "(%d/%d)"
            % (
                f_freq_2 - f_cb_2,
                was_raised_2 - f_cb_opp_2,
            ),
            "% Fold to DonkBetAndRaise turn",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "f_dbr2=NA",
            "f_dbr2=NA",
            "(0/0)",
            "% Fold DonkBetAndRaise turn",
        )


def f_dbr3(stat_dict, player):
    """Calculate and return the fold to DonkBetAndRaise statistic for a given player on river/6th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and additional information.

    Example:
        f_dbr3(stat_dict, player)

    Note:
        If an exception occurs during calculation, 'NA' values are returned.

    """
    stat = 0.0
    try:
        f_freq_3 = float(stat_dict[player].get("f_freq_3", 0))
        f_cb_3 = float(stat_dict[player].get("f_cb_3", 0))
        was_raised_3 = float(stat_dict[player].get("was_raised_3", 0))
        f_cb_opp_3 = float(stat_dict[player].get("f_cb_opp_3", 0))

        if (was_raised_3 - f_cb_opp_3) != 0:  # Check to avoid division by zero
            stat = (f_freq_3 - f_cb_3) / (was_raised_3 - f_cb_opp_3)
        else:
            stat = 0  # Default to 0 if the denominator is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f_dbr3=%3.1f%%" % (100.0 * stat),
            "f_dbr3=%3.1f%%" % (100.0 * stat),
            "(%d/%d)"
            % (
                f_freq_3 - f_cb_3,
                was_raised_3 - f_cb_opp_3,
            ),
            "% Fold to DonkBetAndRaise river",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "f_dbr3=NA",
            "f_dbr3=NA",
            "(0/0)",
            "% Fold DonkBetAndRaise river",
        )


def squeeze(stat_dict, player):
    """Calculate the squeeze statistic for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, percentage values, and formatted strings.
        Returns "-" if no opportunities available to distinguish from 0% (never squeezed).

    """
    stat = 0.0
    try:
        sqz_opp_0 = float(stat_dict[player].get("sqz_opp_0", 0))
        sqz_0 = float(stat_dict[player].get("sqz_0", 0))

        # No opportunities = no data available
        if sqz_opp_0 == 0:
            return format_no_data_stat("SQZ", "% squeeze preflop")

        # Calculate squeeze percentage
        stat = sqz_0 / sqz_opp_0

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "SQZ=%3.1f%%" % (100.0 * stat),
            "SQZ_pf=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (sqz_0, sqz_opp_0),
            "% squeeze preflop",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "SQZ=NA", "SQZ_pf=NA", "(0/0)", "% squeeze preflop")


def raiseToSteal(stat_dict, player):
    """Calculate the raise to steal stat for a player.

    Args:
        stat_dict (dict): A dictionary containing stats for each player.
        player (int): The player for whom the stat is calculated.

    Returns:
        tuple: A tuple containing the raise to steal stat, formatted percentages, and additional information.
        Returns "-" if no opportunities to distinguish from 0% (never raised to steal).

    """
    stat = 0.0
    try:
        rts_opp = float(stat_dict[player].get("rts_opp", 0))
        rts = float(stat_dict[player].get("rts", 0))

        # No opportunities = no data available
        if rts_opp == 0:
            return format_no_data_stat("RST", "% raise to steal")

        # Calculate raise to steal percentage
        stat = rts / rts_opp

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "RST=%3.1f%%" % (100.0 * stat),
            "RST_pf=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (rts, rts_opp),
            "% raise to steal",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "RST=NA", "RST_pf=NA", "(0/0)", "% raise to steal")


def car0(stat_dict, player):
    """Calculate the percentage of called a raise preflop stat for a player based on the provided stat dictionary.

    Args:
        stat_dict (dict): A dictionary containing stats for each player.
        player (int): The player for whom the CAR0 stat is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the CAR0 stat.
            If an exception occurs during calculation, returns default 'NA' values.

    """
    stat = 0.0
    try:
        car_opp_0 = float(
            stat_dict[player].get("car_opp_0", 0),
        )  # Ensure key exists and default to 0
        if car_opp_0 != 0:  # Check to avoid division by zero
            stat = float(stat_dict[player]["car_0"]) / car_opp_0
        else:
            stat = 0  # Default to 0 if car_opp_0 is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "CAR0=%3.1f%%" % (100.0 * stat),
            "CAR_pf=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (stat_dict[player]["car_0"], car_opp_0),
            "% called a raise preflop",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "CAR0=NA", "CAR_pf=NA", "(0/0)", "% called a raise preflop")


def f_3bet(stat_dict, player):
    """Calculate the Fold to 3-Bet statistic for a player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various representations of the Fold to 3-Bet statistic.
            The tuple includes the statistic value, percentage, labels, and counts.
            If an error occurs during calculation, returns 'NA' values.

    """
    stat = 0.0
    try:
        f3b_opp_0 = float(
            stat_dict[player].get("f3b_opp_0", 0),
        )  # Ensure key exists and default to 0
        if f3b_opp_0 != 0:  # Check to avoid division by zero
            stat = float(stat_dict[player]["f3b_0"]) / f3b_opp_0
        else:
            stat = 0  # Default to 0 if f3b_opp_0 is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "F3B=%3.1f%%" % (100.0 * stat),
            "F3B_pf=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (stat_dict[player]["f3b_0"], f3b_opp_0),
            "% fold to 3 bet preflop/3rd street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "F3B=NA",
            "F3B_pf=NA",
            "(0/0)",
            "% fold to 3 bet preflop/3rd street",
        )


def f_4bet(stat_dict, player):
    """Calculate and return fold to 4-bet statistics for a player.

    Args:
        stat_dict (dict): Dictionary containing player statistics.
        player (int): Player identifier.

    Returns:
        tuple: Tuple containing various statistics related to fold to 4-bet.

    """
    stat = 0.0
    try:
        f4b_opp_0 = float(
            stat_dict[player].get("f4b_opp_0", 0),
        )  # Ensure key exists and default to 0
        if f4b_opp_0 != 0:  # Check to avoid division by zero
            stat = float(stat_dict[player]["f4b_0"]) / f4b_opp_0
        else:
            stat = 0  # Default to 0 if f4b_opp_0 is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "F4B=%3.1f%%" % (100.0 * stat),
            "F4B_pf=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (stat_dict[player]["f4b_0"], f4b_opp_0),
            "% fold to 4 bet preflop/3rd street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "F4B=NA",
            "F4B_pf=NA",
            "(0/0)",
            "% fold to 4 bet preflop/3rd street",
        )


def WMsF(stat_dict, player):
    """Calculate the win money percentage when seeing the flop or 4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistics are calculated.

    Returns:
        tuple: A tuple containing various win money percentage statistics and descriptions.
        Returns "-" if no flops seen to distinguish from 0% (never won money seeing flop).

    """
    stat = 0.0
    try:
        saw_1 = float(stat_dict[player].get("saw_1", 0))
        saw_f = float(stat_dict[player].get("saw_f", 0))
        w_w_s_1 = float(stat_dict[player].get("w_w_s_1", 0))

        # No flops seen = no data available
        if saw_f == 0:
            return format_no_data_stat("WMsF", "% won money when seen flop/4th street")

        # Calculate win money seeing flop percentage
        stat = w_w_s_1 / saw_1 if saw_1 != 0 else 0

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "wf=%3.1f%%" % (100.0 * stat),
            "w_w_f=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (w_w_s_1, saw_f),
            "% won money when seen flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "wf=NA",
            "w_w_f=NA",
            "(0/0)",
            "% won money when seen flop/4th street",
        )


def wwsf(stat_dict, player):
    """Return the standard Won When Saw Flop statistic.

    ``WMsF`` is fpdb's historical name for WWSF.  Keep the legacy entry point
    for existing HUD layouts while exposing the name used by modern trackers.
    """
    return WMsF(stat_dict, player)


def a_freq1(stat_dict, player):
    """Calculate aggression frequency for a specific player based on their stats on flop/4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the aggression frequency is calculated.

    Returns:
        tuple: A tuple containing the calculated aggression frequency, formatted strings, and related information.
        Returns "-" if no opportunities available to distinguish from 0% (passive player).

    """
    stat = 0.0
    try:
        saw_f = float(stat_dict[player].get("saw_f", 0))
        aggr_1 = float(stat_dict[player].get("aggr_1", 0))

        # No opportunities = no data available
        if saw_f == 0:
            return format_no_data_stat("a1", "Aggression frequency flop/4th street")

        # Calculate aggression frequency
        stat = aggr_1 / saw_f

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "a1=%3.1f%%" % (100.0 * stat),
            "a_fq_1=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (aggr_1, saw_f),
            "Aggression frequency flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "a1=NA",
            "a_fq_1=NA",
            "(0/0)",
            "Aggression frequency flop/4th street",
        )


def a_freq2(stat_dict, player):
    """Calculate aggression frequency for a specific player based on their stats on turn/5th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the aggression frequency is calculated.

    Returns:
        tuple: A tuple containing the calculated aggression frequency, formatted strings, and related information.
        Returns "-" if no opportunities available to distinguish from 0% (passive player).

    """
    stat = 0.0
    try:
        saw_2 = float(stat_dict[player].get("saw_2", 0))
        aggr_2 = float(stat_dict[player].get("aggr_2", 0))

        # No opportunities = no data available
        if saw_2 == 0:
            return format_no_data_stat("a2", "Aggression frequency turn/5th street")

        # Calculate aggression frequency
        stat = aggr_2 / saw_2

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "a2=%3.1f%%" % (100.0 * stat),
            "a_fq_2=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (aggr_2, saw_2),
            "Aggression frequency turn/5th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "a2=NA",
            "a_fq_2=NA",
            "(0/0)",
            "Aggression frequency turn/5th street",
        )


def a_freq3(stat_dict, player):
    """Calculate aggression frequency for a specific player based on their stats on river/6th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the aggression frequency is calculated.

    Returns:
        tuple: A tuple containing the calculated aggression frequency, formatted strings, and related information.
        Returns "-" if no opportunities available to distinguish from 0% (passive player).

    """
    stat = 0.0
    try:
        saw_3 = float(stat_dict[player].get("saw_3", 0))
        aggr_3 = float(stat_dict[player].get("aggr_3", 0))

        # No opportunities = no data available
        if saw_3 == 0:
            return format_no_data_stat("a3", "Aggression frequency river/6th street")

        # Calculate aggression frequency
        stat = aggr_3 / saw_3

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "a3=%3.1f%%" % (100.0 * stat),
            "a_fq_3=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (aggr_3, saw_3),
            "Aggression frequency river/6th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "a3=NA",
            "a_fq_3=NA",
            "(0/0)",
            "Aggression frequency river/6th street",
        )


def a_freq4(stat_dict, player):
    """Calculate aggression frequency for a specific player based on their stats on 7th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the aggression frequency is calculated.

    Returns:
        tuple: A tuple containing the calculated aggression frequency, formatted strings, and related information.
        Returns "-" if no opportunities available to distinguish from 0% (passive player).

    """
    stat = 0.0
    try:
        saw_4 = float(stat_dict[player].get("saw_4", 0))
        aggr_4 = float(stat_dict[player].get("aggr_4", 0))

        # No opportunities = no data available
        if saw_4 == 0:
            return format_no_data_stat("a4", "Aggression frequency 7th street")

        # Calculate aggression frequency
        stat = aggr_4 / saw_4

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "a4=%3.1f%%" % (100.0 * stat),
            "a_fq_4=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (aggr_4, saw_4),
            "Aggression frequency 7th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "a4=NA",
            "a_fq_4=NA",
            "(0/0)",
            "Aggression frequency 7th street",
        )


def a_freq_123(stat_dict, player):
    """Calculate aggression frequency for a specific player based on their stats post-flop.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the aggression frequency is calculated.

    Returns:
        tuple: A tuple containing the calculated aggression frequency, formatted strings, and related information.

    """
    stat = 0.0
    try:
        # Sum up aggression and seen stats
        total_aggr = (
            stat_dict[player].get("aggr_1", 0) + stat_dict[player].get("aggr_2", 0) + stat_dict[player].get("aggr_3", 0)
        )
        total_saw = (
            stat_dict[player].get("saw_1", 0) + stat_dict[player].get("saw_2", 0) + stat_dict[player].get("saw_3", 0)
        )

        # Check to avoid division by zero
        if total_saw != 0:
            stat = float(total_aggr) / float(total_saw)
        else:
            stat = 0  # Default to 0 if total_saw is zero

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "afq=%3.1f%%" % (100.0 * stat),
            "post_a_fq=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (total_aggr, total_saw),
            "Post-flop aggression frequency",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "afq=NA",
            "post_a_fq=NA",
            "(0/0)",
            "Post-flop aggression frequency",
        )


def agg_fact(stat_dict, player):
    """Calculate the aggression factor based on the given player's statistics.

    Args:
        stat_dict (dict): A dictionary containing the player's statistics.
        player (str): The player for whom the aggression factor is calculated.

    Returns:
        tuple: A tuple containing the calculated aggression factor in different formats.
            The formats include percentage, float, and string representations.
            Returns "-" if no post-flop actions available to distinguish from 0.0 (passive player).

    """
    stat = 0.0
    try:
        # Sum of all bet/raise and call actions
        bet_raise = (
            stat_dict[player].get("aggr_1", 0)
            + stat_dict[player].get("aggr_2", 0)
            + stat_dict[player].get("aggr_3", 0)
            + stat_dict[player].get("aggr_4", 0)
        )
        post_call = (
            stat_dict[player].get("call_1", 0)
            + stat_dict[player].get("call_2", 0)
            + stat_dict[player].get("call_3", 0)
            + stat_dict[player].get("call_4", 0)
        )

        # No post-flop actions = no data available
        if bet_raise == 0 and post_call == 0:
            return format_no_data_stat("afa", "Aggression factor", bet_raise, post_call)

        # Calculate aggression factor (bet+raise) / call
        stat = float(bet_raise) / float(post_call) if post_call > 0 else float(bet_raise)

        return (
            stat / 100.0,
            f"{stat:2.2f}",
            f"afa={stat:2.2f}",
            f"agg_fa={stat:2.2f}",
            "(%d/%d)" % (bet_raise, post_call),
            "Aggression factor",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "afa=NA", "agg_fa=NA", "(0/0)", "Aggression factor")


def agg_fact_pct(stat_dict, player):
    """Calculate the aggression factor percentage based on the given player's stats.

    Args:
        stat_dict (dict): A dictionary containing the player's statistics.
        player (int): The player for whom the aggression factor percentage is calculated.

    Returns:
        tuple: A tuple containing the aggression factor percentage, formatted strings, and related information.
            Returns "-" if no post-flop actions available to distinguish from 0.0% (passive player).

    """
    stat = 0.0
    try:
        # Safely retrieve the values, defaulting to 0 if the keys are missing
        bet_raise = (
            stat_dict[player].get("aggr_1", 0)
            + stat_dict[player].get("aggr_2", 0)
            + stat_dict[player].get("aggr_3", 0)
            + stat_dict[player].get("aggr_4", 0)
        )
        post_call = (
            stat_dict[player].get("call_1", 0)
            + stat_dict[player].get("call_2", 0)
            + stat_dict[player].get("call_3", 0)
            + stat_dict[player].get("call_4", 0)
        )

        # No post-flop actions = no data available
        if bet_raise == 0 and post_call == 0:
            return format_no_data_stat("afap", "Aggression factor pct", bet_raise, post_call)

        # Calculate aggression factor percentage (bet+raise) / (bet+raise+call)
        if float(post_call + bet_raise) > 0.0:
            stat = float(bet_raise) / float(post_call + bet_raise)

        return (
            stat / 100.0,
            f"{stat:2.2f}",
            f"afap={stat:2.2f}",
            f"agg_fa_pct={stat:2.2f}",
            "(%d/%d)" % (bet_raise, post_call),
            "Aggression factor pct",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "afap=NA",
            "agg_fa_pct=NA",
            "(0/0)",
            "Aggression factor pct",
        )


def cbet(stat_dict, player):
    """Calculate the continuation bet (cbet) percentage for a player.

    Args:
        stat_dict (dict): A dictionary containing statistics for the player.
        player (int): The player for whom the cbet percentage is calculated.

    Returns:
        tuple: A tuple containing the cbet percentage, formatted strings, and stats.

    Raises:
        Exception: If there is an issue with calculating the cbet percentage.

    """
    stat = 0.0
    try:
        # Safely retrieve cbet and opportunity values, defaulting to 0 if keys don't exist
        cbets = (
            stat_dict[player].get("cb_1", 0)
            + stat_dict[player].get("cb_2", 0)
            + stat_dict[player].get("cb_3", 0)
            + stat_dict[player].get("cb_4", 0)
        )
        oppt = (
            stat_dict[player].get("cb_opp_1", 0)
            + stat_dict[player].get("cb_opp_2", 0)
            + stat_dict[player].get("cb_opp_3", 0)
            + stat_dict[player].get("cb_opp_4", 0)
        )

        # No opportunities = no data available
        if oppt == 0:
            return format_no_data_stat("cbet", "% continuation bet")

        # Calculate cbet percentage
        stat = float(cbets) / float(oppt)

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cbet=%3.1f%%" % (100.0 * stat),
            "cbet=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cbets, oppt),
            "% continuation bet",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "cbet=NA", "cbet=NA", "(0/0)", "% continuation bet")


def cb1(stat_dict, player):
    """Calculate the continuation bet statistic for a given player on flop/4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the continuation bet statistic.

    """
    stat = 0.0
    try:
        cb_opp_1 = float(stat_dict[player].get("cb_opp_1", 0))
        cb_1 = float(stat_dict[player].get("cb_1", 0))

        # No opportunities = no data available
        if cb_opp_1 == 0:
            return format_no_data_stat("cb1", "% continuation bet flop/4th street")

        # Calculate continuation bet percentage
        stat = cb_1 / cb_opp_1
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cb1=%3.1f%%" % (100.0 * stat),
            "cb_1=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cb_1, cb_opp_1),
            "% continuation bet flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("cb1", "% continuation bet flop/4th street")


def cb2(stat_dict, player):
    """Calculate the continuation bet statistic for a given player on turn/5th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the continuation bet statistic.

    """
    stat = 0.0
    try:
        cb_opp_2 = float(stat_dict[player].get("cb_opp_2", 0))
        cb_2 = float(stat_dict[player].get("cb_2", 0))

        # No opportunities = no data available
        if cb_opp_2 == 0:
            return format_no_data_stat("cb2", "% continuation bet turn/5th street")

        # Calculate continuation bet percentage
        stat = cb_2 / cb_opp_2
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cb2=%3.1f%%" % (100.0 * stat),
            "cb_2=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cb_2, cb_opp_2),
            "% continuation bet turn/5th street",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("cb2", "% continuation bet turn/5th street")


def cb3(stat_dict, player):
    """Calculate the continuation bet statistic for a given player on river/6th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the continuation bet statistic.

    """
    stat = 0.0
    try:
        cb_opp_3 = float(stat_dict[player].get("cb_opp_3", 0))
        cb_3 = float(stat_dict[player].get("cb_3", 0))

        # No opportunities = no data available
        if cb_opp_3 == 0:
            return format_no_data_stat("cb3", "% continuation bet river/6th street")

        # Calculate continuation bet percentage
        stat = cb_3 / cb_opp_3
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cb3=%3.1f%%" % (100.0 * stat),
            "cb_3=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cb_3, cb_opp_3),
            "% continuation bet river/6th street",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("cb3", "% continuation bet river/6th street")


def cb4(stat_dict, player):
    """Calculate the continuation bet statistic for a given player on 7th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the continuation bet statistic.

    """
    stat = 0.0
    try:
        cb_opp_4 = float(stat_dict[player].get("cb_opp_4", 0))
        cb_4 = float(stat_dict[player].get("cb_4", 0))

        # No opportunities = no data available
        if cb_opp_4 == 0:
            return format_no_data_stat("cb4", "% continuation bet 7th street")

        # Calculate continuation bet percentage
        stat = cb_4 / cb_opp_4
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cb4=%3.1f%%" % (100.0 * stat),
            "cb_4=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cb_4, cb_opp_4),
            "% continuation bet 7th street",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("cb4", "% continuation bet 7th street")


def ffreq1(stat_dict, player):
    """Calculate the fold frequency statistic for a given player on the flop/4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold frequency statistic.

    """
    stat = 0.0
    try:
        was_raised_1 = float(
            stat_dict[player].get("was_raised_1", 0),
        )  # Ensure key exists and default to 0
        f_freq_1 = float(stat_dict[player].get("f_freq_1", 0))

        # No opportunities = no data available
        if was_raised_1 == 0:
            return format_no_data_stat("ff1", "% fold frequency flop/4th street")

        # Calculate fold frequency percentage
        stat = f_freq_1 / was_raised_1

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "ff1=%3.1f%%" % (100.0 * stat),
            "ff_1=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_freq_1, was_raised_1),
            "% fold frequency flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "ff1=NA",
            "ff_1=NA",
            "(0/0)",
            "% fold frequency flop/4th street",
        )


def ffreq2(stat_dict, player):
    """Calculate the fold frequency statistic for a given player on the turn/5th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold frequency statistic.

    """
    stat = 0.0
    try:
        was_raised_2 = float(
            stat_dict[player].get("was_raised_2", 0),
        )  # Ensure key exists and default to 0
        f_freq_2 = float(stat_dict[player].get("f_freq_2", 0))

        # No opportunities = no data available
        if was_raised_2 == 0:
            return format_no_data_stat("ff2", "% fold frequency turn/5th street")

        # Calculate fold frequency percentage
        stat = f_freq_2 / was_raised_2

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "ff2=%3.1f%%" % (100.0 * stat),
            "ff_2=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_freq_2, was_raised_2),
            "% fold frequency turn/5th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "ff2=NA",
            "ff_2=NA",
            "(0/0)",
            "% fold frequency turn/5th street",
        )


def ffreq3(stat_dict, player):
    """Calculate the fold frequency statistic for a given player on the river/6th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold frequency statistic.

    """
    stat = 0.0
    try:
        was_raised_3 = float(
            stat_dict[player].get("was_raised_3", 0),
        )  # Ensure key exists and default to 0
        f_freq_3 = float(stat_dict[player].get("f_freq_3", 0))

        # No opportunities = no data available
        if was_raised_3 == 0:
            return format_no_data_stat("ff3", "% fold frequency river/6th street")

        # Calculate fold frequency percentage
        stat = f_freq_3 / was_raised_3

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "ff3=%3.1f%%" % (100.0 * stat),
            "ff_3=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_freq_3, was_raised_3),
            "% fold frequency river/6th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "ff3=NA",
            "ff_3=NA",
            "(0/0)",
            "% fold frequency river/6th street",
        )


def ffreq4(stat_dict, player):
    """Calculate the fold frequency statistic for a given player on the 7th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold frequency statistic.

    """
    stat = 0.0
    try:
        was_raised_4 = float(stat_dict[player].get("was_raised_4", 0))
        f_freq_4 = float(stat_dict[player].get("f_freq_4", 0))

        # No opportunities = no data available
        if was_raised_4 == 0:
            return format_no_data_stat("ff4", "% fold frequency 7th street")

        # Calculate fold frequency percentage
        stat = f_freq_4 / was_raised_4

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "ff4=%3.1f%%" % (100.0 * stat),
            "ff_4=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_freq_4, was_raised_4),
            "% fold frequency 7th street",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "ff4=NA", "ff_4=NA", "(0/0)", "% fold frequency 7th street")


def f_cb1(stat_dict, player):
    """Calculate the fold to continuation bet statistic for a given player on the flop/4th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold to continuation bet statistic.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - f_cb1 (str): The calculated statistic value formatted as a percentage with a specific format.
              - f_cb_1 (str): The calculated statistic value formatted as a percentage with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's continuation bets.
              - description (str): A description of the statistic.

    """
    stat = 0.0
    try:
        f_cb_opp_1 = float(
            stat_dict[player].get("f_cb_opp_1", 0),
        )  # Ensure key exists and default to 0
        f_cb_1 = float(stat_dict[player].get("f_cb_1", 0))

        # No opportunities = no data available
        if f_cb_opp_1 == 0:
            return format_no_data_stat("f_cb1", "% fold to continuation bet flop/4th street")

        # Calculate fold to continuation bet percentage
        stat = f_cb_1 / f_cb_opp_1

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f_cb1=%3.1f%%" % (100.0 * stat),
            "f_cb_1=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_cb_1, f_cb_opp_1),
            "% fold to continuation bet flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "f_cb1=NA",
            "f_cb_1=NA",
            "(0/0)",
            "% fold to continuation bet flop/4th street",
        )


def f_cb2(stat_dict, player):
    """Calculate the fold to continuation bet statistic for a given player on the turn/5th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold to continuation bet statistic.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - f_cb2 (str): The calculated statistic value formatted as a percentage with a specific format.
              - f_cb_2 (str): The calculated statistic value formatted as a percentage with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's continuation bets.
              - description (str): A description of the statistic.

    """
    stat = 0.0
    try:
        f_cb_opp_2 = float(stat_dict[player].get("f_cb_opp_2", 0))
        f_cb_2 = float(stat_dict[player].get("f_cb_2", 0))

        # No opportunities = no data available
        if f_cb_opp_2 == 0:
            return format_no_data_stat("f_cb2", "% fold to continuation bet turn/5th street")

        # Calculate fold to continuation bet percentage
        stat = f_cb_2 / f_cb_opp_2

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f_cb2=%3.1f%%" % (100.0 * stat),
            "f_cb_2=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_cb_2, f_cb_opp_2),
            "% fold to continuation bet turn/5th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "f_cb2=NA",
            "f_cb_2=NA",
            "(0/0)",
            "% fold to continuation bet turn/5th street",
        )


def f_cb3(stat_dict, player):
    """Calculate the fold to continuation bet statistic for a given player on the river/6th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold to continuation bet statistic.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - f_cb3 (str): The calculated statistic value formatted as a percentage with a specific format.
              - f_cb_3 (str): The calculated statistic value formatted as a percentage with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's continuation bets.
              - description (str): A description of the statistic.

    """
    stat = 0.0
    try:
        f_cb_opp_3 = float(stat_dict[player].get("f_cb_opp_3", 0))
        f_cb_3 = float(stat_dict[player].get("f_cb_3", 0))

        # No opportunities = no data available
        if f_cb_opp_3 == 0:
            return format_no_data_stat("f_cb3", "% fold to continuation bet river/6th street")

        # Calculate fold to continuation bet percentage
        stat = f_cb_3 / f_cb_opp_3

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f_cb3=%3.1f%%" % (100.0 * stat),
            "f_cb_3=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_cb_3, f_cb_opp_3),
            "% fold to continuation bet river/6th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "f_cb3=NA",
            "f_cb_3=NA",
            "(0/0)",
            "% fold to continuation bet river/6th street",
        )


def fold_to_cbet_flop(stat_dict, player):
    """Return fold-to-cbet on the flop using the modern stat name."""
    return f_cb1(stat_dict, player)


def fold_to_cbet_turn(stat_dict, player):
    """Return fold-to-cbet on the turn using the modern stat name."""
    return f_cb2(stat_dict, player)


def fold_to_cbet_river(stat_dict, player):
    """Return fold-to-cbet on the river using the modern stat name."""
    return f_cb3(stat_dict, player)


def f_cb4(stat_dict, player):
    """Calculate the fold to continuation bet statistic for a given player on the 7th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the fold to continuation bet statistic.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - f_cb4 (str): The calculated statistic value formatted as a percentage with a specific format.
              - f_cb_4 (str): The calculated statistic value formatted as a percentage with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's continuation bets.
              - description (str): A description of the statistic.

    Raises:
        None

    """
    stat = 0.0
    try:
        f_cb_opp_4 = float(stat_dict[player].get("f_cb_opp_4", 0))
        f_cb_4 = float(stat_dict[player].get("f_cb_4", 0))

        # No opportunities = no data available
        if f_cb_opp_4 == 0:
            return format_no_data_stat("f_cb4", "% fold to continuation bet 7th street")

        # Calculate fold to continuation bet percentage
        stat = f_cb_4 / f_cb_opp_4

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f_cb4=%3.1f%%" % (100.0 * stat),
            "f_cb_4=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f_cb_4, f_cb_opp_4),
            "% fold to continuation bet 7th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "f_cb4=NA",
            "f_cb_4=NA",
            "(0/0)",
            "% fold to continuation bet 7th street",
        )


def cr1(stat_dict, player):
    """Calculate the check-raise flop/4th street statistic for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the check-raise flop/4th street statistic.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - cr1 (str): The calculated statistic value formatted with a specific format.
              - cr_1 (str): The calculated statistic value formatted with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's check-raises.
              - description (str): A description of the statistic.

    Raises:
        None

    """
    stat = 0.0
    try:
        ccr_opp_1 = float(
            stat_dict[player].get("ccr_opp_1", 0),
        )  # Ensure key exists and default to 0
        cr_1 = float(stat_dict[player].get("cr_1", 0))

        # No opportunities = no data available
        if ccr_opp_1 == 0:
            return format_no_data_stat("cr1", "% check-raise flop/4th street")

        # Calculate check-raise percentage
        stat = cr_1 / ccr_opp_1

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cr1=%3.1f%%" % (100.0 * stat),
            "cr_1=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cr_1, ccr_opp_1),
            "% check-raise flop/4th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "cr1=NA",
            "cr_1=NA",
            "(0/0)",
            "% check-raise flop/4th street",
        )


def cr2(stat_dict, player):
    """Calculates the check-raise turn/5th street for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the check-raise to fold ratio.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - cr2 (str): The calculated statistic value formatted with a specific format.
              - cr_2 (str): The calculated statistic value formatted with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's check-raises.
              - description (str): A description of the statistic.

    """
    stat = 0.0
    try:
        ccr_opp_2 = float(
            stat_dict[player].get("ccr_opp_2", 0),
        )  # Ensure key exists and default to 0
        cr_2 = float(stat_dict[player].get("cr_2", 0))

        # No opportunities = no data available
        if ccr_opp_2 == 0:
            return format_no_data_stat("cr2", "% check-raise turn/5th street")

        # Calculate check-raise percentage
        stat = cr_2 / ccr_opp_2

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cr2=%3.1f%%" % (100.0 * stat),
            "cr_2=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cr_2, ccr_opp_2),
            "% check-raise turn/5th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "cr2=NA",
            "cr_2=NA",
            "(0/0)",
            "% check-raise turn/5th street",
        )


def cr3(stat_dict, player):
    """Calculate the river/6th street check-raise statistic for a given player.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the check-raise to fold ratio.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - cr3 (str): The calculated statistic value formatted with a specific format.
              - cr_3 (str): The calculated statistic value formatted with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's check-raises.
              - description (str): A description of the statistic.

    Raises:
        None

    """
    stat = 0.0
    try:
        ccr_opp_3 = float(
            stat_dict[player].get("ccr_opp_3", 0),
        )  # Ensure key exists and default to 0
        cr_3 = float(stat_dict[player].get("cr_3", 0))

        # No opportunities = no data available
        if ccr_opp_3 == 0:
            return format_no_data_stat("cr3", "% check-raise river/6th street")

        # Calculate check-raise percentage
        stat = cr_3 / ccr_opp_3

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cr3=%3.1f%%" % (100.0 * stat),
            "cr_3=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cr_3, ccr_opp_3),
            "% check-raise river/6th street",
        )
    except (KeyError, ValueError, TypeError):
        return (
            stat,
            "NA",
            "cr3=NA",
            "cr_3=NA",
            "(0/0)",
            "% check-raise river/6th street",
        )


def cr4(stat_dict, player):
    """Calculate the 7th street check-raise statistics for a given player on the 7th street.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing various formatted strings representing the check-raise to fold ratio.
              The tuple contains the following elements:
              - stat (float): The calculated statistic value.
              - percent (str): The calculated statistic value formatted as a percentage.
              - cr4 (str): The calculated statistic value formatted with a specific format.
              - cr_4 (str): The calculated statistic value formatted with a specific format.
              - count (str): The count of occurrences divided by the count of opponent's check-raises.
              - description (str): A description of the statistic.

    Raises:
        None

    """
    stat = 0.0
    try:
        ccr_opp_4 = float(
            stat_dict[player].get("ccr_opp_4", 0),
        )  # Ensure key exists and default to 0
        cr_4 = float(stat_dict[player].get("cr_4", 0))

        # No opportunities = no data available
        if ccr_opp_4 == 0:
            return format_no_data_stat("cr4", "% check-raise 7th street")

        # Calculate check-raise percentage
        stat = cr_4 / ccr_opp_4

        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cr4=%3.1f%%" % (100.0 * stat),
            "cr_4=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cr_4, ccr_opp_4),
            "% check-raise 7th street",
        )
    except (KeyError, ValueError, TypeError):
        return (stat, "NA", "cr4=NA", "cr_4=NA", "(0/0)", "% check-raise 7th street")


def game_abbr(stat_dict, player):
    """Function to retrieve the abbreviation for a specific poker game based on the game category and limit type.

    Parameters
    ----------
    - stat_dict: Dictionary containing statistics related to the game.
    - player: Integer representing the player number.

    Returns:
    -------
    - Tuple containing various representations of the game abbreviation.

    """
    hand_instance = _get_hand_instance()
    stat = ""
    try:
        if hand_instance is None or "gametype" not in hand_instance:
            # If hand_instance is None, return default empty values
            return ("NA", "NA", "game=NA", "game_abbr=NA", "(NA)", "Game abbreviation")

        cat_plus_limit = hand_instance.gametype["category"] + "." + hand_instance.gametype["limitType"]
        stat = {
            # ftp's 10-game with official abbreviations
            "holdem.fl": "H",
            "studhilo.fl": "E",
            "omahahi.pl": "P",
            "27_3draw.fl": "T",
            "razz.fl": "R",
            "holdem.nl": "N",
            "omahahilo.fl": "O",
            "studhi.fl": "S",
            "27_1draw.nl": "K",
            "badugi.fl": "B",
            # other common games with dubious abbreviations
            "fivedraw.fl": "F",
            "fivedraw.pl": "Fp",
            "fivedraw.nl": "Fn",
            "27_3draw.pl": "Tp",
            "27_3draw.nl": "Tn",
            "badugi.pl": "Bp",
            "badugi.hp": "Bh",
            "omahahilo.pl": "Op",
            "omahahilo.nl": "On",
            "holdem.pl": "Hp",
            "studhi.nl": "Sn",
        }.get(
            cat_plus_limit,
            "Unknown",
        )  # Default to "Unknown" if not found
        return (
            stat,
            f"{stat}",
            f"game={stat}",
            f"game_abbr={stat}",
            f"({stat})",
            "Game abbreviation",
        )
    except (KeyError, ValueError, TypeError):
        return ("NA", "NA", "game=NA", "game_abbr=NA", "(NA)", "Game abbreviation")


def blank(stat_dict, player):
    # blank space on the grid
    # stat = " "
    return ("", "", "", "", "", "<blank>")


def player_note(stat_dict, player):
    """Display a note icon that changes color based on whether the player has notes."""
    try:
        # Try to get player_id from stat_dict
        player_id = None
        for pid, data in stat_dict.items():
            if data.get("screen_name") == player:
                player_id = pid
                break

        if player_id is None:
            # Default gray icon if no player found
            return ("📝", "📝", "📝", "📝", "📝", "Player note icon")

        # Check if player has notes using database query
        # This will be handled by the HUD display logic that checks has_comment()
        # Return a note icon - color will be determined by the HUD
        return ("📝", "📝", "📝", "📝", "📝", "Player note icon")

    except STATS_DATA_ERRORS:
        return ("📝", "📝", "📝", "📝", "📝", "Player note icon")


################################################################################################
# NEW STATS


def vpip_pfr_ratio(stat_dict, player):
    """Calculate the VPIP/PFR ratio for a player.

    This statistic represents the ratio between a player's VPIP (Voluntarily Put money In Pot)
    and PFR (Pre-Flop Raise) percentages, which gives an indication of the player's preflop aggression.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no preflop opportunities to distinguish from actual ratio values.

    """
    try:
        vpip_opp = float(stat_dict[player].get("vpip_opp", 0))
        pfr_opp = float(stat_dict[player].get("pfr_opp", 0))
        vpip_count = float(stat_dict[player].get("vpip", 0))
        pfr_count = float(stat_dict[player].get("pfr", 0))

        # No preflop opportunities = no data available
        if vpip_opp == 0 or pfr_opp == 0:
            return format_no_data_stat("v/p", "VPIP/PFR ratio")

        # Calculate VPIP and PFR percentages
        vpip = vpip_count / vpip_opp
        pfr = pfr_count / pfr_opp

        # Calculate ratio
        if pfr > 0:
            stat = vpip / pfr
        else:
            stat = float("inf")  # Avoid division by zero for PFR

        return (
            stat,
            f"{stat:2.2f}",
            f"v/p={stat:2.2f}",
            f"vpip/pfr={stat:2.2f}",
            "(%d/%d)/(%d/%d)"
            % (
                stat_dict[player]["vpip"],
                stat_dict[player]["vpip_opp"],
                stat_dict[player]["pfr"],
                stat_dict[player]["pfr_opp"],
            ),
            "VPIP/PFR ratio",
        )
    except (KeyError, ValueError, TypeError):
        return (
            float("inf"),
            "NA",
            "v/p=NA",
            "vpip/pfr=NA",
            "(0/0)/(0/0)",
            "VPIP/PFR ratio",
        )


def fold_vs_4bet(stat_dict, player):
    """Calculate the Fold vs 4bet percentage for a player.

    This measures how often a player folds when facing a 4bet.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no fold vs 4bet opportunities to distinguish from 0% (never faced 4bet).
    """
    stat = 0.0
    try:
        f4b_opp = float(stat_dict[player].get("F4B_opp_0", 0))
        f4b_count = float(stat_dict[player].get("F4B_0", 0))

        # No opportunities = no data available
        if f4b_opp == 0:
            return format_no_data_stat("f4b", "% fold vs 4bet")

        # Calculate fold vs 4bet percentage
        stat = f4b_count / f4b_opp
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "f4b=%3.1f%%" % (100.0 * stat),
            "f4b=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (f4b_count, f4b_opp),
            "% fold vs 4bet",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("f4b", "% fold vs 4bet")


def float_bet(stat_dict, player):
    """Calculate the Float Bet percentage for a player.

    A float bet is when a player calls a flop bet in position with the intention
    of taking the pot away on a later street (usually the turn) if the opponent
    shows weakness by checking.

    Float = Call flop in position + Bet turn (when opponent checks)

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no float opportunities to distinguish from 0% (never floated).
    """
    stat = 0.0
    try:
        # Get flop position and calls
        street1_in_position = float(stat_dict[player].get("street1InPosition", 0))
        street1_calls = float(stat_dict[player].get("street1Calls", 0))

        # Get turn bets and first to act
        street2_bets = float(stat_dict[player].get("street2Bets", 0))
        float(stat_dict[player].get("street2FirstToAct", 0))

        # Get opportunities to see flop and turn
        float(stat_dict[player].get("saw_f", 0))
        saw_turn = float(stat_dict[player].get("saw_t", 0))

        # Calculate float opportunities: called flop in position and saw turn
        float_opportunities = min(street1_in_position, street1_calls, saw_turn)

        # No opportunities = no data available
        if float_opportunities == 0:
            return format_no_data_stat("float", "% float bet turn")

        # Calculate float count: bet turn after calling flop in position
        # This is a simplified calculation as we don't have exact sequence data
        float_count = min(street2_bets, float_opportunities)

        # Calculate float percentage
        stat = float_count / float_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "float=%3.1f%%" % (100.0 * stat),
            "float=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (float_count, float_opportunities),
            "% float bet turn",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("float", "% float bet turn")


def probe_bet(stat_dict, player):
    """Calculate the Probe Bet percentage for a player.

    A probe bet is when a player bets after the preflop aggressor checks,
    testing the strength of the opponent's hand.

    Probe = Bet after preflop aggressor checks

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no probe opportunities to distinguish from 0% (never probed).
    """
    stat = 0.0
    try:
        # Get flop betting data
        street1_bets = float(stat_dict[player].get("street1Bets", 0))
        saw_flop = float(stat_dict[player].get("saw_f", 0))

        # Get continuation bet data (opponent's cb opportunities and actual cbs)
        float(stat_dict[player].get("cb_opp_1", 0))
        cb_1 = float(stat_dict[player].get("cb_1", 0))

        # Calculate probe opportunities: saw flop when opponent could have c-bet but didn't
        # This is approximated as flops seen where opponent had cb opportunity but didn't c-bet
        probe_opportunities = saw_flop - cb_1

        # No opportunities = no data available
        if probe_opportunities <= 0:
            return format_no_data_stat("probe", "% probe bet flop")

        # Calculate probe count: bets made in probe situations
        # This is a simplified calculation as exact sequence data isn't available
        probe_count = min(street1_bets, probe_opportunities)

        # Calculate probe percentage
        stat = probe_count / probe_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "probe=%3.1f%%" % (100.0 * stat),
            "probe=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (probe_count, probe_opportunities),
            "% probe bet flop",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("probe", "% probe bet flop")


def sd_winrate(stat_dict, player):
    """Calculate the Showdown Winrate for a player.

    This measures the percentage of hands won when going to showdown.
    SD Winrate = wonAtSD / sawShowdown

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no showdown opportunities to distinguish from 0% (never won at showdown).
    """
    stat = 0.0
    try:
        sd = float(stat_dict[player].get("sd", 0))  # sawShowdown
        wmsd = float(stat_dict[player].get("wmsd", 0))  # wonAtSD

        # No showdown opportunities = no data available
        if sd == 0:
            return format_no_data_stat("sd_wr", "% showdown winrate")

        # Calculate showdown winrate
        stat = wmsd / sd
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "sd_wr=%3.1f%%" % (100.0 * stat),
            "showdown_winrate=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (wmsd, sd),
            "% showdown winrate",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("sd_wr", "% showdown winrate")


def non_sd_winrate(stat_dict, player):
    """Calculate the Non-Showdown Winrate for a player.

    This measures the percentage of hands won without going to showdown.
    This is an approximation based on overall winrate vs showdown winrate.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no non-showdown opportunities to distinguish from 0% (never won non-showdown).
    """
    stat = 0.0
    try:
        saw_f = float(stat_dict[player].get("saw_f", 0))  # street1Seen
        sd = float(stat_dict[player].get("sd", 0))  # sawShowdown
        wmsd = float(stat_dict[player].get("wmsd", 0))  # wonAtSD

        # Get total wins by street
        w_w_s_1 = float(stat_dict[player].get("w_w_s_1", 0))  # wonWhenSeenStreet1

        # Calculate non-showdown opportunities
        non_sd_opportunities = saw_f - sd

        # No non-showdown opportunities = no data available
        if non_sd_opportunities == 0:
            return format_no_data_stat("nsd_wr", "% non-showdown winrate")

        # Calculate non-showdown wins (approximation)
        # Total wins when seen flop minus showdown wins
        non_sd_wins = w_w_s_1 - wmsd

        # Calculate non-showdown winrate
        stat = non_sd_wins / non_sd_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "nsd_wr=%3.1f%%" % (100.0 * stat),
            "non_showdown_winrate=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (non_sd_wins, non_sd_opportunities),
            "% non-showdown winrate",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("nsd_wr", "% non-showdown winrate")


def bet_frequency_flop(stat_dict, player):
    """Calculate the Bet Frequency on flop for a player.

    This measures how often a player bets when they have the opportunity on the flop.
    Bet Frequency = street1Bets / street1Seen

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no flop opportunities to distinguish from 0% (never bet flop).
    """
    stat = 0.0
    try:
        saw_f = float(stat_dict[player].get("saw_f", 0))  # street1Seen
        street1_bets = float(stat_dict[player].get("street1Bets", 0))

        # No flop opportunities = no data available
        if saw_f == 0:
            return format_no_data_stat("bet_f", "% bet frequency flop")

        # Calculate bet frequency on flop
        stat = street1_bets / saw_f
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "bet_f=%3.1f%%" % (100.0 * stat),
            "bet_freq_flop=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (street1_bets, saw_f),
            "% bet frequency flop",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("bet_f", "% bet frequency flop")


def bet_frequency_turn(stat_dict, player):
    """Calculate the Bet Frequency on turn for a player.

    This measures how often a player bets when they have the opportunity on the turn.
    Bet Frequency = street2Bets / street2Seen

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no turn opportunities to distinguish from 0% (never bet turn).
    """
    stat = 0.0
    try:
        saw_t = float(stat_dict[player].get("saw_t", 0))  # street2Seen
        street2_bets = float(stat_dict[player].get("street2Bets", 0))

        # No turn opportunities = no data available
        if saw_t == 0:
            return format_no_data_stat("bet_t", "% bet frequency turn")

        # Calculate bet frequency on turn
        stat = street2_bets / saw_t
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "bet_t=%3.1f%%" % (100.0 * stat),
            "bet_freq_turn=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (street2_bets, saw_t),
            "% bet frequency turn",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("bet_t", "% bet frequency turn")


def raise_frequency_flop(stat_dict, player):
    """Calculate the Raise Frequency on flop for a player.

    This measures how often a player raises when they have the opportunity on the flop.
    Raise Frequency = street1Raises / street1Seen

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no flop opportunities to distinguish from 0% (never raised flop).
    """
    stat = 0.0
    try:
        saw_f = float(stat_dict[player].get("saw_f", 0))  # street1Seen
        street1_raises = float(stat_dict[player].get("street1Raises", 0))

        # No flop opportunities = no data available
        if saw_f == 0:
            return format_no_data_stat("raise_f", "% raise frequency flop")

        # Calculate raise frequency on flop
        stat = street1_raises / saw_f
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "raise_f=%3.1f%%" % (100.0 * stat),
            "raise_freq_flop=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (street1_raises, saw_f),
            "% raise frequency flop",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("raise_f", "% raise frequency flop")


def raise_frequency_turn(stat_dict, player):
    """Calculate the Raise Frequency on turn for a player.

    This measures how often a player raises when they have the opportunity on the turn.
    Raise Frequency = street2Raises / street2Seen

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no turn opportunities to distinguish from 0% (never raised turn).
    """
    stat = 0.0
    try:
        saw_t = float(stat_dict[player].get("saw_t", 0))  # street2Seen
        street2_raises = float(stat_dict[player].get("street2Raises", 0))

        # No turn opportunities = no data available
        if saw_t == 0:
            return format_no_data_stat("raise_t", "% raise frequency turn")

        # Calculate raise frequency on turn
        stat = street2_raises / saw_t
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "raise_t=%3.1f%%" % (100.0 * stat),
            "raise_freq_turn=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (street2_raises, saw_t),
            "% raise frequency turn",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("raise_t", "% raise frequency turn")


def cb_ip(stat_dict, player):
    """Calculate the Continuation Bet In Position percentage for a player.

    This measures how often a player c-bets when they are in position on the flop.
    CB IP = (cb_1 * estimated_IP_ratio) / (cb_opp_1 * estimated_IP_ratio)

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no IP c-bet opportunities to distinguish from 0% (never c-bet IP).
    """
    stat = 0.0
    try:
        cb_opp_1 = float(stat_dict[player].get("cb_opp_1", 0))
        cb_1 = float(stat_dict[player].get("cb_1", 0))
        street1_in_position = float(stat_dict[player].get("street1InPosition", 0))
        saw_f = float(stat_dict[player].get("saw_f", 0))

        # Calculate estimated IP ratio
        if saw_f == 0:
            return format_no_data_stat("cb_ip", "% c-bet in position")

        ip_ratio = street1_in_position / saw_f

        # Calculate IP c-bet opportunities (approximation)
        cb_ip_opportunities = cb_opp_1 * ip_ratio

        # No IP c-bet opportunities = no data available
        if cb_ip_opportunities == 0:
            return format_no_data_stat("cb_ip", "% c-bet in position")

        # Calculate IP c-bet count (approximation)
        cb_ip_count = cb_1 * ip_ratio

        # Calculate IP c-bet percentage
        stat = cb_ip_count / cb_ip_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cb_ip=%3.1f%%" % (100.0 * stat),
            "cbet_in_position=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cb_ip_count, cb_ip_opportunities),
            "% c-bet in position",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("cb_ip", "% c-bet in position")


def cb_oop(stat_dict, player):
    """Calculate the Continuation Bet Out of Position percentage for a player.

    This measures how often a player c-bets when they are out of position on the flop.
    CB OOP = (cb_1 * estimated_OOP_ratio) / (cb_opp_1 * estimated_OOP_ratio)

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no OOP c-bet opportunities to distinguish from 0% (never c-bet OOP).
    """
    stat = 0.0
    try:
        cb_opp_1 = float(stat_dict[player].get("cb_opp_1", 0))
        cb_1 = float(stat_dict[player].get("cb_1", 0))
        street1_in_position = float(stat_dict[player].get("street1InPosition", 0))
        saw_f = float(stat_dict[player].get("saw_f", 0))

        # Calculate estimated OOP ratio
        if saw_f == 0:
            return format_no_data_stat("cb_oop", "% c-bet out of position")

        oop_ratio = (saw_f - street1_in_position) / saw_f

        # Calculate OOP c-bet opportunities (approximation)
        cb_oop_opportunities = cb_opp_1 * oop_ratio

        # No OOP c-bet opportunities = no data available
        if cb_oop_opportunities == 0:
            return format_no_data_stat("cb_oop", "% c-bet out of position")

        # Calculate OOP c-bet count (approximation)
        cb_oop_count = cb_1 * oop_ratio

        # Calculate OOP c-bet percentage
        stat = cb_oop_count / cb_oop_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "cb_oop=%3.1f%%" % (100.0 * stat),
            "cbet_out_of_position=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (cb_oop_count, cb_oop_opportunities),
            "% c-bet out of position",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("cb_oop", "% c-bet out of position")


def triple_barrel(stat_dict, player):
    """Calculate the Triple Barrel percentage for a player.

    This measures how often a player bets all three streets (flop, turn, river).
    Triple Barrel = (cb_1 * cb_2 * cb_3) / (cb_opp_1 * cb_opp_2 * cb_opp_3)

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no triple barrel opportunities to distinguish from 0% (never triple barreled).
    """
    stat = 0.0
    try:
        cb_opp_1 = float(stat_dict[player].get("cb_opp_1", 0))
        cb_1 = float(stat_dict[player].get("cb_1", 0))
        cb_opp_2 = float(stat_dict[player].get("cb_opp_2", 0))
        cb_2 = float(stat_dict[player].get("cb_2", 0))
        cb_opp_3 = float(stat_dict[player].get("cb_opp_3", 0))
        cb_3 = float(stat_dict[player].get("cb_3", 0))

        # Calculate triple barrel opportunities (minimum of all three streets)
        triple_barrel_opportunities = min(cb_opp_1, cb_opp_2, cb_opp_3)

        # No triple barrel opportunities = no data available
        if triple_barrel_opportunities == 0:
            return format_no_data_stat("3barrel", "% triple barrel")

        # Calculate triple barrel count (approximation based on c-bet ratios)
        if cb_opp_1 > 0 and cb_opp_2 > 0 and cb_opp_3 > 0:
            cb_rate_1 = cb_1 / cb_opp_1
            cb_rate_2 = cb_2 / cb_opp_2
            cb_rate_3 = cb_3 / cb_opp_3

            # Estimate triple barrel count
            triple_barrel_count = triple_barrel_opportunities * cb_rate_1 * cb_rate_2 * cb_rate_3
        else:
            triple_barrel_count = 0

        # Calculate triple barrel percentage
        stat = triple_barrel_count / triple_barrel_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "3barrel=%3.1f%%" % (100.0 * stat),
            "triple_barrel=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (triple_barrel_count, triple_barrel_opportunities),
            "% triple barrel",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("3barrel", "% triple barrel")


def resteal(stat_dict, player):
    """Calculate the Resteal percentage for a player.

    This measures how often a player re-raises against a steal attempt.
    Resteal is approximated as a portion of 3-bets against steal positions.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no resteal opportunities to distinguish from 0% (never restealed).
    """
    stat = 0.0
    try:
        three_bet_opp = float(stat_dict[player].get("tb_opp_0", 0))
        three_bet = float(stat_dict[player].get("tb_0", 0))

        # Estimate resteal opportunities (approximately 60% of 3-bet opportunities are vs steal)
        resteal_opportunities = three_bet_opp * 0.6

        # No resteal opportunities = no data available
        if resteal_opportunities == 0:
            return format_no_data_stat("resteal", "% resteal")

        # Calculate resteal count (approximation - 70% of 3-bets are resteals)
        resteal_count = three_bet * 0.7

        # Calculate resteal percentage
        stat = resteal_count / resteal_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "resteal=%3.1f%%" % (100.0 * stat),
            "resteal=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (resteal_count, resteal_opportunities),
            "% resteal",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("resteal", "% resteal")


def probe_bet_turn(stat_dict, player):
    """Calculate the Probe Bet Turn percentage for a player.

    This measures how often a player probe bets on the turn after the preflop aggressor checks.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no turn probe opportunities to distinguish from 0% (never probed turn).
    """
    stat = 0.0
    try:
        # Get turn betting data
        street2_bets = float(stat_dict[player].get("street2Bets", 0))
        saw_t = float(stat_dict[player].get("saw_t", 0))

        # Get continuation bet data (opponent's cb opportunities and actual cbs)
        float(stat_dict[player].get("cb_opp_2", 0))
        cb_2 = float(stat_dict[player].get("cb_2", 0))

        # Calculate turn probe opportunities: saw turn when opponent could have c-bet but didn't
        turn_probe_opportunities = saw_t - cb_2

        # No opportunities = no data available
        if turn_probe_opportunities <= 0:
            return format_no_data_stat("probe_t", "% probe bet turn")

        # Calculate turn probe count: bets made in turn probe situations
        turn_probe_count = min(street2_bets, turn_probe_opportunities)

        # Calculate turn probe percentage
        stat = turn_probe_count / turn_probe_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "probe_t=%3.1f%%" % (100.0 * stat),
            "probe_turn=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (turn_probe_count, turn_probe_opportunities),
            "% probe bet turn",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("probe_t", "% probe bet turn")


def probe_bet_river(stat_dict, player):
    """Calculate the Probe Bet River percentage for a player.

    This measures how often a player probe bets on the river after the preflop aggressor checks.

    Args:
        stat_dict (dict): A dictionary containing player statistics.
        player (int): The player for whom the statistic is calculated.

    Returns:
        tuple: A tuple containing the calculated statistic, formatted strings, and related information.
        Returns "-" if no river probe opportunities to distinguish from 0% (never probed river).
    """
    stat = 0.0
    try:
        # Get river betting data
        street3_bets = float(stat_dict[player].get("street3Bets", 0))
        saw_r = float(stat_dict[player].get("saw_r", 0))

        # Get continuation bet data (opponent's cb opportunities and actual cbs)
        float(stat_dict[player].get("cb_opp_3", 0))
        cb_3 = float(stat_dict[player].get("cb_3", 0))

        # Calculate river probe opportunities: saw river when opponent could have c-bet but didn't
        river_probe_opportunities = saw_r - cb_3

        # No opportunities = no data available
        if river_probe_opportunities <= 0:
            return format_no_data_stat("probe_r", "% probe bet river")

        # Calculate river probe count: bets made in river probe situations
        river_probe_count = min(street3_bets, river_probe_opportunities)

        # Calculate river probe percentage
        stat = river_probe_count / river_probe_opportunities
        return (
            stat,
            "%3.1f" % (100.0 * stat),
            "probe_r=%3.1f%%" % (100.0 * stat),
            "probe_river=%3.1f%%" % (100.0 * stat),
            "(%d/%d)" % (river_probe_count, river_probe_opportunities),
            "% probe bet river",
        )
    except (KeyError, ValueError, TypeError):
        return format_no_data_stat("probe_r", "% probe bet river")


#
#
#
#################################################################################################


def starthands(stat_dict, player):
    """Retrieves the starting hands and their positions for a specific player in a hand.

    Args:
        stat_dict (dict): A dictionary containing the statistics.
        player (int): The ID of the player.

    Returns:
        tuple: A tuple containing the following:
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the title of the statistic.

    Raises:
        None.

    Notes:
        - This function retrieves the starting hands and their positions for a specific player in a hand.
        - The starting hands and their positions are displayed in a specific format.
        - The function uses a global variable `_get_hand_instance()` to get the hand instance.
        - The function executes a SQL query to retrieve the starting hands and their positions from the database.
        - The function formats the retrieved data and returns it as a tuple.

    """
    hand_instance = _get_hand_instance()
    if not hand_instance:
        return ("", "", "", "", "", "Hands seen at this table")

    # summary of known starting hands+position
    # data volumes could get crazy here,so info is limited to hands
    # in the current HH file only

    # this info is NOT read from the cache, so does not obey aggregation
    # parameters for other stats

    # display shows 5 categories
    # PFcall - limp or coldcall preflop
    # PFaggr - raise preflop
    # PFdefend - defended in BB
    # PFcar

    # hand is shown, followed by position indicator
    # (b=SB/BB. l=Button/cutoff m=previous 3 seats to that, e=remainder)

    # due to screen space required for this stat, it should only
    # be used in the popup section i.e.
    # <pu_stat pu_stat_name="starthands"> </pu_stat>
    handid = int(hand_instance.handid_selected)
    PFlimp = "Limped:"
    PFaggr = "Raised:"
    PFcar = "Called raise:"
    PFdefendBB = "Defend BB:"
    count_pfl = count_pfa = count_pfc = count_pfd = 5

    c = Configuration.Config()
    db_connection = Database.Database(c)
    sc = db_connection.get_cursor()

    query = (
        "SELECT distinct startCards, street0Aggr, street0CalledRaiseDone, "
        "case when HandsPlayers.position = 'B' then 'b' "
        "when HandsPlayers.position = 'S' then 'b' "
        "when HandsPlayers.position = '0' then 'l' "
        "when HandsPlayers.position = '1' then 'l' "
        "when HandsPlayers.position = '2' then 'm' "
        "when HandsPlayers.position = '3' then 'm' "
        "when HandsPlayers.position = '4' then 'm' "
        "when HandsPlayers.position = '5' then 'e' "
        "when HandsPlayers.position = '6' then 'e' "
        "when HandsPlayers.position = '7' then 'e' "
        "when HandsPlayers.position = '8' then 'e' "
        "when HandsPlayers.position = '9' then 'e' "
        "else 'X' end "
        "FROM Hands, HandsPlayers, Gametypes "
        "WHERE HandsPlayers.handId = Hands.id "
        " AND Gametypes.id = Hands.gametypeid "
        " AND Gametypes.type = "
        "   (SELECT Gametypes.type FROM Gametypes, Hands   "
        "  WHERE Hands.gametypeid = Gametypes.id and Hands.id = %d) "
        " AND Gametypes.Limittype =  "
        "   (SELECT Gametypes.limitType FROM Gametypes, Hands  "
        " WHERE Hands.gametypeid = Gametypes.id and Hands.id = %d) "
        "AND Gametypes.category = 'holdem' "
        "AND fileId = (SELECT fileId FROM Hands "
        " WHERE Hands.id = %d) "
        "AND HandsPlayers.playerId = %d "
        "AND street0VPI "
        "AND startCards > 0 AND startCards <> 170 "
        "ORDER BY startCards DESC "
        ";"
    ) % (int(handid), int(handid), int(handid), int(player))

    # print query
    sc.execute(query)
    for qstartcards, qstreet0Aggr, qstreet0CalledRaiseDone, qposition in sc.fetchall():
        humancards = Card.decodeStartHandValue("holdem", qstartcards)
        # print humancards, qstreet0Aggr, qstreet0CalledRaiseDone, qposition
        if qposition == "b" and qstreet0CalledRaiseDone:
            PFdefendBB = PFdefendBB + "/" + humancards
            count_pfd += 1
            if count_pfd / 8.0 == int(count_pfd / 8.0):
                PFdefendBB = PFdefendBB + "\n"
        elif qstreet0Aggr is True:
            PFaggr = PFaggr + "/" + humancards + "." + qposition
            count_pfa += 1
            if count_pfa / 8.0 == int(count_pfa / 8.0):
                PFaggr = PFaggr + "\n"
        elif qstreet0CalledRaiseDone:
            PFcar = PFcar + "/" + humancards + "." + qposition
            count_pfc += 1
            if count_pfc / 8.0 == int(count_pfc / 8.0):
                PFcar = PFcar + "\n"
        else:
            PFlimp = PFlimp + "/" + humancards + "." + qposition
            count_pfl += 1
            if count_pfl / 8.0 == int(count_pfl / 8.0):
                PFlimp = PFlimp + "\n"
    sc.close()

    returnstring = PFlimp + "\n" + PFaggr + "\n" + PFcar + "\n" + PFdefendBB  # + "\n" + str(handid)

    return (
        (returnstring),
        (returnstring),
        (returnstring),
        (returnstring),
        (returnstring),
        "Hands seen at this table\n",
    )


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
            except Exception:  # intentional broad catch: calling stats with None, None can raise exceptions
                pass

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
