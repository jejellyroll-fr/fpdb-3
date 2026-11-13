"""Plain-language text of the HUD Stats Guide (issue #751).

Two things live here, both written from the code that fills each column
(``DerivedStats`` and its ``derived_stats_*`` mixins), not from stat names:

* :func:`phrase` turns a HUD stat-dict key into the counter it holds
  ("Number of times the player saw the flop"), so a formula can be read the way
  PokerTracker 4 shows it: ``Number of ... / Number of ...``.
* :func:`describe` gives each stat a full title and a detailed description.

Street numbers follow the database: street 1 is the flop (4th street in stud),
2 the turn (5th), 3 the river (6th), 4 the 7th street of stud.
"""

from __future__ import annotations

import re

STREETS = {
    "1": "flop",
    "2": "turn",
    "3": "river",
    "4": "7th street",
    "f": "flop",
    "t": "turn",
    "r": "river",
    "p": "preflop",
}
STREET_WORDS = {"flop": "1", "turn": "2", "river": "3"}
POSITIONS = {
    "bb": "the big blind",
    "sb": "the small blind",
    "btn": "the button",
    "co": "the cutoff",
    "mp": "middle position",
    "ep": "early position",
    "lp": "the cutoff (late position)",
}
SITUATIONS = {
    "3bet": "a 3-bet",
    "4bet": "a 4-bet",
    "squeeze": "a squeeze",
    "cbet": "a continuation bet",
    "donk": "a donk bet (a bet into the preflop raiser)",
    "float": "a bet after having called the previous street's bet in position (a float spot)",
}

# Keys whose meaning is not a pattern. Each phrase reads after "Number of".
_FIXED: dict[str, str] = {
    "n": "hands played",
    "vpip": "hands where the player voluntarily put money in the pot preflop (call, raise or complete; posting a blind does not count)",
    "vpip_opp": "hands where the player had the chance to put money in voluntarily (excludes walks and blinds folded or all-in without a decision)",
    "pfr": "hands where the player raised preflop",
    "pfr_opp": "hands where the player had the chance to raise preflop",
    "car_0": "calls of a preflop raise (each call counts; after a call, counting resumes at the next raise)",
    "car_opp_0": "preflop actions the player took while facing a raise (fold, call or raise; several per hand are possible)",
    "tb_0": "preflop 3-bets made",
    "tb_opp_0": "times the player faced a single preflop raise with the chance to 3-bet",
    "fb_0": "preflop 4-bets made by the original raiser",
    "fb_opp_0": "times the original raiser faced a 3-bet with the chance to 4-bet",
    "cfb_0": "cold 4-bets (a 4-bet by a player who had not raised before)",
    "cfb_opp_0": "times a player who had not raised faced a 3-bet with the chance to 4-bet",
    "f3b_0": "times the original raiser folded to a 3-bet",
    "f3b_opp_0": "times the original raiser faced a 3-bet",
    "f4b_0": "times a player other than the original raiser folded facing a 4-bet",
    "f4b_opp_0": "times a player other than the original raiser acted facing a 4-bet",
    "sqz_0": "squeezes (a 3-bet after a raise and at least one call)",
    "sqz_opp_0": "times the player faced a raise and at least one call with the chance to 3-bet",
    "sqzdef_fold": "times the player folded to a squeeze",
    "sqzdef_opp": "times the player faced a squeeze after opening or calling",
    "steal": "steal attempts (first raise from the cutoff, button or small blind into an unopened pot)",
    "steal_opp": "times the player was in the cutoff, button or small blind with the pot unopened",
    "suc_st": "steal attempts that won the blinds uncontested",
    "rts": "times the player re-raised a steal attempt from the blinds",
    "rts_opp": "times the player was in the blinds facing a steal attempt",
    "sbstolen": "times the player was in the small blind facing a steal attempt",
    "sbnotdef": "times the player folded the small blind to a steal attempt",
    "bbstolen": "times the player was in the big blind facing a steal attempt",
    "bbnotdef": "times the player folded the big blind to a steal attempt",
    "open_limp": "open limps (first to enter the pot, by calling)",
    "open_limp_opp": "times the pot was unopened when the player acted",
    "face_limpers": "limpers faced, summed over hands (only counted while the pot is unraised)",
    "p_face_raise": "hands where the player acted preflop after a raise",
    "straddle_done": "straddles posted",
    "gp_open_opp": "times the player could open an unopened pot",
    "gp_2x": "open raises of less than 40% of the stack",
    "gp_os": "open shoves (open raises of 40% of the stack or more)",
    "gp_limp": "open limps",
    "rfi_0": "raises first in (the first raise, into a pot nobody had entered)",
    "rfi_opp_0": "times the player acted while the pot was still unopened",
    "saw_f": "hands where the player saw the flop",
    "street1inposition": "flops played in position",
    "sd": "hands where the player went to showdown",
    "wmsd": "showdowns where the player won money (any share of a pot)",
    "w_w_s_1": "hands where the player saw the flop and won money (any share of a pot, with or without showdown)",
    "net": "sum: the player's total profit, in cents",
    "bigblind": "sum: big blinds in play, summed over hands (big blind × hands)",
    "faced_allin": "hands where the player faced an all-in bet or raise with a decision to make (first such spot only)",
    "fold_allin": "times the player folded to that all-in",
    "float_turn_chance": "times the player had called the flop aggressor's bet, saw the turn and acted after that aggressor checked it",
    "float_turn_done": "times the player then bet or raised the turn (float)",
    "float_river_chance": "times the player had called the turn aggressor's bet, saw the river and acted after that aggressor checked it",
    "float_river_done": "times the player then bet or raised the river (float)",
    "amt_blind": "sum: blinds and antes posted, in cents",
    "amt_bet_p": "sum: chips put in preflop, blinds included, in cents",
    "amt_bet_f": "sum: chips put in on the flop, in cents",
    "amt_bet_t": "sum: chips put in on the turn, in cents",
    "amt_bet_r": "sum: chips put in on the river, in cents",
    "amt_bet_ttl": "sum: chips put in over the whole hand, in cents",
    "aof_obs": "observable all-ins (decision all-in, hole cards and flop captured)",
    "aof_known": "all-ins whose callers' cards were all captured",
    "aof_known_equity_ppm": "sum: flop equity against the actual callers in parts per million",
    "aof_known_ev_bb_ppm": "sum: EV against the actual callers in millionths of a big blind",
    "aof_range": "all-ins with a population-range equity",
    "aof_range_equity_ppm": "sum: flop equity against the population range in parts per million",
    "aof_decision_ev": "all-in decisions with a modelled EV (weak, strong or uncertain)",
    "aof_decision_ev_bb_ppm": "sum: modelled decision EV in millionths of a big blind",
    "aof_weak": "all-ins whose modelled EV is negative even at the upper 95% bound",
    "aof_splash_seen": "splash-pot hands played",
    "aof_splash_hit": "splash-pot hands where the player took a share of the splash",
    "aof_splash_cents": "sum: splash money collected, in cents",
    "aof_no_made": "observable all-ins with no made hand",
    "aof_made": "observable all-ins with a made hand",
    "aof_nfd": "observable all-ins with the nut flush draw",
    "aof_non_nfd": "observable all-ins with a non-nut flush draw",
    "aof_wrap9": "observable all-ins with at least nine straight outs",
    "aof_big_wrap13": "observable all-ins with at least thirteen straight outs",
    "aof_pair": "observable all-ins with one pair",
    "aof_two_pair": "observable all-ins with two pair",
    "aof_trips": "observable all-ins with trips",
    "aof_straight": "observable all-ins with a straight",
    "aof_flush": "observable all-ins with a flush",
    "aof_full_house": "observable all-ins with a full house",
    "aof_quads": "observable all-ins with quads",
    "aof_straight_flush": "observable all-ins with a straight flush",
}

