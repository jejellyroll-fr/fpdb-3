"""Hand-written HUD Stats Guide entries (issue #751).

The stats whose logic is not a plain ratio of HudCache counters -- averages,
estimates, last-hand values, deprecated placeholders -- cannot be solved from
their output, so their formula and SQL logic are written here, read from the
source of each function in ``fpdb_3_legacy/stats_*.py``.
"""

from __future__ import annotations

# name -> dict(formula=..., sql=..., note=..., status=...)
OVERRIDES: dict[str, dict[str, str]] = {
    "BBper100": dict(
        formula="50 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)",
        sql="net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)",
        note="Big *bets* per 100 hands: the 50 factor counts a big bet as two big blinds. `bbper100` is the big-blind version.",
    ),
    "bbper100": dict(
        formula="100 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)",
        sql="net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)",
        note="Big blinds won per 100 hands.",
    ),
    "agg_fact": dict(
        formula="(Σ aggr_1..4) / (Σ call_1..4); the numerator alone when there is no call",
        sql="aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4 (flop to 7th street)",
        note="Postflop aggression factor, raw ratio.",
    ),
    "agg_fact_pct": dict(
        formula="(Σ aggr_1..4) / (Σ call_1..4 + Σ aggr_1..4)",
        sql="aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4",
        note="Despite its name the result is a 0..1 fraction (aggression / (aggression + calls)), not multiplied by 100.",
    ),
    "cbet": dict(
        formula="(Σ cb_1..4) / (Σ cb_opp_1..4) × 100",
        sql="cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 4",
        note="Continuation bet across all four streets pooled; `cb1`..`cb4` give one street each.",
    ),
    "cb_ip": dict(
        formula="(cb_1 × r) / (cb_opp_1 × r) × 100 with r = street1inposition / saw_f; r cancels, so = cb_1 / cb_opp_1 × 100",
        sql="cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); saw_f = SUM(HudCache.street1Seen); street1inposition = SUM(HudCache.street1InPosition)",
        note="Not split by position: both counts are scaled by the same in-position share of flops seen, which cancels out, so the value always equals `cb1`. HudCache has no c-bet count by position.",
        status="estimate",
    ),
    "cb_oop": dict(
        formula="(cb_1 × r) / (cb_opp_1 × r) × 100 with r = (saw_f − street1inposition) / saw_f; r cancels, so = cb_1 / cb_opp_1 × 100",
        sql="cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); saw_f = SUM(HudCache.street1Seen); street1inposition = SUM(HudCache.street1InPosition)",
        note="Not split by position: both counts are scaled by the same out-of-position share of flops seen, which cancels out, so the value always equals `cb1`. HudCache has no c-bet count by position.",
        status="estimate",
    ),
    "fbr": dict(
        formula="(fb_0 / fb_opp_0) × (pfr / n) × 100",
        sql="fb_0 = SUM(HudCache.street0_4BDone); fb_opp_0 = SUM(HudCache.street0_4BChance); pfr = SUM(HudCache.street0Aggr); n = SUM(HudCache.n)",
        note="Historical estimate of the four-bet range: the four-bet rate multiplied by the share of hands that were preflop raises.",
    ),
    "probe_bet": dict(
        formula="min(bet_1, saw_f − cb_1) / (saw_f − cb_1) × 100",
        sql="saw_f = SUM(HudCache.street1Seen); cb_1 = SUM(HudCache.street1CBDone); bet_1 = SUM(HudCache.street1Bets)",
        note="Flop probe: flop bets over the flops seen where the player did not c-bet. An estimate from totals, not the same hands.",
        status="estimate",
    ),
    "probe_bet_turn": dict(
        formula="min(bet_2, saw_2 − cb_2) / (saw_2 − cb_2) × 100",
        sql="saw_2 = SUM(HudCache.street2Seen); cb_2 = SUM(HudCache.street2CBDone); bet_2 = SUM(HudCache.street2Bets)",
        note="Turn probe: turn bets over the turns seen where the player did not c-bet. An estimate from totals, not the same hands.",
        status="estimate",
    ),
    "probe_bet_river": dict(
        formula="min(bet_3, saw_3 − cb_3) / (saw_3 − cb_3) × 100",
        sql="saw_3 = SUM(HudCache.street3Seen); cb_3 = SUM(HudCache.street3CBDone); bet_3 = SUM(HudCache.street3Bets)",
        note="River probe: river bets over the rivers seen where the player did not c-bet. An estimate from totals, not the same hands.",
        status="estimate",
    ),
    "float_bet": dict(
        formula="min(bet_2, opp) / opp × 100 with opp = min(street1inposition, call_1, saw_2)",
        sql="street1inposition = SUM(HudCache.street1InPosition); call_1 = SUM(HudCache.street1Calls); saw_2 = SUM(HudCache.street2Seen); bet_2 = SUM(HudCache.street2Bets)",
        note="An estimate from totals, not the same hands: the opportunities are the smallest of flops in position, flop calls and turns seen.",
        status="estimate",
    ),
    "triple_barrel": dict(
        formula="min(cb_opp_1..3) × Π (cb_N / cb_opp_N) / min(cb_opp_1..3) × 100 = Π (cb_N / cb_opp_N) × 100",
        sql="cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 3",
        note="An estimate: the product of the three street c-bet rates, assuming the streets are independent. It does not follow the same hands through the three streets.",
    ),
    "overbet_frequency": dict(
        formula="constant 15 %, shown once any bet has been seen (bet_1 + bet_2 + bet_3 > 0)",
        sql="bet_N = SUM(HudCache.streetNBets) for streets 1 to 3",
        note="Not measured. The function returns a fixed 15 % estimate; it is kept for old layouts.",
        status="estimate",
    ),
    "resteal": dict(
        formula="(0.7 × tb_0) / (0.6 × tb_opp_0) × 100",
        sql="tb_0 = SUM(HudCache.street0_3BDone); tb_opp_0 = SUM(HudCache.street0_3BChance)",
        note="An estimate built from the 3-bet counts with fixed 0.7 and 0.6 factors (the share assumed to be from the blinds); it is not a count of re-steals. Use `raiseToSteal` for the measured value.",
        status="estimate",
    ),
    "vpip_pfr_ratio": dict(
        formula="(vpip / vpip_opp) / (pfr / pfr_opp)",
        sql="vpip = SUM(HudCache.street0VPI); vpip_opp = SUM(HudCache.street0VPIChance); pfr = SUM(HudCache.street0Aggr); pfr_opp = SUM(HudCache.street0AggrChance)",
        note="A plain ratio of the two percentages (not multiplied by 100); shows infinity when PFR is 0.",
    ),
    "profit100": dict(
        formula="net / n  (net in cents, so cents per hand, shown as per 100 hands in the label)",
        sql="net = SUM(HudCache.totalProfit); n = SUM(HudCache.n)",
        note="The label says per 100 hands but the formula is the average profit per hand, in cents.",
    ),
    "totalprofit": dict(
        formula="net / 100, formatted with the game's currency",
        sql="net = SUM(HudCache.totalProfit); currency is not selected by the HUD queries, so the USD default is used",
    ),
    "n": dict(
        formula="n (hand count; shown as 12.3k from 10 000)",
        sql="n = SUM(HudCache.n)",
    ),
    "bbstack": dict(
        formula="end stack of the player at the current hand / big blind of that hand",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value, not aggregated over the history.",
    ),
    "m_ratio": dict(
        formula="end stack / (antes + blinds posted in the hand + small blind + big blind)",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value, not aggregated over the history.",
    ),
    "stack_amount": dict(
        formula="reconstructed stack of the player, in the table's currency",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value.",
    ),
    "stack_bb": dict(
        formula="reconstructed stack / big blind",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value.",
    ),
    "stack_native_bb": dict(
        formula="reconstructed stack, followed by the stack / big blind",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value.",
    ),
    "bounty": dict(
        formula="the player's current bounty after the last hand",
        sql="not a HudCache aggregate: read from the hand being displayed (Hand object)",
        note="Knockout tournaments only.",
    ),
    "covers": dict(
        formula="compares the player's end stack with the hero's: +1 you cover, −1 covers you, 0 even",
        sql="not a HudCache aggregate: read from the hand being displayed (Hand object)",
    ),
    "starthands": dict(
        formula="lists the hands the player voluntarily played in the current history file, grouped as limped, raised, called a raise, defended the BB",
        sql="SELECT DISTINCT startCards, street0Aggr, street0CalledRaiseDone, position FROM Hands, HandsPlayers, Gametypes WHERE street0VPI AND fileId = the current file",
        note="Meant for popups: it reads one history file, not the cache, so it ignores the HUD's aggregation settings.",
    ),
    "playerprofile": dict(
        formula="player type (for example nit, TAG, LAG, fish) chosen by PlayerProfiler.classify_player from VPIP, PFR and aggression",
        sql="uses the HUD stat row of the player (VPIP, PFR, aggression inputs)",
        note="A label, not a number.",
    ),
    "playername": dict(formula="the player's name", sql="screen_name = Players.name"),
    "playershort": dict(formula="the player's name, shortened to fit the cell", sql="screen_name = Players.name"),
    "player_note": dict(
        formula="an icon when the player has a note",
        sql="screen_name = Players.name; the note is read from the notes of that player",
    ),
    "game_abbr": dict(
        formula="abbreviation of the game being played (for example Hold'em NL)",
        sql="read from the game type of the table; not a HudCache aggregate",
    ),
    "blank": dict(formula="an empty cell, used as a spacer in layouts", sql="none"),
    "call_vs_steal": dict(
        formula="no data (deprecated)",
        sql="none: needs data about other players that HudCache cannot aggregate",
        status="deprecated",
    ),
    "iso": dict(
        formula="no data (deprecated)",
        sql="none: isolation raises cannot be aggregated from HudCache",
        status="deprecated",
    ),
    "three_bet_vs_steal": dict(
        formula="no data (deprecated)",
        sql="none: needs data about other players that HudCache cannot aggregate",
        status="deprecated",
    ),
    "avg_bet_size_flop": dict(formula="no data (deprecated); see `f_bet_made`", sql="none", status="deprecated"),
    "avg_bet_size_turn": dict(formula="no data (deprecated); see `t_bet_made`", sql="none", status="deprecated"),
    "avg_bet_size_river": dict(formula="no data (deprecated); see `r_bet_made`", sql="none", status="deprecated"),
    "aof_observed": dict(
        formula="aof_obs (a count)",
        sql="aof_obs = count of all-or-fold decisions with decision = 'allin' and cardsObservable (sql_queries_aof.py)",
    ),
    "aof_showdowns": dict(
        formula="sd (a count, with n as the sample)",
        sql="sd = SUM(HudCache.sawShowdown); n = SUM(HudCache.n)",
        note="Hands that reached showdown, not hands whose cards were captured.",
    ),
    "aof_splash_won": dict(
        formula="aof_splash_cents / 100",
        sql="aof_splash_cents, aof_splash_seen and aof_splash_hit from sql_queries_aof.py (splash pot winnings)",
        note="Money the room adds to the pot from outside; read it together with profit.",
    ),
    "aof_summary": dict(
        formula="the markers seen over the observed all-ins, for example NFD×10 W9×8 air×4",
        sql="aof_obs and one counter per marker (aof_nfd, aof_wrap9, aof_pair…) from sql_queries_aof.py",
    ),
}
