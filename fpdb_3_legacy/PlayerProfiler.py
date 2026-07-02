"""Player Profiler.

Classifies poker players based on their statistics.
"""

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("player_profiler")


class PlayerProfile:
    """Player profile categories."""

    FISH = "fish"
    REG = "reg"
    NIT = "nit"
    MANIAC = "maniac"
    LAG = "lag"
    TAG = "tag"
    CALLING_STATION = "calling_station"
    UNKNOWN = "unknown"


# Profile icons
PROFILE_ICONS = {
    PlayerProfile.FISH: "🐟",
    PlayerProfile.CALLING_STATION: "📞",
    PlayerProfile.MANIAC: "🌪️",
    PlayerProfile.LAG: "⚡",
    PlayerProfile.REG: "💼",
    PlayerProfile.TAG: "🎯",
    PlayerProfile.NIT: "🐌",
    PlayerProfile.UNKNOWN: "❓",
}

# Profile colors
PROFILE_COLORS = {
    PlayerProfile.FISH: "#00FF00",  # Green
    PlayerProfile.CALLING_STATION: "#00FFAA",  # Bright Green
    PlayerProfile.MANIAC: "#FF00FF",  # Purple
    PlayerProfile.LAG: "#FFAA00",  # Orange
    PlayerProfile.REG: "#FF0000",  # Red
    PlayerProfile.TAG: "#AA0000",  # Dark Red
    PlayerProfile.NIT: "#0000FF",  # Blue
    PlayerProfile.UNKNOWN: "#888888",  # Gray
}


def classify_player(stat_dict, player_id, min_hands=10):
    """Classifies a player based on their statistics.

    Args:
        stat_dict (dict): The statistics dictionary.
        player_id (int): The player ID.
        min_hands (int): The minimum number of hands required to classify.

    Returns:
        tuple: (profile_type, emoji_icon, hex_color)
    """
    try:
        player_stats = stat_dict[player_id]
    except KeyError:
        return (
            PlayerProfile.UNKNOWN,
            PROFILE_ICONS[PlayerProfile.UNKNOWN],
            PROFILE_COLORS[PlayerProfile.UNKNOWN],
        )

    hands = int(player_stats.get("n", 0))
    if hands < min_hands:
        return (
            PlayerProfile.UNKNOWN,
            PROFILE_ICONS[PlayerProfile.UNKNOWN],
            PROFILE_COLORS[PlayerProfile.UNKNOWN],
        )

    # Calculate VPIP
    vpip_opp = float(player_stats.get("vpip_opp", 0))
    vpip_val = float(player_stats.get("vpip", 0))
    vpip = 100.0 * vpip_val / vpip_opp if vpip_opp > 0 else 0.0

    # Calculate PFR
    pfr_opp = float(player_stats.get("pfr_opp", 0))
    pfr_val = float(player_stats.get("pfr", 0))
    pfr = 100.0 * pfr_val / pfr_opp if pfr_opp > 0 else 0.0

    vpip_pfr_gap = vpip - pfr

    # Calculate 3-bet
    tb_opp = float(player_stats.get("TB_opp_0", 0))
    tb_val = float(player_stats.get("TB_0", 0))
    three_bet = 100.0 * tb_val / tb_opp if tb_opp > 0 else 0.0

    # Calculate Aggression % and Factor
    bet_raise = (
        float(player_stats.get("aggr_1", 0))
        + float(player_stats.get("aggr_2", 0))
        + float(player_stats.get("aggr_3", 0))
        + float(player_stats.get("aggr_4", 0))
    )
    post_call = (
        float(player_stats.get("call_1", 0))
        + float(player_stats.get("call_2", 0))
        + float(player_stats.get("call_3", 0))
        + float(player_stats.get("call_4", 0))
    )

    agg_pct = 100.0 * bet_raise / (bet_raise + post_call) if (post_call + bet_raise) > 0 else 0.0
    agg_factor = bet_raise / post_call if post_call > 0 else bet_raise

    # Calculate Went to Showdown
    sd = float(player_stats.get("sd", 0))
    saw_f = float(player_stats.get("saw_f", 0))
    wtsd = 100.0 * sd / saw_f if saw_f > 0 else 0.0

    # 1. NIT: Very tight (VPIP < 15, PFR < 12)
    if vpip < 15 and pfr < 12:
        profile = PlayerProfile.NIT

    # 2. CALLING STATION: Passive caller
    elif vpip > 30 and vpip_pfr_gap > 15 and agg_pct < 25 and wtsd > 33:
        profile = PlayerProfile.CALLING_STATION

    # 3. FISH: Loose-passive (VPIP > 35, gap > 20)
    elif vpip > 35 and vpip_pfr_gap > 20:
        profile = PlayerProfile.FISH

    # 4. MANIAC: Loose-aggressive (wild)
    elif vpip > 40 and pfr > 30 and (agg_pct > 60 or agg_factor > 3.0):
        profile = PlayerProfile.MANIAC

    # 5. LAG: Loose-aggressive (controlled)
    elif vpip > 28 and pfr > 22 and vpip_pfr_gap < 12 and agg_pct > 45:
        profile = PlayerProfile.LAG

    # 6. REG: Tight-aggressive regular
    elif 21 <= vpip <= 28 and 18 <= pfr <= 24 and vpip_pfr_gap < 10 and agg_pct > 40:
        profile = PlayerProfile.REG

    # 7. TAG: Tight-aggressive (standard)
    elif 15 <= vpip <= 25 and 12 <= pfr <= 20 and agg_pct > 35:
        profile = PlayerProfile.TAG

    # Default to UNKNOWN
    else:
        profile = PlayerProfile.UNKNOWN

    return profile, PROFILE_ICONS[profile], PROFILE_COLORS[profile]