_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"saw_([1-4])$", "hands where the player saw the {s1}"),
    (r"aggr_([1-4])$", "hands where the player bet or raised on the {s1}"),
    (r"bet_([1-3])$", "bets made on the {s1} (every bet counts)"),
    (r"raise_([1-3])$", "raises made on the {s1} (every raise counts, a re-raise too)"),
    (r"call_([1-4])$", "calls made on the {s1} (every call counts)"),
    (r"cb_([1-4])$", "continuation bets on the {s1} (the last preflop raiser bet or raised on the street)"),
    (r"cb_opp_([1-4])$", "{s1} continuation-bet opportunities (the last preflop raiser, not folded yet)"),
    (r"f_cb_([1-4])$", "folds to a {s1} continuation bet"),
    (r"f_cb_opp_([1-4])$", "times the player acted after a {s1} continuation bet"),
    (r"cr_([1-4])$", "check-raises on the {s1}"),
    (r"ccr_opp_([1-4])$", "times the player checked on the {s1} and acted again on that street"),
    (r"was_raised_([1-4])$", "times the player acted on the {s1} after someone else bet or raised"),
    (r"f_freq_([1-4])$", "times the player folded on the {s1} after someone else bet or raised"),
    (r"(fl|tn|rv)3b$", "{s1} 3-bets (re-raise of a bet and a raise)"),
    (r"(fl|tn|rv)3b_opp$", "times the player faced a bet and a raise on the {s1}"),
    (r"(fl|tn|rv)4b$", "{s1} 4-bets"),
    (r"(fl|tn|rv)4b_opp$", "times the player faced a {s1} 3-bet with the chance to 4-bet"),
    (r"f([ftr])3b$", "times the player folded to a {s1} 3-bet after raising"),
    (r"f([ftr])3b_opp$", "times the player raised the {s1} and faced a 3-bet"),
    (r"(fl|tn|rv)open$", "times the player made the first bet on the {s1}"),
    (r"(fl|tn|rv)open_opp$", "times the player acted on the {s1} before anyone had bet"),
    (r"([ftr])_first_raise$", "times the player made the first raise on the {s1}"),
    (r"([ftr])_face_raise$", "{s1}s where the player acted after a raise"),
    (r"([ftr])_fold$", "{s1}s the player folded"),
    (r"cnt_([pftr])_face_(\w+)$", "times the player faced {sit} on the {s1}"),
    (r"cnt_([pftr])_call_(\w+)$", "times the player called {sit} on the {s1}"),
    (r"cnt_([pftr])_raise_(\w+)$", "times the player raised {sit} on the {s1}"),
    (r"([pftr])_(bet|raise|2bet|3bet|4bet|5bet)_facing_cnt$", "{s1} {what} faced with a recorded price"),
    (
        r"([pftr])_(bet|raise|2bet|3bet|4bet|5bet)_facing_bp$",
        "sum: prices of the {s1} {what} faced: amount to call / pot at the decision (the pot already holds the bet), in basis points",
    ),
    (r"([pftr])_bet_made_cnt$", "first bets made on the {s1}"),
    (r"([pftr])_bet_made_bp$", "sum: sizes of those bets: bet / pot before the bet, in basis points"),
    (r"([pftr])_raise_made_cnt$", "first raises made on the {s1}"),
    (r"([pftr])_raise_made_bp$", "sum: sizes of those raises: raise-to amount / pot before the raise, in basis points"),
    (r"([pftr])_raise_made_2_cnt$", "second raises made by the player on the {s1}"),
    (
        r"([pftr])_raise_made_2_bp$",
        "sum: sizes of those second raises: raise-to amount / pot before the raise, in basis points",
    ),
    (r"([ftr])_spr_cnt$", "{s1}s with a recorded stack-to-pot ratio"),
    (r"([ftr])_spr_val$", "sum: stack-to-pot ratios entering the {s1} (effective stack / pot), stored ×100"),
    (r"tb_opp_(\w+)$", "times the player faced a single preflop raise from {pos} with the chance to 3-bet"),
    (r"tb_(\w+)$", "preflop 3-bets made from {pos}"),
    (r"fb_opp_(\w+)$", "times the player, in {pos}, faced a 3-bet with the chance to 4-bet"),
    (r"fb_(\w+)$", "preflop 4-bets made from {pos}"),
    (r"sqz_opp_(\w+)$", "squeeze opportunities in {pos}"),
    (r"sqz_(\w+)$", "squeezes made from {pos}"),
    (r"rfi_opp_(\w+)$", "times the player was first to act into an unopened pot in {pos}"),
    (r"rfi_(\w+)$", "raises first in from {pos}"),
)

