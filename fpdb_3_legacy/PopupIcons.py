"""PopupIcons.py.
from __future__ import annotations
Icon mapping system for modern popup windows.
"""

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("popup_icons")


class IconProvider:
    """Base class for icon providers."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.icons: dict[str, str] = {}

    def get_icon(self, stat_name: str) -> str:
        """Get icon for a specific stat."""
        return self.icons.get(stat_name, "📊")  # Default icon

    def get_section_icon(self, section_name: str) -> str:
        """Get icon for a section."""
        section_icons = {
            "player_info": "👤",
            "preflop": "🎯",
            "flop": "🃏",
            "turn": "🔄",
            "river": "🏁",
            "positional": "📍",
            "aggression": "⚔️",
            "general": "📊",
            "hands": "🤝",
            "profit": "💰",
            "steal": "🥷",
            "continuation": "➡️",
            "fold": "🛡️",
        }
        return section_icons.get(section_name, "📂")


class EmojiIconProvider(IconProvider):
    """Emoji-based icon provider."""

    def __init__(self) -> None:
        super().__init__("emoji")

        # Main stat icons
        self.icons = {
            # Player info
            "playername": "👤",
            "player_note": "📝",
            "n": "🔢",
            # Preflop stats
            "vpip": "💰",  # Voluntarily Put money In Pot
            "pfr": "📈",  # Preflop Raise
            "three_B": "⬆️",  # 3-Bet
            "four_B": "⏫",  # 4-Bet
            "f_3bet": "🛡️",
            "fold_vs_4bet": "🛡️",
            "squeeze": "🤏",
            "limp": "🚶",  # Limp
            "cold_call": "❄️",  # Cold Call
            "rfi": "🚀",  # Raise First In
            # Position stats
            "rfi_early_position": "🌅",
            "rfi_middle_position": "☀️",
            "rfi_late_position": "🌆",
            "sb_steal": "🥷",
            "bb_defend": "🛡️",
            # Flop stats
            "cb1": "➡️",  # Continuation Bet Flop
            "f_cb1": "🛡️",  # Fold to CB Flop
            "raise_cb1": "⬆️",  # Raise CB Flop
            "check_call_flop": "✅",
            "donk_bet": "🎲",
            "float_bet": "🎈",
            "dbr1": "🎲",
            "f_dbr1": "🛡️",
            "cr1": "↗️",
            "cb_ip": "➡️",
            "cb_oop": "↪️",
            # Turn stats
            "cb2": "➡️",  # Continuation Bet Turn
            "f_cb2": "🛡️",  # Fold to CB Turn
            "dbr2": "🎲",
            "f_dbr2": "🛡️",
            "cr2": "↗️",
            "turn_aggression": "⚔️",
            "turn_check_call": "✅",
            # River stats
            "cb3": "➡️",  # Continuation Bet River
            "f_cb3": "🛡️",  # Fold to CB River
            "dbr3": "🎲",
            "f_dbr3": "🛡️",
            "cr3": "↗️",
            "river_call_efficiency": "☎️",
            "river_aggression": "⚔️",
            "value_bet": "💎",
            "bluff": "🎭",
            # Steal & positional
            "steal": "🥷",  # Steal attempt
            "f_steal": "🛡️",  # Fold to steal
            "call_vs_steal": "☎️",
            "three_B_vs_steal": "⬆️",
            "resteal": "🔄",
            # Aggression
            "agg_fact": "⚔️",  # Aggression factor
            "agg_freq": "🎯",  # Aggression frequency
            "agg_pct": "📊",  # Aggression percentage
            "bet_freq": "💸",
            "raise_freq": "📈",
            # Showdown
            "wtsd": "👁️",  # Went to showdown
            "wmsd": "🏆",  # Won money at showdown
            "wwsf": "✨",
            "WMsF": "💵",
            "show_aggr": "💪",  # Showdown aggression
            # General stats
            "hands": "🤝",  # Total hands
            "totalprofit": "💰",  # Total profit
            "profit100": "📊",  # BB/100
            "vpip_pfr_ratio": "⚖️",
            "gap": "📏",  # Gap concept
            # Tournament specific
            "m_ratio": "📊",  # M-ratio
            "push_fold": "⚡",  # Push/fold
            "steal_success": "✅",
            # Advanced stats
            "fold_3B": "🛡️",  # Fold to 3-bet
            "fold_4B": "🛡️",  # Fold to 4-bet
            "isolation": "🎯",  # Isolation
            "limped_pot": "🚶",  # Limped pot
            "multiway": "👥",  # Multiway pot
            # Street-specific
            "saw_f": "👁️",  # Saw flop
            "saw_t": "👁️",  # Saw turn
            "saw_r": "👁️",  # Saw river
            "f_freq1": "🛡️",  # Fold frequency flop
            "f_freq2": "🛡️",  # Fold frequency turn
            "f_freq3": "🛡️",  # Fold frequency river
            # Betting patterns
            "check_raise": "🔄",  # Check-raise
            "donk": "🎲",  # Donk bet
            "probe": "🔍",  # Probe bet
            "blocking": "🚧",  # Blocking bet
            # Special situations
            "blind_def": "🛡️",  # Blind defense
            "blind_att": "⚔️",  # Blind attack
            "heads_up": "👥",  # Heads up
            "vs_missed_cb": "❌",  # Vs missed CB
        }


class UnicodeIconProvider(IconProvider):
    """Unicode symbol-based icon provider."""

    def __init__(self) -> None:
        super().__init__("unicode")

        self.icons = {
            # Player info
            "playername": "◆",
            "player_note": "✎",
            "n": "#",
            # Preflop stats
            "vpip": "♦",
            "pfr": "▲",
            "three_B": "↑",
            "four_B": "⇑",
            "limp": "○",
            "cold_call": "◯",
            # Flop stats
            "cb1": "→",
            "f_cb1": "⌐",
            "raise_cb1": "↗",
            # Turn stats
            "cb2": "⇒",
            "f_cb2": "⌐⌐",
            # River stats
            "cb3": "⟹",
            "f_cb3": "⌐⌐⌐",
            # Steal & positional
            "steal": "※",
            "f_steal": "⌐",
            "resteal": "↻",
            # Aggression
            "agg_fact": "⚡",
            "agg_freq": "◈",
            # General
            "hands": "∑",
            "totalprofit": "$",
            "profit100": "¢",
            # Advanced
            "fold_3B": "⌐",
            "squeeze": "⊂⊃",
            "wtsd": "◐",
            "wmsd": "●",
        }


class TextIconProvider(IconProvider):
    """Text-based icon provider for compatibility."""

    def __init__(self) -> None:
        super().__init__("text")

        self.icons = {
            # All stats get simple text labels
            "playername": "[P]",
            "player_note": "[N]",
            "vpip": "[V]",
            "pfr": "[R]",
            "three_B": "[3B]",
            "cb1": "[CB]",
            "f_cb1": "[F]",
            "steal": "[ST]",
            "agg_fact": "[AF]",
            "hands": "[H]",
            "totalprofit": "[$]",
            "profit100": "[BB]",
        }

        # For any unknown stat, use first 2-3 letters
        def get_icon(self, stat_name: str) -> str:
            if stat_name in self.icons:
                return self.icons[stat_name]
            return f"[{stat_name[:3].upper()}]"


# Icon provider registry
AVAILABLE_PROVIDERS = {
    "emoji": EmojiIconProvider,
    "unicode": UnicodeIconProvider,
    "text": TextIconProvider,
}


def get_icon_provider(provider_name: str = "emoji") -> IconProvider:
    """Get an icon provider instance by name."""
    provider_class = AVAILABLE_PROVIDERS.get(provider_name, EmojiIconProvider)
    return provider_class()


def get_stat_category(stat_name: str) -> str:
    """Categorize a stat into logical groups."""
    preflop_stats = [
        "vpip", "pfr", "vpip_pfr_ratio", "three_B", "four_B", "f_3bet", "f_4bet",
        "fold_vs_4bet", "limp", "open_limp", "cold_call", "rfi", "rfi_total",
        "rfi_early_position", "rfi_middle_position", "rfi_late_position",
        "squeeze", "fold_to_squeeze", "fold_3B", "fold_4B",
        "face_raise_preflop", "face_limpers", "straddle",
        "p_2bet_facing", "p_3bet_facing", "p_4bet_facing", "p_raise_made",
        "p_raise_facing", "p_raise_made_2", "p_5bet_facing",
    ]
    flop_stats = [
        "cb1", "cb_ip", "cb_oop", "f_cb1", "raise_cb1", "donk_bet", "dbr1", "f_dbr1",
        "cr1", "float_bet", "check_call_flop", "check_raise_frequency",
        "bet_frequency_flop", "raise_frequency_flop", "avg_bet_size_flop",
        "four_B_flop", "open_flop", "face_raise_flop", "first_raise_flop", "fold_flop", "f_bet_facing", "f_bet_made", "f_spr", "f_raise_made",
        "f_2bet_facing", "f_3bet_facing", "f_4bet_facing", "f_raise_facing", "f_raise_made_2",
    ]
    turn_stats = [
        "cb2", "f_cb2", "dbr2", "f_dbr2", "cr2", "probe_bet_turn",
        "bet_frequency_turn", "raise_frequency_turn", "avg_bet_size_turn",
        "turn_aggression", "turn_check_call",
        "four_B_turn", "open_turn", "float_turn", "face_raise_turn", "first_raise_turn", "fold_turn", "t_bet_facing", "t_bet_made", "t_spr", "t_raise_made",
        "t_2bet_facing", "t_3bet_facing", "t_4bet_facing", "t_raise_facing", "t_raise_made_2",
    ]
    river_stats = [
        "cb3", "f_cb3", "dbr3", "f_dbr3", "cr3", "probe_bet_river",
        "avg_bet_size_river", "river_call_efficiency", "river_aggression", "value_bet", "bluff",
        "four_B_river", "open_river", "float_river", "face_raise_river", "first_raise_river", "fold_river", "r_bet_facing", "r_bet_made", "r_spr", "r_raise_made",
        "r_2bet_facing", "r_3bet_facing", "r_4bet_facing", "r_raise_facing", "r_raise_made_2",
    ]
    steal_stats = [
        "steal", "s_steal", "f_steal", "f_SB_steal", "f_BB_steal",
        "call_vs_steal", "three_B_vs_steal", "three_bet_vs_steal", "resteal",
    ]
    aggression_stats = [
        "agg_fact", "agg_fact_pct", "agg_freq", "agg_pct", "a_freq1", "a_freq2",
        "a_freq3", "a_freq4", "a_freq_123", "bet_freq", "raise_freq",
        "triple_barrel", "overbet_frequency",
    ]
    general_stats = ["hands", "saw_f", "totalprofit", "profit100", "bbper100", "BBper100",
                     "wtsd", "wmsd", "wwsf", "WMsF", "sd_winrate", "non_sd_winrate", "fold_to_allin",
                     "amt_blind", "amt_bet_p", "amt_bet_f", "amt_bet_t", "amt_bet_r", "amt_bet_ttl"]
    player_stats = ["playername", "player_note", "n"]

    if stat_name in player_stats:
        return "player_info"
    if stat_name in preflop_stats:
        return "preflop"
    if stat_name in flop_stats:
        return "flop"
    if stat_name in turn_stats:
        return "turn"
    if stat_name in river_stats:
        return "river"
    if stat_name in steal_stats:
        return "steal"
    if stat_name in aggression_stats:
        return "aggression"
    if stat_name in general_stats:
        return "general"
    return "general"  # Default category