_WHAT = {
    "bet": "bets",
    "raise": "raises (most recent level)",
    "2bet": "raises",
    "3bet": "3-bets",
    "4bet": "4-bets",
    "5bet": "5-bets",
}
_PREFIX_STREET = {"fl": "flop", "tn": "turn", "rv": "river"}


def phrase(key: str) -> str:
    """What a stat-dict key counts, as the end of "Number of ..."."""
    if key in _FIXED:
        return _FIXED[key]
    lowered = key.lower()
    if lowered in _FIXED:
        return _FIXED[lowered]
    for pattern, text in _PATTERNS:
        match = re.match(pattern, lowered)
        if not match:
            continue
        groups = match.groups()
        first = groups[0] if groups else ""
        street = _PREFIX_STREET.get(first) or STREETS.get(first, first)
        values = {"s1": street, "pos": POSITIONS.get(first, first)}
        if len(groups) > 1:
            values["sit"] = SITUATIONS.get(groups[1], groups[1])
            values["what"] = _WHAT.get(groups[1], groups[1])
        return text.format(**values)
    return f"`{key}`"


def words(num_keys: list[tuple[int, str]], den_keys: list[tuple[int, str]]) -> str:
    """``Number of A / Number of B``, with signed sums when a side has several keys."""

    def side(keys: list[tuple[int, str]]) -> str:
        parts = []
        for coeff, key in keys:
            what = phrase(key)
            text = f"Sum of {what[5:]}" if what.startswith("sum: ") else f"Number of {what}"
            parts.append(("minus " if coeff < 0 else ("plus " if parts else "")) + text)
        return "(" + " ".join(parts) + ")" if len(parts) > 1 else parts[0]

    return f"{side(num_keys)} / {side(den_keys)}"


# --------------------------------------------------------------------------- #
# Titles and detailed descriptions
# --------------------------------------------------------------------------- #

_STREET_LONG = {"1": "flop", "2": "turn", "3": "river", "4": "7th street"}

# name -> (title, detailed description). The formula itself is added by the generator.
_TEXT: dict[str, tuple[str, str]] = {
    # --- player / display ---
    "blank": ("Blank cell", "An empty cell used to space a HUD layout. It shows nothing."),
    "game_abbr": ("Game", "The abbreviation of the game played at the table, for example NL Hold'em."),
    "n": (
        "Hands",
        "The number of hands the HUD has for this player, over the aggregation period the HUD uses. Shown as 12.3k from 10,000 hands.",
    ),
    "player_note": ("Player note", "An icon shown when you have written a note on this player."),
    "playername": ("Player name", "The player's screen name."),
    "playershort": ("Player name (short)", "The player's screen name, shortened to fit the cell."),
    "playerprofile": (
        "Player profile",
        "A player type (for example nit, TAG, LAG, fish) chosen from the player's VPIP, PFR and aggression. It is a label, not a number.",
    ),
    "starthands": (
        "Starting hands seen",
        "The hands this player voluntarily played in the current hand-history file, grouped as limped, raised, called a raise, and defended the big blind, with a position letter. It reads one file, not the cache, so it ignores the HUD's aggregation settings; use it in a popup.",
    ),
    # --- preflop core ---
    "vpip": (
        "Voluntarily Put $ In Pot (VPIP)",
        "Percentage of the time that a player put money in the pot preflop by choice: calling, raising or completing. Posting a blind is not voluntary, and walks or blinds folded without a decision are left out of the opportunities.",
    ),
    "pfr": ("Preflop Raise (PFR)", "Percentage of the time that a player raised preflop when they had the chance to."),
    "vpip_pfr_ratio": (
        "VPIP / PFR ratio",
        "How much of a player's voluntary play is raising: VPIP divided by PFR. 1.0 means every hand played was raised; large values mean a lot of calling. Infinite when PFR is 0.",
    ),
    "limp": (
        "Limp",
        "Percentage of the time that a player put money in preflop without raising (VPIP hands that were not PFR hands), over their VPIP opportunities.",
    ),
    "open_limp": (
        "Open Limp",
        "Percentage of the time that a player, first to enter an unopened pot, called the big blind instead of raising or folding.",
    ),
    "car0": (
        "Called a Raise Preflop",
        "Percentage of preflop decisions facing a raise that were calls. Every decision facing a raise counts, so one hand can add several.",
    ),
    "cold_call": (
        "Cold Call Preflop",
        "Percentage of preflop decisions facing a raise that were calls. Reads the same counters as `car0`, so it also counts calls by a player who had already put money in.",
    ),
    "three_B": (
        "Preflop 3-Bet",
        "Percentage of the time that a player re-raised (3-bet) when facing a single preflop raise.",
    ),
    "four_B": ("Preflop 4-Bet", "Percentage of the time that the original raiser re-raised (4-bet) after being 3-bet."),
    "cfour_B": (
        "Cold 4-Bet",
        "Percentage of the time that a player who had not raised before 4-bet when facing a raise and a 3-bet.",
    ),
    "f_3bet": ("Fold to Preflop 3-Bet", "Percentage of the time that the original preflop raiser folded when 3-bet."),
    "f_4bet": (
        "Fold to Preflop 4-Bet",
        "Percentage of the time that a player other than the original raiser (usually the 3-bettor) folded when facing a 4-bet.",
    ),
    "fold_vs_4bet": (
        "Fold to Preflop 4-Bet",
        "Percentage of the time that a player other than the original raiser (usually the 3-bettor) folded when facing a 4-bet. Reads the same counters as `f_4bet`.",
    ),
    "ctb": (
        "Call Preflop 3-Bet",
        "Percentage of the time that the original raiser called a 3-bet: the 3-bets faced that were neither folded to nor 4-bet. Derived by subtraction, so it is an estimate when the counters disagree.",
    ),
    "squeeze": ("Squeeze", "Percentage of the time that a player 3-bet after a raise and at least one call."),
    "fold_to_squeeze": (
        "Fold to Squeeze",
        "Percentage of the time that a player folded to a squeeze after having opened or called the raise.",
    ),
    "face_limpers": (
        "Limpers Faced",
        "The average number of limpers already in the pot when the player first acted preflop, per hand played (limpers are counted only while the pot is unraised). Not a percentage.",
    ),
    "face_raise_preflop": (
        "Faced a Raise Preflop",
        "Percentage of hands where the player had to act preflop after someone raised.",
    ),
    "straddle": ("Straddle", "Percentage of hands where the player posted a straddle."),
    "rfi_total": (
        "Raise First In (RFI)",
        "Percentage of the time that a player raised when the pot was still unopened (nobody had called, raised or limped before). A raise after limpers (an isolation raise) is not counted.",
    ),
    "three_bet_range": (
        "3-Bet Range",
        "Preflop 3-bets as a share of all hands played: how wide a range the player 3-bets with.",
    ),
    "four_bet_range": ("4-Bet Range", "Preflop 4-bets as a share of all hands played."),
    "squeeze_range": ("Squeeze Range", "Squeezes as a share of all hands played."),
    "fbr": (
        "4-Bet Range (estimate)",
        "An estimate of the share of hands the player 4-bets: the 4-bet rate multiplied by the share of hands that were preflop raises.",
    ),
    "gp_2x": (
        "Open Raise (small)",
        "Percentage of the time that a player opened an unopened pot with a raise of less than 40% of their stack.",
    ),
    "gp_os": (
        "Open Shove",
        "Percentage of the time that a player opened an unopened pot with a raise of 40% of their stack or more.",
    ),
    "gp_limp": (
        "Open Limp (GP)",
        "Percentage of the time that a player opened an unopened pot by limping, over the same opportunities as the open raise and open shove.",
    ),
    # --- steal ---
    "steal": (
        "Attempt to Steal Blinds",
        "Percentage of the time that a player raised first in from the cutoff, button or small blind when the pot was unopened.",
    ),
    "s_steal": (
        "Successful Steal",
        "Percentage of steal attempts that won the blinds without a fight (the blinds folded).",
    ),
    "f_SB_steal": (
        "Fold Small Blind to Steal",
        "Percentage of the time that a player in the small blind folded to a steal attempt.",
    ),
    "f_BB_steal": (
        "Fold Big Blind to Steal",
        "Percentage of the time that a player in the big blind folded to a steal attempt.",
    ),
    "f_steal": (
        "Fold Blind to Steal",
        "Percentage of the time that a player in either blind folded to a steal attempt.",
    ),
    "raiseToSteal": ("Re-raise Steal", "Percentage of the time that a player in the blinds re-raised a steal attempt."),
    "resteal": (
        "Re-steal (estimate)",
        "An estimate of how often the player re-steals, built from the overall 3-bet counts with fixed 0.7 and 0.6 factors. It is not a count of re-steals: use Re-raise Steal for the measured value.",
    ),
    "amt_blind": (
        "Average Blinds Posted",
        "The average amount of blinds and antes the player posted per hand, in the table's currency.",
    ),
    # --- postflop totals ---
    "saw_f": ("Saw Flop", "Percentage of hands where the player saw the flop (4th street in stud)."),
    "wtsd": (
        "Went to Showdown (WTSD)",
        "Percentage of the time that a player went to showdown, given that they saw the flop.",
    ),
    "wmsd": (
        "Won Money at Showdown (W$SD)",
        "Percentage of showdowns where the player won money (any share of a pot).",
    ),
    "sd_winrate": (
        "Showdown Win Rate",
        "Percentage of showdowns where the player won money. Same counters as W$SD (`wmsd`).",
    ),
    "WMsF": (
        "Won When Saw Flop (WWSF / W$wsF)",
        "Percentage of the time that a player won some money, in any fashion, given that they saw the flop: with or without a showdown, a split pot counts.",
    ),
    "wwsf": (
        "Won When Saw Flop (WWSF)",
        "Alias of `WMsF` under the name other trackers use. Percentage of the time that a player won some money, in any fashion, given that they saw the flop.",
    ),
    "non_sd_winrate": (
        "Won Without Showdown",
        "Percentage of flops seen that did not reach showdown and that the player still won: won-when-saw-flop hands minus showdown wins, over flops seen minus showdowns.",
    ),
    "river_call_efficiency": (
        "River Call Efficiency",
        "Showdowns won per call made on the river. It compares two different counts (showdowns won, river calls), so it can exceed 100%.",
    ),
    "a_freq_123": (
        "Postflop Aggression Frequency",
        "Percentage of the flops, turns and rivers a player saw on which they bet or raised at least once.",
    ),
    "agg_fact": (
        "Aggression Factor",
        "Bets and raises divided by calls, over the flop, turn, river and 7th street. Higher means more aggressive. Each street counts once per hand for aggression but every call counts.",
    ),
    "agg_fact_pct": (
        "Aggression Percentage",
        "Aggressive streets as a share of aggressive streets plus calls, over the flop to 7th street. A fraction between 0 and 1, not multiplied by 100.",
    ),
    "cbet": (
        "Continuation Bet (all streets)",
        "Percentage of the time that the last preflop raiser bet on a later street when they had the chance, pooled over the flop, turn, river and 7th street.",
    ),
    "cb_ip": (
        "Flop C-Bet In Position (not split)",
        "Meant as the flop continuation-bet rate in position. The cache has no c-bet counts by position, so the stat scales both counts by the share of flops played in position; the share cancels and the value is the overall flop c-bet (`cb1`).",
    ),
    "cb_oop": (
        "Flop C-Bet Out of Position (not split)",
        "Meant as the flop continuation-bet rate out of position. The cache has no c-bet counts by position, so the stat scales both counts by the share of flops played out of position; the share cancels and the value is the overall flop c-bet (`cb1`).",
    ),
    "check_raise_frequency": (
        "Check-Raise (postflop)",
        "Percentage of the time that a player check-raised, given that they checked and acted again on the street, pooled over the flop, turn and river.",
    ),
    "fold_to_allin": (
        "Fold to All-In",
        "Percentage of the time that a player folded the first time they faced an all-in bet or raise in a hand.",
    ),
    "triple_barrel": (
        "Triple Barrel (estimate)",
        "An estimate of how often the preflop raiser bets flop, turn and river: the product of the three street c-bet rates. It does not follow the same hands through the three streets.",
    ),
    "overbet_frequency": (
        "Overbet Frequency (fixed)",
        "Not measured: the stat shows a fixed 15% as soon as any bet exists. Kept so old layouts load.",
    ),
    "probe_bet": (
        "Flop Probe Bet",
        "Percentage of the flops seen without a c-bet on which the player bet: flop bets, capped at that number of flops. An estimate built from totals, not from the same hands.",
    ),
    "probe_bet_turn": (
        "Turn Probe Bet",
        "Percentage of the turns seen without a c-bet on which the player bet: turn bets, capped at that number of turns. An estimate built from totals, not from the same hands.",
    ),
    "probe_bet_river": (
        "River Probe Bet",
        "Percentage of the rivers seen without a c-bet on which the player bet: river bets, capped at that number of rivers. An estimate built from totals, not from the same hands.",
    ),
    "float_bet": (
        "Float Bet Turn",
        "Estimate of how often the player bets the turn after calling the flop in position: turn bets over the smallest of the flops played in position, the flop calls and the turns seen. Built from totals, not from the same hands.",
    ),
    "float_turn": (
        "Turn Float",
        "Percentage of the time that a player who called the flop aggressor's bet bet or raised the turn after that aggressor checked to them.",
    ),
    "float_river": (
        "River Float",
        "Percentage of the time that a player who called the turn aggressor's bet bet or raised the river after that aggressor checked to them.",
    ),
    # --- money ---
    "BBper100": (
        "Big Bets per 100 Hands",
        "Big bets won per 100 hands, where a big bet is two big blinds (the limit-poker unit).",
    ),
    "bbper100": ("Big Blinds per 100 Hands", "Big blinds won per 100 hands."),
    "profit100": (
        "Profit per Hand",
        "The average profit per hand, in cents. The label says per 100 hands but the formula is per hand.",
    ),
    "totalprofit": (
        "Total Profit",
        "The player's total profit over the aggregated hands. It is shown in the game's currency, without a symbol when the pooled game types use different currencies. In tournaments the amount is chips (usually shown as T$).",
    ),
    "amt_bet_p": (
        "Average Preflop Investment",
        "The average amount the player put in preflop per hand, blinds included, in the table's currency.",
    ),
    "amt_bet_f": (
        "Average Flop Investment",
        "The average amount the player put in on the flop per hand played (all hands, not only flops seen).",
    ),
    "amt_bet_t": ("Average Turn Investment", "The average amount the player put in on the turn per hand played."),
    "amt_bet_r": ("Average River Investment", "The average amount the player put in on the river per hand played."),
    "amt_bet_ttl": (
        "Average Total Investment",
        "The average amount the player put in over the whole hand, per hand played.",
    ),
    # --- tournament / last hand ---
    "bbstack": (
        "Stack in Big Blinds",
        "The player's stack after the current hand, in big blinds of that hand. Not aggregated over the history.",
    ),
    "m_ratio": (
        "M Ratio",
        "The player's stack after the current hand divided by the cost of one orbit (blinds and antes). Not aggregated over the history.",
    ),
    "stack_amount": ("Stack", "The player's stack after the last hand, in the table's currency."),
    "stack_bb": ("Stack (bb)", "The player's stack after the last hand, in big blinds."),
    "stack_native_bb": (
        "Stack and Stack (bb)",
        "The player's stack after the last hand, followed by the same stack in big blinds.",
    ),
    "bounty": ("Bounty", "The player's current bounty in a knockout tournament, after the last hand."),
    "covers": (
        "Covers",
        "Who has the bigger stack after the last hand: you cover the player, the player covers you, or even.",
    ),
    # --- deprecated ---
    "call_vs_steal": (
        "Call vs Steal (deprecated)",
        "Shows no data: it needs information about the other players that the cache cannot aggregate.",
    ),
    "three_bet_vs_steal": (
        "3-Bet vs Steal (deprecated)",
        "Shows no data: it needs information about the other players that the cache cannot aggregate.",
    ),
    "iso": ("Isolation Raise (deprecated)", "Shows no data: isolation raises cannot be aggregated from the cache."),
    "avg_bet_size_flop": (
        "Average Bet Size Flop (deprecated)",
        "Shows no data. Use Average Flop Bet Made (`f_bet_made`).",
    ),
    "avg_bet_size_turn": (
        "Average Bet Size Turn (deprecated)",
        "Shows no data. Use Average Turn Bet Made (`t_bet_made`).",
    ),
    "avg_bet_size_river": (
        "Average Bet Size River (deprecated)",
        "Shows no data. Use Average River Bet Made (`r_bet_made`).",
    ),
    # --- All-in or Fold ---
    "aof_allin": (
        "All-in (AoF)",
        "In All-in or Fold games, percentage of the time that a player went all-in on their single decision.",
    ),
    "aof_fold": (
        "Fold (AoF)",
        "In All-in or Fold games, percentage of the time that a player folded on their single decision.",
    ),
    "aof_observed": (
        "Observed All-ins",
        "The number of the player's all-ins whose hole cards and flop were captured, the sample the hand-class stats use.",
    ),
    "aof_showdowns": (
        "Showdowns (AoF)",
        "The number of the player's hands that reached showdown. Reaching showdown does not mean the cards were captured.",
    ),
    "aof_summary": (
        "All-in Profile",
        "What the player shows up with over their observed all-ins, for example NFD×10 W9×8 air×4, most telling first, with the sample size.",
    ),
    "aof_known_equity": (
        "Equity vs Callers",
        "The average flop equity of the player's all-ins against the actual callers, using only all-ins where every caller's cards were captured.",
    ),
    "aof_known_ev": (
        "EV vs Callers (bb)",
        "The average EV, in big blinds, of the player's all-ins against the actual callers, using only fully known hands.",
    ),
    "aof_range_equity": (
        "Equity vs Range",
        "The average flop equity of the player's all-ins against the population range for the room, game and role. Biased toward showdown hands and trained only on earlier hands.",
    ),
    "aof_decision_ev": (
        "Decision EV (bb)",
        "The average modelled EV, in big blinds, of the player's all-in decisions, including the fold and call branches. Before rake until the room's rake schedule is verified.",
    ),
    "aof_weak": (
        "Weak All-ins",
        "Percentage of modelled all-in decisions whose EV is negative even at the upper 95% confidence bound. Uncertain and unmodelled decisions are not counted as weak.",
    ),
    "aof_splash_freq": ("Splash Share", "Percentage of splash-pot hands where the player took a share of the splash."),
    "aof_splash_won": (
        "Splash Collected",
        "The money the player collected from splash pots (money the room adds from outside the pot), in the table's currency. Add it to profit to read the player's real take.",
    ),
}

_HAND_CLASSES = {
    "aof_made": "a made hand",
    "aof_no_made": "no made hand",
    "aof_nfd": "the nut flush draw",
    "aof_non_nfd": "a non-nut flush draw",
    "aof_wrap9": "at least nine straight outs",
    "aof_big_wrap13": "at least thirteen straight outs",
    "aof_pair": "one pair",
    "aof_two_pair": "two pair",
    "aof_trips": "trips",
    "aof_straight": "a straight",
    "aof_flush": "a flush",
    "aof_full_house": "a full house",
    "aof_quads": "quads",
    "aof_straight_flush": "a straight flush",
}

_POS_NAMES = {
    "bb": "Big Blind",
    "sb": "Small Blind",
    "btn": "Button",
    "co": "Cutoff",
    "mp": "Middle Position",
    "ep": "Early Position",
}
_SIT_TITLES = {
    "3bet": "3-Bet",
    "4bet": "4-Bet",
    "squeeze": "Squeeze",
    "cbet": "C-Bet",
    "donk": "Donk Bet",
}


def _family_hand_class(name: str) -> tuple[str, str] | None:
    """Title and description of the `hand_class` stat family, or None."""
    if name in _HAND_CLASSES:
        cls = _HAND_CLASSES[name]
        return (
            f"All-ins with {cls}",
            f"Percentage of the player's observable all-ins (hole cards and flop captured) where they held {cls} on the flop.",
        )
    return None


def _family_position(name: str) -> tuple[str, str] | None:
    """Title and description of the `position` stat family, or None."""
    match = re.fullmatch(r"(three_bet|four_bet|squeeze)_(bb|sb|btn|co|mp|ep)", name)
    if match:
        kind, pos = match.groups()
        label = {"three_bet": "3-Bet", "four_bet": "4-Bet", "squeeze": "Squeeze"}[kind]
        verb = {
            "three_bet": "3-bet when facing a single raise",
            "four_bet": "4-bet after being 3-bet",
            "squeeze": "3-bet after a raise and at least one call",
        }[kind]
        return (f"{label} from {_POS_NAMES[pos]}", f"Percentage of the time that a player in {POSITIONS[pos]} {verb}.")
    return None


def _family_rfi(name: str) -> tuple[str, str] | None:
    """Title and description of the `rfi` stat family, or None."""
    match = re.fullmatch(r"rfi_(early|middle|late)_position", name)
    if match:
        where = {"early": "early position", "middle": "middle position", "late": "the cutoff"}[match.group(1)]
        note = " The button is counted apart, so it is not included." if match.group(1) == "late" else ""
        return (
            f"Raise First In from {match.group(1).title()} Position",
            f"Percentage of the time that a player in {where} raised when the pot was unopened.{note}",
        )
    return None


def _family_enum(name: str) -> tuple[str, str] | None:
    """Title and description of the `enum` stat family, or None."""
    match = re.fullmatch(r"(call|raise|fold)_vs_(preflop|flop|turn|river)_(\w+)", name)
    if match:
        verb, street, sit = match.groups()
        verbs = {"call": "called", "raise": "raised", "fold": "folded"}
        title = f"{verb.title()} vs {street.title()} {_SIT_TITLES.get(sit, sit)}"
        extra = (
            " Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%."
            if verb == "fold"
            else ""
        )
        return (
            title,
            f"Percentage of the time that a player {verbs[verb]} when facing {SITUATIONS.get(sit, sit)} on the {street}.{extra}",
        )
    return None


def _family_float(name: str) -> tuple[str, str] | None:
    """Title and description of the `float` stat family, or None."""
    match = re.fullmatch(r"(call|raise|fold)_float_(turn|river)", name)
    if match:
        verb, street = match.groups()
        before = "flop c-bet" if street == "turn" else "turn bet"
        verbs = {"call": "called", "raise": "raised", "fold": "folded"}
        return (
            f"{verb.title()} vs {street.title()} Barrel after Float",
            f"Percentage of the time that a player who called the {before} in position {verbs[verb]} when the aggressor bet the {street} again.",
        )
    return None


def _family_numbered(name: str) -> tuple[str, str] | None:
    """Title and description of the `numbered` stat family, or None."""
    match = re.fullmatch(r"(a_freq|cb|cr|f_cb|ffreq|dbr|f_dbr)([1-4])", name)
    if match:
        kind, num = match.groups()
        street = _STREET_LONG[num]
        texts = {
            "a_freq": (
                f"{street.title()} Aggression Frequency",
                f"Percentage of the time that a player bet or raised at least once on the {street}, given that they saw it.",
            ),
            "cb": (
                f"{street.title()} Continuation Bet",
                f"Percentage of the time that the last preflop raiser bet (or raised) on the {street} when they had the chance.",
            ),
            "cr": (
                f"{street.title()} Check-Raise",
                f"Percentage of the time that a player check-raised the {street}, given that they checked and acted again on it.",
            ),
            "f_cb": (
                f"Fold to {street.title()} Continuation Bet",
                f"Percentage of the time that a player folded when facing a {street} continuation bet.",
            ),
            "ffreq": (
                f"{street.title()} Fold to Bet or Raise",
                f"Percentage of the time that a player folded on the {street} after someone else bet or raised there.",
            ),
            "dbr": (
                f"{street.title()} Bet/Raise when not the C-Bettor",
                f"Percentage of the {street}s a player saw outside a continuation-bet spot on which they bet or raised: aggression that is not a c-bet (donk bets and raises).",
            ),
            "f_dbr": (
                f"Fold to {street.title()} Bet/Raise (not a C-Bet)",
                f"Percentage of the time that a player folded on the {street} to a bet or raise that was not a continuation bet.",
            ),
        }
        return texts[kind]
    return None


def _family_fold_to_cbet(name: str) -> tuple[str, str] | None:
    """Title and description of the `fold_to_cbet` stat family, or None."""
    match = re.fullmatch(r"fold_to_cbet_(flop|turn|river)", name)
    if match:
        street = match.group(1)
        return (
            f"Fold to {street.title()} Continuation Bet",
            f"Percentage of the time that a player folded when facing a {street} continuation bet.",
        )
    return None


def _family_postflop_raises(name: str) -> tuple[str, str] | None:
    """Title and description of the `postflop_raises` stat family, or None."""
    match = re.fullmatch(r"(three_B|four_B|fold_to_three_B)_(flop|turn|river)", name)
    if match:
        kind, street = match.groups()
        texts = {
            "three_B": (
                f"{street.title()} 3-Bet",
                f"Percentage of the time that a player re-raised when facing a bet and a raise on the {street}.",
            ),
            "four_B": (
                f"{street.title()} 4-Bet",
                f"Percentage of the time that a player re-raised when facing a 3-bet on the {street}.",
            ),
            "fold_to_three_B": (
                f"Fold to {street.title()} 3-Bet",
                f"Percentage of the time that a player who raised the {street} folded to a 3-bet.",
            ),
        }
        return texts[kind]
    return None


def _family_street_frequency(name: str) -> tuple[str, str] | None:
    """Title and description of the `street_frequency` stat family, or None."""
    match = re.fullmatch(r"(open|first_raise|face_raise|fold|bet_frequency|raise_frequency)_(flop|turn|river)", name)
    if match:
        kind, street = match.groups()
        texts = {
            "open": (
                f"{street.title()} Open (first bet)",
                f"Percentage of the time that a player made the first bet on the {street} when nobody had bet before them.",
            ),
            "first_raise": (
                f"{street.title()} First Raise",
                f"Percentage of the {street}s a player saw on which they made the first raise.",
            ),
            "face_raise": (
                f"Faced a Raise on the {street.title()}",
                f"Percentage of the {street}s a player saw on which they acted after a raise.",
            ),
            "fold": (f"{street.title()} Fold", f"Percentage of the {street}s a player saw that they folded."),
            "bet_frequency": (
                f"{street.title()} Bet Frequency",
                f"Bets made on the {street} per {street} seen, as a percentage.",
            ),
            "raise_frequency": (
                f"{street.title()} Raise Frequency",
                f"Raises made on the {street} per {street} seen, as a percentage. Every raise counts, a re-raise too, so it can pass 100%.",
            ),
        }
        return texts[kind]
    return None


def _family_price(name: str) -> tuple[str, str] | None:
    """Title and description of the `price` stat family, or None."""
    match = re.fullmatch(r"([pftr])_(bet|raise|2bet|3bet|4bet|5bet)_facing", name)
    if match:
        st, what = match.groups()
        street = STREETS[st]
        noun = {"bet": "Bet", "raise": "Raise", "2bet": "Raise", "3bet": "3-Bet", "4bet": "4-Bet", "5bet": "5-Bet"}[
            what
        ]
        latest = " When several raises are faced on the street, the last one counts." if what == "raise" else ""
        return (
            f"Price of {street.title()} {noun} Faced",
            f"The average price the player was offered when facing a {street} {noun.lower()}: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.{latest}",
        )
    return None


def _family_size(name: str) -> tuple[str, str] | None:
    """Title and description of the `size` stat family, or None."""
    match = re.fullmatch(r"([pftr])_(bet|raise)_made(_2)?", name)
    if match:
        st, what, second = match.groups()
        street = STREETS[st]
        if what == "bet":
            return (
                f"Average {street.title()} Bet Size",
                f"The average size of the player's first {street} bet, as a percentage of the pot before the bet.",
            )
        nth = "second" if second else "first"
        return (
            f"Average {street.title()} Raise Size{' (2nd raise)' if second else ''}",
            f"The average size of the player's {nth} {street} raise: the raise-to amount as a percentage of the pot before the raise.",
        )
    return None


def _family_spr(name: str) -> tuple[str, str] | None:
    """Title and description of the `spr` stat family, or None."""
    match = re.fullmatch(r"([ftr])_spr", name)
    if match:
        street = STREETS[match.group(1)]
        return (
            f"{street.title()} Stack-to-Pot Ratio",
            f"The average stack-to-pot ratio entering the {street}: the effective stack (smallest of the player's and the deepest active opponent's) divided by the pot.",
        )
    return None


_FAMILIES = (
    _family_hand_class,
    _family_position,
    _family_rfi,
    _family_enum,
    _family_float,
    _family_numbered,
    _family_fold_to_cbet,
    _family_postflop_raises,
    _family_street_frequency,
    _family_price,
    _family_size,
    _family_spr,
)


def _family(name: str) -> tuple[str, str] | None:
    """Title and description of a stat that belongs to a numbered or positional family."""
    for family in _FAMILIES:
        found = family(name)
        if found is not None:
            return found
    return None


def describe(name: str, origin: str, fallback: str) -> tuple[str, str]:
    """``(title, detailed description)`` of a stat; *fallback* is its tooltip."""
    if origin == "native":
        if name in _TEXT:
            return _TEXT[name]
        family = _family(name)
        if family:
            return family
    return fallback, fallback


# Formula in words for the stats whose formula is written by hand in the generator.
OVERRIDE_WORDS: dict[str, str] = {
    "BBper100": "Sum of profit in cents × 50 / Sum of big blinds in play (big blind × hands); a big bet is two big blinds",
    "bbper100": "Sum of profit in cents × 100 / Sum of big blinds in play (big blind × hands)",
    "profit100": "Sum of profit in cents / Number of hands played",
    "totalprofit": "Sum of profit in cents / 100, in the game's currency",
    "n": "Number of hands played",
    "agg_fact": "(Number of hands with a bet or raise on the flop + turn + river + 7th street) / (Number of calls on the flop + turn + river + 7th street)",
    "agg_fact_pct": "(Number of hands with a bet or raise on the flop to 7th street) / (that number + Number of calls on the flop to 7th street)",
    "cbet": "(Number of continuation bets, flop to 7th street) / (Number of continuation-bet opportunities, flop to 7th street) × 100",
    "cb_ip": "(Number of flop continuation bets × r) / (Number of flop continuation-bet opportunities × r) × 100, r = share of flops in position (cancels)",
    "cb_oop": "(Number of flop continuation bets × r) / (Number of flop continuation-bet opportunities × r) × 100, r = share of flops out of position (cancels)",
    "fbr": "(Number of preflop 4-bets / Number of 4-bet opportunities) × (Number of preflop raises / Number of hands played) × 100",
    "triple_barrel": "(flop c-bets / flop c-bet chances) × (turn c-bets / turn c-bet chances) × (river c-bets / river c-bet chances) × 100",
    "resteal": "(0.7 × Number of preflop 3-bets) / (0.6 × Number of 3-bet opportunities) × 100",
    "vpip_pfr_ratio": "(Number of VPIP hands / VPIP opportunities) / (Number of preflop raises / raise opportunities)",
    "probe_bet": "min(flop bets, flops seen − flop c-bets) / (Number of flops seen − Number of flop c-bets) × 100",
    "probe_bet_turn": "min(turn bets, turns seen − turn c-bets) / (Number of turns seen − Number of turn c-bets) × 100",
    "probe_bet_river": "min(river bets, rivers seen − river c-bets) / (Number of rivers seen − Number of river c-bets) × 100",
    "overbet_frequency": "15% (a constant)",
    "float_bet": "min(Number of turn bets, opp) / opp × 100, where opp = the smallest of Number of flops in position, Number of flop calls, Number of turns seen",
    "stack_bb": "Stack after the last hand / big blind",
    "stack_native_bb": "Stack after the last hand, then stack / big blind",
    "bbstack": "Stack after the current hand / big blind of that hand",
    "m_ratio": "Stack after the current hand / (antes + blinds of one orbit)",
    "aof_observed": "Number of observable all-ins (decision all-in, hole cards and flop captured)",
    "aof_showdowns": "Number of hands where the player went to showdown",
    "aof_splash_won": "Sum of splash money collected, in cents / 100",
}


# PT4 stock stats (by their PT4 title) and the FPDB HUD stat that answers the same question.
# The PT4 side is read from docs/pt4-stock-stat-coverage.md, which pt4_import --coverage
# generates from PT4's own StatDefinitions.pt4; the parity itself is measured, not assumed.
PT4_EQUIVALENTS: dict[str, str] = {
    "VPIP": "vpip",
    "PFR": "pfr",
    "3Bet Preflop": "three_B",
    "Fold to PF 3Bet": "f_3bet",
    "CBet Flop": "cb1",
    "Fold to F CBet": "f_cb1",
    "WTSD": "wtsd",
    "WSD": "wmsd",
    "Total AF": "agg_fact",
    "Flop AFq": "a_freq1",
    "Total AFq": "a_freq_123",
    "Att To Steal": "steal",
    "Fold to Steal": "f_steal",
}

# Why a measured PT4 difference exists, for the stats whose formula differs.
PT4_DIFFERENCES: dict[str, str] = {
    "agg_fact": "PT4 divides every flop, turn and river bet and raise by the calls on those streets. FPDB counts hands with at least one bet or raise on each street (one per street, however many raises) and adds 7th street, over every call.",
    "a_freq1": "PT4: flop bets and raises / (flop calls + folds + bets + raises), over actions. FPDB: flops on which the player bet or raised at least once / flops seen, over hands.",
    "a_freq_123": "PT4: flop-to-river bets and raises / (calls + folds + bets + raises), over actions. FPDB: streets with a bet or raise / streets seen, over hands.",
}
