# HUD Stats Guide

Generated from the code by `tools/gen_stats_guide.py`; do not edit by hand. The same data feeds the in-app **Stats Guide**.

## How to read an entry

- **Code identifier**: the name written in a HUD layout (`<stat stat_name=...>`). It is what the Add/Edit Statistic picker stores.
- **HUD abbreviation**: the short text the HUD draws; it is the first part of the value the stat function returns.
- **XML titles**: the `col_title` of the legacy Ring Player Stats columns that show the same measure. They are display titles only.
- **Formula** and **SQL database field / logic**: the numerator and denominator the stat function really uses, and the HudCache expression that fills each input.

Stats installed as user stat packs (`stat_packs`) or custom `stats.d` files are extensible and are **not** listed here.

## Player

### `blank` — 

- **Description**: <blank>
- **Formula**: `an empty cell, used as a spacer in layouts`
- **SQL database field / logic**: none

### `game_abbr` — game

- **Description**: Game abbreviation
- **Formula**: `abbreviation of the game being played (for example Hold'em NL)`
- **SQL database field / logic**: read from the game type of the table; not a HudCache aggregate
- **Detailed HUD text**: `game_abbr`

### `n` — n

- **Description**: Number of hands seen
- **Formula**: `n (hand count; shown as 12.3k from 10 000)`
- **SQL database field / logic**: n = SUM(HudCache.n)

### `player_note` — 📝

- **Description**: Player note icon
- **Formula**: `an icon when the player has a note`
- **SQL database field / logic**: screen_name = Players.name; the note is read from the notes of that player

### `playername` — 1

- **Description**: Player name
- **Formula**: `the player's name`
- **SQL database field / logic**: screen_name = Players.name
- **Note**: The HUD abbreviation `1` is shared with: `playershort`.

### `playerprofile` — p

- **Description**: Player Profile
- **Formula**: `player type (for example nit, TAG, LAG, fish) chosen by PlayerProfiler.classify_player from VPIP, PFR and aggression`
- **SQL database field / logic**: uses the HUD stat row of the player (VPIP, PFR, aggression inputs)
- **Detailed HUD text**: `playerprofile`
- **Note**: A label, not a number. The HUD abbreviation `p` is shared with: `pfr`, `profit100`.

### `playershort` — 1

- **Description**: Player Name 1-5
- **Formula**: `the player's name, shortened to fit the cell`
- **SQL database field / logic**: screen_name = Players.name
- **Note**: The HUD abbreviation `1` is shared with: `playername`.

### `starthands` — 

- **Description**: Hands seen at this table
- **Formula**: `lists the hands the player voluntarily played in the current history file, grouped as limped, raised, called a raise, defended the BB`
- **SQL database field / logic**: SELECT DISTINCT startCards, street0Aggr, street0CalledRaiseDone, position FROM Hands, HandsPlayers, Gametypes WHERE street0VPI AND fileId = the current file
- **Note**: Meant for popups: it reads one history file, not the cache, so it ignores the HUD's aggregation settings.

## Preflop

### `call_vs_preflop_3bet` — Cv3B

- **Description**: % calling facing a preflop 3-bet
- **Formula**: `cnt_p_call_3bet / cnt_p_face_3bet × 100`
- **SQL database field / logic**: cnt_p_face_3bet = SUM(HudCache.cnt_p_face_3bet); cnt_p_call_3bet = SUM(HudCache.cnt_p_call_3bet)

### `call_vs_preflop_4bet` — Cv4B

- **Description**: % calling facing a preflop 4-bet
- **Formula**: `cnt_p_call_4bet / cnt_p_face_4bet × 100`
- **SQL database field / logic**: cnt_p_face_4bet = SUM(HudCache.cnt_p_face_4bet); cnt_p_call_4bet = SUM(HudCache.cnt_p_call_4bet)

### `call_vs_preflop_squeeze` — CvSQ

- **Description**: % calling facing a preflop squeeze
- **Formula**: `cnt_p_call_squeeze / cnt_p_face_squeeze × 100`
- **SQL database field / logic**: cnt_p_face_squeeze = SUM(HudCache.cnt_p_face_squeeze); cnt_p_call_squeeze = SUM(HudCache.cnt_p_call_squeeze)

### `car0` — CAR0

- **Description**: % called a raise preflop
- **Formula**: `car_0 / car_opp_0 × 100`
- **SQL database field / logic**: car_opp_0 = SUM(HudCache.street0CalledRaiseChance); car_0 = SUM(HudCache.street0CalledRaiseDone)
- **Detailed HUD text**: `CAR_pf`
- **XML titles**: `CARpre`

### `cfour_B` — C4B

- **Description**: % cold 4 bet preflop/3rd street
- **Formula**: `cfb_0 / cfb_opp_0 × 100`
- **SQL database field / logic**: cfb_opp_0 = SUM(HudCache.street0_C4BChance); cfb_0 = SUM(HudCache.street0_C4BDone)
- **Detailed HUD text**: `C4B_pf`

### `cold_call` — cc

- **Description**: % cold call preflop
- **Formula**: `CAR_0 / CAR_opp_0 × 100`
- **SQL database field / logic**: CAR_opp_0 = SUM(HudCache.street0CalledRaiseChance); CAR_0 = SUM(HudCache.street0CalledRaiseDone)

### `ctb` — ctb

- **Description**: % call 3 bet
- **Formula**: `(f3b_opp_0 − f3b_0 − fb_0) / f3b_opp_0 × 100`
- **SQL database field / logic**: f3b_opp_0 = SUM(HudCache.street0_FoldTo3BChance); f3b_0 = SUM(HudCache.street0_FoldTo3BDone); fb_0 = SUM(HudCache.street0_4BDone)
- **Detailed HUD text**: `call3B`

### `f_3bet` — F3B

- **Description**: % fold to 3 bet preflop/3rd street
- **Formula**: `f3b_0 / f3b_opp_0 × 100`
- **SQL database field / logic**: f3b_opp_0 = SUM(HudCache.street0_FoldTo3BChance); f3b_0 = SUM(HudCache.street0_FoldTo3BDone)
- **Detailed HUD text**: `F3B_pf`
- **XML titles**: `PFF3`
- **Note**: The HUD abbreviation `F3B` is shared with: `three_B_flop`.

### `f_4bet` — F4B

- **Description**: % fold to 4 bet preflop/3rd street
- **Formula**: `f4b_0 / f4b_opp_0 × 100`
- **SQL database field / logic**: f4b_opp_0 = SUM(HudCache.street0_FoldTo4BChance); f4b_0 = SUM(HudCache.street0_FoldTo4BDone)
- **Detailed HUD text**: `F4B_pf`
- **XML titles**: `PFF4`
- **Note**: The HUD abbreviation `F4B` is shared with: `four_B_flop`.

### `face_limpers` — FLmp

- **Description**: avg limpers faced preflop
- **Formula**: `face_limpers / n`
- **SQL database field / logic**: n = SUM(HudCache.n); face_limpers = SUM(HudCache.street0_FaceLimpers)

### `face_raise_preflop` — FvRp

- **Description**: % face raise preflop
- **Formula**: `p_face_raise / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); p_face_raise = SUM(HudCache.street0FaceRaise)

### `fbr` — fbr

- **Description**: 4 bet range
- **Formula**: `(fb_0 / fb_opp_0) × (pfr / n) × 100`
- **SQL database field / logic**: fb_0 = SUM(HudCache.street0_4BDone); fb_opp_0 = SUM(HudCache.street0_4BChance); pfr = SUM(HudCache.street0Aggr); n = SUM(HudCache.n)
- **Detailed HUD text**: `4Brange`
- **Note**: Historical estimate of the four-bet range: the four-bet rate multiplied by the share of hands that were preflop raises.

### `fold_to_3bet_preflop` — Fold to 3-bet (preflop)

- **Description**: How often the player folded when facing a preflop 3-bet.
- **Formula**: `decisions matching the numerator {'response': 'fold'} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'preflop', 'situation': 'facing_3bet'}
- **Note**: Analytics definition (metric fold_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### `fold_to_squeeze` — FvSq

- **Description**: % fold to squeeze
- **Formula**: `sqzdef_fold / sqzdef_opp × 100`
- **SQL database field / logic**: sqzdef_opp = SUM(HudCache.street0_FoldToSqueezeChance); sqzdef_fold = SUM(HudCache.street0_FoldToSqueezeDone)

### `fold_vs_4bet` — f4b

- **Description**: % fold vs 4bet
- **Formula**: `F4B_0 / F4B_opp_0 × 100`
- **SQL database field / logic**: F4B_opp_0 = SUM(HudCache.street0_FoldTo4BChance); F4B_0 = SUM(HudCache.street0_FoldTo4BDone)

### `fold_vs_preflop_3bet` — Fv3B

- **Description**: % folding facing a preflop 3-bet
- **Formula**: `(cnt_p_face_3bet − cnt_p_call_3bet − cnt_p_raise_3bet) / cnt_p_face_3bet × 100`
- **SQL database field / logic**: cnt_p_face_3bet = SUM(HudCache.cnt_p_face_3bet); cnt_p_call_3bet = SUM(HudCache.cnt_p_call_3bet); cnt_p_raise_3bet = SUM(HudCache.cnt_p_raise_3bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_preflop_4bet` — Fv4B

- **Description**: % folding facing a preflop 4-bet
- **Formula**: `(cnt_p_face_4bet − cnt_p_call_4bet − cnt_p_raise_4bet) / cnt_p_face_4bet × 100`
- **SQL database field / logic**: cnt_p_face_4bet = SUM(HudCache.cnt_p_face_4bet); cnt_p_call_4bet = SUM(HudCache.cnt_p_call_4bet); cnt_p_raise_4bet = SUM(HudCache.cnt_p_raise_4bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_preflop_squeeze` — FvSQ

- **Description**: % folding facing a preflop squeeze
- **Formula**: `(cnt_p_face_squeeze − cnt_p_call_squeeze − cnt_p_raise_squeeze) / cnt_p_face_squeeze × 100`
- **SQL database field / logic**: cnt_p_face_squeeze = SUM(HudCache.cnt_p_face_squeeze); cnt_p_call_squeeze = SUM(HudCache.cnt_p_call_squeeze); cnt_p_raise_squeeze = SUM(HudCache.cnt_p_raise_squeeze)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `four_B` — 4B

- **Description**: % 4 bet preflop/3rd street
- **Formula**: `fb_0 / fb_opp_0 × 100`
- **SQL database field / logic**: fb_opp_0 = SUM(HudCache.street0_4BChance); fb_0 = SUM(HudCache.street0_4BDone)
- **XML titles**: `PF4`

### `four_bet` — 4Bet

- **Description**: Preflop 4-bet.
- **Formula**: `100 * street0_4BDone / street0_4BChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street0_4BDone, street0_4BChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `four_bet_bb` — 4B BB

- **Description**: % 4B BB preflop
- **Formula**: `fb_bb / fb_opp_bb × 100`
- **SQL database field / logic**: fb_opp_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_4BChance ELSE 0 END); fb_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_4BDone ELSE 0 END)

### `four_bet_btn` — 4B BTN

- **Description**: % 4B BTN preflop
- **Formula**: `fb_btn / fb_opp_btn × 100`
- **SQL database field / logic**: fb_opp_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_4BChance ELSE 0 END); fb_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_4BDone ELSE 0 END)

### `four_bet_co` — 4B CO

- **Description**: % 4B CO preflop
- **Formula**: `fb_co / fb_opp_co × 100`
- **SQL database field / logic**: fb_opp_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_4BChance ELSE 0 END); fb_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_4BDone ELSE 0 END)

### `four_bet_ep` — 4B EP

- **Description**: % 4B EP preflop
- **Formula**: `fb_ep / fb_opp_ep × 100`
- **SQL database field / logic**: fb_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_4BChance ELSE 0 END); fb_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_4BDone ELSE 0 END)

### `four_bet_mp` — 4B MP

- **Description**: % 4B MP preflop
- **Formula**: `fb_mp / fb_opp_mp × 100`
- **SQL database field / logic**: fb_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_4BChance ELSE 0 END); fb_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_4BDone ELSE 0 END)

### `four_bet_range` — 4BR

- **Description**: 4-bet range
- **Formula**: `fb_0 / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); fb_0 = SUM(HudCache.street0_4BDone)

### `four_bet_sb` — 4B SB

- **Description**: % 4B SB preflop
- **Formula**: `fb_sb / fb_opp_sb × 100`
- **SQL database field / logic**: fb_opp_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_4BChance ELSE 0 END); fb_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_4BDone ELSE 0 END)

### `gp_2x` — 2X

- **Description**: % open-raise (<40% stack)
- **Formula**: `gp_2x / gp_open_opp × 100`
- **SQL database field / logic**: gp_open_opp = SUM(HudCache.cnt_gp_open_opp); gp_2x = SUM(HudCache.cnt_gp_2x)

### `gp_limp` — Limp

- **Description**: % open-limp
- **Formula**: `gp_limp / gp_open_opp × 100`
- **SQL database field / logic**: gp_open_opp = SUM(HudCache.cnt_gp_open_opp); gp_limp = SUM(HudCache.cnt_gp_limp)

### `gp_os` — OS

- **Description**: % open-shove (>=40% stack)
- **Formula**: `gp_os / gp_open_opp × 100`
- **SQL database field / logic**: gp_open_opp = SUM(HudCache.cnt_gp_open_opp); gp_os = SUM(HudCache.cnt_gp_os)

### `iso` — iso

- **Description**: % isolation raise (deprecated)
- **Formula**: `no data (deprecated)`
- **SQL database field / logic**: none: isolation raises cannot be aggregated from HudCache
- **Status**: deprecated

### `limp` — limp

- **Description**: % limp preflop
- **Formula**: `(vpip − pfr) / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI); pfr = SUM(HudCache.street0Aggr)

### `open_limp` — openlimp

- **Description**: % open limp preflop
- **Formula**: `open_limp / open_limp_opp × 100`
- **SQL database field / logic**: open_limp_opp = SUM(HudCache.street0OpenLimpChance); open_limp = SUM(HudCache.street0OpenLimp)

### `p_2bet_facing` — 2Bvs

- **Description**: avg 2bet faced (% pot)
- **Formula**: `(p_2bet_facing_bp / p_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_2bet_facing_cnt = SUM(HudCache.cnt_p_2bet_facing); p_2bet_facing_bp = SUM(HudCache.val_p_2bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `p_3bet_facing` — 3Bvs

- **Description**: avg 3bet faced (% pot)
- **Formula**: `(p_3bet_facing_bp / p_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_3bet_facing_cnt = SUM(HudCache.cnt_p_3bet_facing); p_3bet_facing_bp = SUM(HudCache.val_p_3bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `p_4bet_facing` — 4Bvs

- **Description**: avg 4bet faced (% pot)
- **Formula**: `(p_4bet_facing_bp / p_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_4bet_facing_cnt = SUM(HudCache.cnt_p_4bet_facing); p_4bet_facing_bp = SUM(HudCache.val_p_4bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `p_5bet_facing` — 5Bvs

- **Description**: avg 5bet faced (% pot)
- **Formula**: `(p_5bet_facing_bp / p_5bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_5bet_facing_cnt = SUM(HudCache.cnt_p_5bet_facing); p_5bet_facing_bp = SUM(HudCache.val_p_5bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `p_raise_facing` — PRvs

- **Description**: avg preflop raise faced (% pot)
- **Formula**: `(p_raise_facing_bp / p_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_raise_facing_cnt = SUM(HudCache.cnt_p_raise_facing); p_raise_facing_bp = SUM(HudCache.val_p_raise_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `p_raise_made` — PRz

- **Description**: avg preflop raise made (% pot)
- **Formula**: `(p_raise_made_bp / p_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_raise_made_cnt = SUM(HudCache.cnt_p_raise_made); p_raise_made_bp = SUM(HudCache.val_p_raise_made_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `p_raise_made_2` — PRz2

- **Description**: avg 2nd preflop raise made (% pot)
- **Formula**: `(p_raise_made_2_bp / p_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_raise_made_2_cnt = SUM(HudCache.cnt_p_raise_made_2); p_raise_made_2_bp = SUM(HudCache.val_p_raise_made_2_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `pfr` — p

- **Description**: Preflop/3rd street raise %
- **Formula**: `pfr / pfr_opp × 100`
- **SQL database field / logic**: pfr_opp = SUM(HudCache.street0AggrChance); pfr = SUM(HudCache.street0Aggr)
- **Detailed HUD text**: `pfr`
- **XML titles**: `PFR`
- **Note**: The HUD abbreviation `p` is shared with: `playerprofile`, `profit100`.

### `preflop_raise_frequency_by_position` — Preflop raise frequency by position

- **Description**: How often each seat raised when it had a preflop decision.
- **Formula**: `decisions matching the numerator {'response': ['raise', 'complete']} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'preflop'}; grouped by position
- **Note**: Analytics definition (metric raise_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### `raise_vs_preflop_3bet` — Rv3B

- **Description**: % raising facing a preflop 3-bet
- **Formula**: `cnt_p_raise_3bet / cnt_p_face_3bet × 100`
- **SQL database field / logic**: cnt_p_face_3bet = SUM(HudCache.cnt_p_face_3bet); cnt_p_raise_3bet = SUM(HudCache.cnt_p_raise_3bet)

### `raise_vs_preflop_4bet` — Rv4B

- **Description**: % raising facing a preflop 4-bet
- **Formula**: `cnt_p_raise_4bet / cnt_p_face_4bet × 100`
- **SQL database field / logic**: cnt_p_face_4bet = SUM(HudCache.cnt_p_face_4bet); cnt_p_raise_4bet = SUM(HudCache.cnt_p_raise_4bet)

### `raise_vs_preflop_squeeze` — RvSQ

- **Description**: % raising facing a preflop squeeze
- **Formula**: `cnt_p_raise_squeeze / cnt_p_face_squeeze × 100`
- **SQL database field / logic**: cnt_p_face_squeeze = SUM(HudCache.cnt_p_face_squeeze); cnt_p_raise_squeeze = SUM(HudCache.cnt_p_raise_squeeze)

### `rfi` — RFI

- **Description**: Raise first in (open raise).
- **Formula**: `100 * raisedFirstIn / raiseFirstInChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): raisedFirstIn, raiseFirstInChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `rfi_early_position` — rfi_ep

- **Description**: % RFI early position
- **Formula**: `rfi_ep / rfi_opp_ep × 100`
- **SQL database field / logic**: rfi_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.raiseFirstInChance ELSE 0 END); rfi_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.raisedFirstIn ELSE 0 END)
- **Detailed HUD text**: `rfi_early_pos`

### `rfi_late_position` — rfi_lp

- **Description**: % RFI late position
- **Formula**: `rfi_lp / rfi_opp_lp × 100`
- **SQL database field / logic**: rfi_opp_lp = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.raiseFirstInChance ELSE 0 END); rfi_lp = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.raisedFirstIn ELSE 0 END)
- **Detailed HUD text**: `rfi_late_pos`

### `rfi_middle_position` — rfi_mp

- **Description**: % RFI middle position
- **Formula**: `rfi_mp / rfi_opp_mp × 100`
- **SQL database field / logic**: rfi_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.raiseFirstInChance ELSE 0 END); rfi_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.raisedFirstIn ELSE 0 END)
- **Detailed HUD text**: `rfi_middle_pos`

### `rfi_total` — rfi

- **Description**: % raise first in
- **Formula**: `max(0, pfr − 3bet) / pfr_opp × 100`
- **SQL database field / logic**: pfr = SUM(HudCache.street0Aggr); pfr_opp = SUM(HudCache.street0AggrChance); 3bet is not selected by any HUD query, so it is always 0
- **Note**: In practice this equals PFR. The measured raise-first-in rate is `rfi_early_position`, `rfi_middle_position` and `rfi_late_position` pooled by the position queries.

### `squeeze` — SQZ

- **Description**: % squeeze preflop
- **Formula**: `sqz_0 / sqz_opp_0 × 100`
- **SQL database field / logic**: sqz_opp_0 = SUM(HudCache.street0_SqueezeChance); sqz_0 = SUM(HudCache.street0_SqueezeDone)
- **Detailed HUD text**: `SQZ_pf`

### `squeeze_bb` — SQZ BB

- **Description**: % SQZ BB preflop
- **Formula**: `sqz_bb / sqz_opp_bb × 100`
- **SQL database field / logic**: sqz_opp_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_SqueezeDone ELSE 0 END)

### `squeeze_btn` — SQZ BTN

- **Description**: % SQZ BTN preflop
- **Formula**: `sqz_btn / sqz_opp_btn × 100`
- **SQL database field / logic**: sqz_opp_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_SqueezeDone ELSE 0 END)

### `squeeze_co` — SQZ CO

- **Description**: % SQZ CO preflop
- **Formula**: `sqz_co / sqz_opp_co × 100`
- **SQL database field / logic**: sqz_opp_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_SqueezeDone ELSE 0 END)

### `squeeze_ep` — SQZ EP

- **Description**: % SQZ EP preflop
- **Formula**: `sqz_ep / sqz_opp_ep × 100`
- **SQL database field / logic**: sqz_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_SqueezeDone ELSE 0 END)

### `squeeze_mp` — SQZ MP

- **Description**: % SQZ MP preflop
- **Formula**: `sqz_mp / sqz_opp_mp × 100`
- **SQL database field / logic**: sqz_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_SqueezeDone ELSE 0 END)

### `squeeze_range` — SQZR

- **Description**: squeeze range
- **Formula**: `sqz_0 / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); sqz_0 = SUM(HudCache.street0_SqueezeDone)

### `squeeze_sb` — SQZ SB

- **Description**: % SQZ SB preflop
- **Formula**: `sqz_sb / sqz_opp_sb × 100`
- **SQL database field / logic**: sqz_opp_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_SqueezeDone ELSE 0 END)

### `straddle` — Str

- **Description**: % straddle
- **Formula**: `straddle_done / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); straddle_done = SUM(HudCache.flg_blind_k)
- **Note**: The HUD abbreviation `Str` is shared with: `aof_straight`.

### `three_B` — 3B

- **Description**: % 3 bet preflop/3rd street
- **Formula**: `tb_0 / tb_opp_0 × 100`
- **SQL database field / logic**: tb_opp_0 = SUM(HudCache.street0_3BChance); tb_0 = SUM(HudCache.street0_3BDone)
- **Detailed HUD text**: `3B_pf`
- **XML titles**: `PF3`

### `three_bet` — 3Bet

- **Description**: Preflop 3-bet.
- **Formula**: `100 * street0_3BDone / street0_3BChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street0_3BDone, street0_3BChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `three_bet_bb` — 3B BB

- **Description**: % 3B BB preflop
- **Formula**: `tb_bb / tb_opp_bb × 100`
- **SQL database field / logic**: tb_opp_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_3BChance ELSE 0 END); tb_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_3BDone ELSE 0 END)

### `three_bet_btn` — 3B BTN

- **Description**: % 3B BTN preflop
- **Formula**: `tb_btn / tb_opp_btn × 100`
- **SQL database field / logic**: tb_opp_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_3BChance ELSE 0 END); tb_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_3BDone ELSE 0 END)

### `three_bet_co` — 3B CO

- **Description**: % 3B CO preflop
- **Formula**: `tb_co / tb_opp_co × 100`
- **SQL database field / logic**: tb_opp_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_3BChance ELSE 0 END); tb_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_3BDone ELSE 0 END)

### `three_bet_ep` — 3B EP

- **Description**: % 3B EP preflop
- **Formula**: `tb_ep / tb_opp_ep × 100`
- **SQL database field / logic**: tb_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_3BChance ELSE 0 END); tb_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_3BDone ELSE 0 END)

### `three_bet_mp` — 3B MP

- **Description**: % 3B MP preflop
- **Formula**: `tb_mp / tb_opp_mp × 100`
- **SQL database field / logic**: tb_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_3BChance ELSE 0 END); tb_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_3BDone ELSE 0 END)

### `three_bet_range` — 3BR

- **Description**: 3-bet range
- **Formula**: `tb_0 / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); tb_0 = SUM(HudCache.street0_3BDone)

### `three_bet_sb` — 3B SB

- **Description**: % 3B SB preflop
- **Formula**: `tb_sb / tb_opp_sb × 100`
- **SQL database field / logic**: tb_opp_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_3BChance ELSE 0 END); tb_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_3BDone ELSE 0 END)

### `vpip` — v

- **Description**: Voluntarily put in preflop/3rd street %
- **Formula**: `vpip / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI)
- **Detailed HUD text**: `vpip`
- **XML titles**: `VPIP`
- **Note**: The HUD abbreviation `v` is shared with: `bbstack`.

### `vpip_pfr_ratio` — v/p

- **Description**: VPIP/PFR ratio
- **Formula**: `(vpip / vpip_opp) / (pfr / pfr_opp)`
- **SQL database field / logic**: vpip = SUM(HudCache.street0VPI); vpip_opp = SUM(HudCache.street0VPIChance); pfr = SUM(HudCache.street0Aggr); pfr_opp = SUM(HudCache.street0AggrChance)
- **Detailed HUD text**: `vpip/pfr`
- **Note**: A plain ratio of the two percentages (not multiplied by 100); shows infinity when PFR is 0.

## Steal and blinds

### `amt_blind` — Blind

- **Description**: avg blinds posted
- **Formula**: `0.01 × amt_blind / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_blind = SUM(HudCache.amt_blind)

### `call_vs_steal` — cvs

- **Description**: % call vs steal (deprecated)
- **Formula**: `no data (deprecated)`
- **SQL database field / logic**: none: needs data about other players that HudCache cannot aggregate
- **Status**: deprecated

### `f_BB_steal` — fBB

- **Description**: % folded BB to steal
- **Formula**: `bbnotdef / bbstolen × 100`
- **SQL database field / logic**: bbstolen = SUM(HudCache.foldBbToStealChance); bbnotdef = SUM(HudCache.foldedBbToSteal)
- **Detailed HUD text**: `fBB_s`

### `f_SB_steal` — fSB

- **Description**: % folded SB to steal
- **Formula**: `sbnotdef / sbstolen × 100`
- **SQL database field / logic**: sbstolen = SUM(HudCache.foldSbToStealChance); sbnotdef = SUM(HudCache.foldedSbToSteal)
- **Detailed HUD text**: `fSB_s`

### `f_steal` — fB

- **Description**: % folded blind to steal
- **Formula**: `(sbnotdef + bbnotdef) / (sbstolen + bbstolen) × 100`
- **SQL database field / logic**: sbnotdef = SUM(HudCache.foldedSbToSteal); bbnotdef = SUM(HudCache.foldedBbToSteal); sbstolen = SUM(HudCache.foldSbToStealChance); bbstolen = SUM(HudCache.foldBbToStealChance)
- **Detailed HUD text**: `fB_s`

### `fold_bb_to_steal` — Fold BB to Steal

- **Description**: Fold the big blind facing a steal attempt.
- **Formula**: `100 * foldedBbToSteal / foldBbToStealChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): foldedBbToSteal, foldBbToStealChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `raiseToSteal` — RST

- **Description**: % raise to steal
- **Formula**: `rts / rts_opp × 100`
- **SQL database field / logic**: rts_opp = SUM(HudCache.raiseToStealChance); rts = SUM(HudCache.raiseToStealDone)
- **Detailed HUD text**: `RST_pf`

### `resteal` — resteal

- **Description**: % resteal
- **Formula**: `(0.7 × tb_0) / (0.6 × tb_opp_0) × 100`
- **SQL database field / logic**: tb_0 = SUM(HudCache.street0_3BDone); tb_opp_0 = SUM(HudCache.street0_3BChance)
- **Status**: estimate
- **Note**: An estimate built from the 3-bet counts with fixed 0.7 and 0.6 factors (the share assumed to be from the blinds); it is not a count of re-steals. Use `raiseToSteal` for the measured value.

### `s_steal` — s_st

- **Description**: % steal success
- **Formula**: `suc_st / steal × 100`
- **SQL database field / logic**: steal = SUM(HudCache.stealDone); suc_st = SUM(HudCache.success_Steal)
- **Detailed HUD text**: `s_steal`

### `steal` — st

- **Description**: % steal attempted
- **Formula**: `steal / steal_opp × 100`
- **SQL database field / logic**: steal_opp = SUM(HudCache.stealChance); steal = SUM(HudCache.stealDone)
- **Detailed HUD text**: `steal`
- **XML titles**: `Steals`

### `three_bet_vs_steal` — 3bvs

- **Description**: % 3bet vs steal (deprecated)
- **Formula**: `no data (deprecated)`
- **SQL database field / logic**: none: needs data about other players that HudCache cannot aggregate
- **Status**: deprecated

## Flop / 4th street

### `a_freq1` — a1

- **Description**: Aggression frequency flop/4th street
- **Formula**: `aggr_1 / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); aggr_1 = SUM(HudCache.street1Aggr)
- **Detailed HUD text**: `a_fq_1`
- **XML titles**: `FlAFq`

### `avg_bet_size_flop` — avg_bet_f

- **Description**: avg bet size flop (deprecated)
- **Formula**: `no data (deprecated); see `f_bet_made``
- **SQL database field / logic**: none
- **Status**: deprecated

### `bet_frequency_flop` — bet_f

- **Description**: % bet frequency flop
- **Formula**: `street1Bets / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); street1Bets (not selected by the HUD queries)
- **Detailed HUD text**: `bet_freq_flop`
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### `call_vs_flop_3bet` — CvF3B

- **Description**: % calling facing a flop 3-bet
- **Formula**: `cnt_f_call_3bet / cnt_f_face_3bet × 100`
- **SQL database field / logic**: cnt_f_face_3bet = SUM(HudCache.cnt_f_face_3bet); cnt_f_call_3bet = SUM(HudCache.cnt_f_call_3bet)

### `call_vs_flop_4bet` — CvF4B

- **Description**: % calling facing a flop 4-bet
- **Formula**: `cnt_f_call_4bet / cnt_f_face_4bet × 100`
- **SQL database field / logic**: cnt_f_face_4bet = SUM(HudCache.cnt_f_face_4bet); cnt_f_call_4bet = SUM(HudCache.cnt_f_call_4bet)

### `call_vs_flop_cbet` — CvFCB

- **Description**: % calling facing a flop c-bet
- **Formula**: `cnt_f_call_cbet / cnt_f_face_cbet × 100`
- **SQL database field / logic**: cnt_f_face_cbet = SUM(HudCache.cnt_f_face_cbet); cnt_f_call_cbet = SUM(HudCache.cnt_f_call_cbet)

### `call_vs_flop_donk` — CvFDk

- **Description**: % calling facing a flop donk bet
- **Formula**: `cnt_f_call_donk / cnt_f_face_donk × 100`
- **SQL database field / logic**: cnt_f_face_donk = SUM(HudCache.cnt_f_face_donk); cnt_f_call_donk = SUM(HudCache.cnt_f_call_donk)

### `cb1` — cb1

- **Description**: % continuation bet flop/4th street
- **Formula**: `cb_1 / cb_opp_1 × 100`
- **SQL database field / logic**: cb_opp_1 = SUM(HudCache.street1CBChance); cb_1 = SUM(HudCache.street1CBDone)
- **Detailed HUD text**: `cb_1`

### `cb_ip` — cb_ip

- **Description**: % c-bet in position
- **Formula**: `cb_1 / cb_opp_1 × 100, only over hands played in position on the flop`
- **SQL database field / logic**: cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); street1InPosition = SUM(HudCache.street1InPosition)
- **Detailed HUD text**: `cbet_in_position`
- **Note**: Flop c-bet when in position. Positions are split by `cbet_by_position` (stats_postflop.py) with the in-position share of the sample.

### `cb_oop` — cb_oop

- **Description**: % c-bet out of position
- **Formula**: `cb_1 / cb_opp_1 × 100, only over hands played out of position on the flop`
- **SQL database field / logic**: cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); street1InPosition = SUM(HudCache.street1InPosition)
- **Note**: Flop c-bet when out of position; counterpart of `cb_ip`.

### `cbet_flop` — C-bet Flop

- **Description**: Continuation bet on the flop.
- **Formula**: `100 * street1CBDone / street1CBChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street1CBDone, street1CBChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `cr1` — cr1

- **Description**: % check-raise flop/4th street
- **Formula**: `cr_1 / ccr_opp_1 × 100`
- **SQL database field / logic**: ccr_opp_1 = SUM(HudCache.street1CheckCallRaiseChance); cr_1 = SUM(HudCache.street1CheckRaiseDone)
- **Detailed HUD text**: `cr_1`

### `dbr1` — dbr1

- **Description**: % DonkBetAndRaise flop/4th street
- **Formula**: `(aggr_1 − cb_1) / (saw_f − cb_opp_1)`
- **SQL database field / logic**: aggr_1 = SUM(HudCache.street1Aggr); cb_1 = SUM(HudCache.street1CBDone); saw_f = SUM(HudCache.street1Seen); cb_opp_1 = SUM(HudCache.street1CBChance)

### `f_2bet_facing` — F2vs

- **Description**: avg flop 2bet faced (% pot)
- **Formula**: `(f_2bet_facing_bp / f_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_2bet_facing_cnt = SUM(HudCache.cnt_f_2bet_facing); f_2bet_facing_bp = SUM(HudCache.val_f_2bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_3bet_facing` — F3vs

- **Description**: avg flop 3bet faced (% pot)
- **Formula**: `(f_3bet_facing_bp / f_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_3bet_facing_cnt = SUM(HudCache.cnt_f_3bet_facing); f_3bet_facing_bp = SUM(HudCache.val_f_3bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_4bet_facing` — F4vs

- **Description**: avg flop 4bet faced (% pot)
- **Formula**: `(f_4bet_facing_bp / f_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_4bet_facing_cnt = SUM(HudCache.cnt_f_4bet_facing); f_4bet_facing_bp = SUM(HudCache.val_f_4bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_bet_facing` — FBvs

- **Description**: avg flop bet faced (% pot)
- **Formula**: `(f_bet_facing_bp / f_bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_bet_facing_cnt = SUM(HudCache.cnt_f_bet_facing); f_bet_facing_bp = SUM(HudCache.val_f_bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_bet_made` — FBet

- **Description**: avg flop bet made (% pot)
- **Formula**: `(f_bet_made_bp / f_bet_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_bet_made_cnt = SUM(HudCache.cnt_f_bet_made); f_bet_made_bp = SUM(HudCache.val_f_bet_made_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_cb1` — f_cb1

- **Description**: % fold to continuation bet flop/4th street
- **Formula**: `f_cb_1 / f_cb_opp_1 × 100`
- **SQL database field / logic**: f_cb_opp_1 = SUM(HudCache.foldToStreet1CBChance); f_cb_1 = SUM(HudCache.foldToStreet1CBDone)
- **Detailed HUD text**: `f_cb_1`
- **Note**: The HUD abbreviation `f_cb1` is shared with: `fold_to_cbet_flop`.

### `f_dbr1` — f_dbr1

- **Description**: % Fold to DonkBetAndRaise flop/4th street
- **Formula**: `(f_freq_1 − f_cb_1) / (was_raised_1 − f_cb_opp_1) × 100`
- **SQL database field / logic**: f_freq_1 = SUM(HudCache.foldToOtherRaisedStreet1); f_cb_1 = SUM(HudCache.foldToStreet1CBDone); was_raised_1 = SUM(HudCache.otherRaisedStreet1); f_cb_opp_1 = SUM(HudCache.foldToStreet1CBChance)

### `f_raise_facing` — FRvs

- **Description**: avg flop raise faced (% pot)
- **Formula**: `(f_raise_facing_bp / f_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_raise_facing_cnt = SUM(HudCache.cnt_f_raise_facing); f_raise_facing_bp = SUM(HudCache.val_f_raise_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_raise_made` — FRz

- **Description**: avg flop raise made (% pot)
- **Formula**: `(f_raise_made_bp / f_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_raise_made_cnt = SUM(HudCache.cnt_f_raise_made); f_raise_made_bp = SUM(HudCache.val_f_raise_made_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_raise_made_2` — FRz2

- **Description**: avg 2nd flop raise made (% pot)
- **Formula**: `(f_raise_made_2_bp / f_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_raise_made_2_cnt = SUM(HudCache.cnt_f_raise_made_2); f_raise_made_2_bp = SUM(HudCache.val_f_raise_made_2_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `f_spr` — fSPR

- **Description**: avg flop SPR
- **Formula**: `0.01 × f_spr_val / f_spr_cnt`
- **SQL database field / logic**: f_spr_cnt = SUM(HudCache.cnt_f_spr); f_spr_val = SUM(HudCache.val_f_spr)

### `face_raise_flop` — FvRf

- **Description**: % face raise flop
- **Formula**: `f_face_raise / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); f_face_raise = SUM(HudCache.street1FaceRaise)

### `ffreq1` — ff1

- **Description**: % fold frequency flop/4th street
- **Formula**: `f_freq_1 / was_raised_1 × 100`
- **SQL database field / logic**: was_raised_1 = SUM(HudCache.otherRaisedStreet1); f_freq_1 = SUM(HudCache.foldToOtherRaisedStreet1)
- **Detailed HUD text**: `ff_1`

### `first_raise_flop` — 1Rf

- **Description**: % first raise flop
- **Formula**: `f_first_raise / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); f_first_raise = SUM(HudCache.street1FirstRaise)

### `fold_flop` — Fldf

- **Description**: % fold flop
- **Formula**: `f_fold / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); f_fold = SUM(HudCache.flg_f_fold)

### `fold_to_cbet_flop` — f_cb1

- **Description**: % fold to continuation bet flop/4th street
- **Formula**: `f_cb_1 / f_cb_opp_1 × 100`
- **SQL database field / logic**: f_cb_opp_1 = SUM(HudCache.foldToStreet1CBChance); f_cb_1 = SUM(HudCache.foldToStreet1CBDone)
- **Detailed HUD text**: `f_cb_1`
- **Note**: The HUD abbreviation `f_cb1` is shared with: `f_cb1`.

### `fold_to_cbet_flop` — Fold to flop c-bet

- **Description**: How often the player folded when facing a continuation bet on the flop.
- **Formula**: `decisions matching the numerator {'response': 'fold'} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'flop', 'situation': 'facing_cbet'}
- **Note**: Analytics definition (metric fold_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### `fold_to_cbet_flop_by_size` — Fold to flop c-bet by bet size

- **Description**: How often the player folded to a flop c-bet, split by the size faced.
- **Formula**: `decisions matching the numerator {'response': 'fold'} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'flop', 'situation': 'facing_cbet'}; grouped by facing_sizing_bucket
- **Note**: Analytics definition (metric fold_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### `fold_to_three_B_flop` — FF3B

- **Description**: % fold to flop 3bet
- **Formula**: `ff3b / ff3b_opp × 100`
- **SQL database field / logic**: ff3b_opp = SUM(HudCache.street1_FoldTo3BChance); ff3b = SUM(HudCache.street1_FoldTo3BDone)

### `fold_vs_flop_3bet` — FvF3B

- **Description**: % folding facing a flop 3-bet
- **Formula**: `(cnt_f_face_3bet − cnt_f_call_3bet − cnt_f_raise_3bet) / cnt_f_face_3bet × 100`
- **SQL database field / logic**: cnt_f_face_3bet = SUM(HudCache.cnt_f_face_3bet); cnt_f_call_3bet = SUM(HudCache.cnt_f_call_3bet); cnt_f_raise_3bet = SUM(HudCache.cnt_f_raise_3bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_flop_4bet` — FvF4B

- **Description**: % folding facing a flop 4-bet
- **Formula**: `(cnt_f_face_4bet − cnt_f_call_4bet − cnt_f_raise_4bet) / cnt_f_face_4bet × 100`
- **SQL database field / logic**: cnt_f_face_4bet = SUM(HudCache.cnt_f_face_4bet); cnt_f_call_4bet = SUM(HudCache.cnt_f_call_4bet); cnt_f_raise_4bet = SUM(HudCache.cnt_f_raise_4bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_flop_cbet` — FvFCB

- **Description**: % folding facing a flop c-bet
- **Formula**: `(cnt_f_face_cbet − cnt_f_call_cbet − cnt_f_raise_cbet) / cnt_f_face_cbet × 100`
- **SQL database field / logic**: cnt_f_face_cbet = SUM(HudCache.cnt_f_face_cbet); cnt_f_call_cbet = SUM(HudCache.cnt_f_call_cbet); cnt_f_raise_cbet = SUM(HudCache.cnt_f_raise_cbet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_flop_donk` — FvFDk

- **Description**: % folding facing a flop donk bet
- **Formula**: `(cnt_f_face_donk − cnt_f_call_donk − cnt_f_raise_donk) / cnt_f_face_donk × 100`
- **SQL database field / logic**: cnt_f_face_donk = SUM(HudCache.cnt_f_face_donk); cnt_f_call_donk = SUM(HudCache.cnt_f_call_donk); cnt_f_raise_donk = SUM(HudCache.cnt_f_raise_donk)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `four_B_flop` — F4B

- **Description**: % 4 bet flop
- **Formula**: `fl4b / fl4b_opp × 100`
- **SQL database field / logic**: fl4b_opp = SUM(HudCache.street1_4BChance); fl4b = SUM(HudCache.street1_4BDone)
- **Note**: The HUD abbreviation `F4B` is shared with: `f_4bet`.

### `open_flop` — OPf

- **Description**: % open flop
- **Formula**: `flopen / flopen_opp × 100`
- **SQL database field / logic**: flopen_opp = SUM(HudCache.street1OpenChance); flopen = SUM(HudCache.street1OpenDone)

### `probe_bet` — probe

- **Description**: % probe bet flop
- **Formula**: `min(street1Bets, saw_f − cb_1) / (saw_f − cb_1) × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); cb_1 = SUM(HudCache.street1CBDone); street1Bets = SUM(HudCache.street1Bets)
- **Status**: input-missing
- **Note**: Flop probe: bets over the flops seen where the player did not c-bet. Reads `street1Bets`, which the HUD queries expose as `bet_1`.

### `raise_frequency_flop` — raise_f

- **Description**: % raise frequency flop
- **Formula**: `street1Raises / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); street1Raises (not selected by the HUD queries)
- **Detailed HUD text**: `raise_freq_flop`
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### `raise_vs_flop_3bet` — RvF3B

- **Description**: % raising facing a flop 3-bet
- **Formula**: `cnt_f_raise_3bet / cnt_f_face_3bet × 100`
- **SQL database field / logic**: cnt_f_face_3bet = SUM(HudCache.cnt_f_face_3bet); cnt_f_raise_3bet = SUM(HudCache.cnt_f_raise_3bet)

### `raise_vs_flop_4bet` — RvF4B

- **Description**: % raising facing a flop 4-bet
- **Formula**: `cnt_f_raise_4bet / cnt_f_face_4bet × 100`
- **SQL database field / logic**: cnt_f_face_4bet = SUM(HudCache.cnt_f_face_4bet); cnt_f_raise_4bet = SUM(HudCache.cnt_f_raise_4bet)

### `raise_vs_flop_cbet` — RvFCB

- **Description**: % raising facing a flop c-bet
- **Formula**: `cnt_f_raise_cbet / cnt_f_face_cbet × 100`
- **SQL database field / logic**: cnt_f_face_cbet = SUM(HudCache.cnt_f_face_cbet); cnt_f_raise_cbet = SUM(HudCache.cnt_f_raise_cbet)

### `raise_vs_flop_donk` — RvFDk

- **Description**: % raising facing a flop donk bet
- **Formula**: `cnt_f_raise_donk / cnt_f_face_donk × 100`
- **SQL database field / logic**: cnt_f_face_donk = SUM(HudCache.cnt_f_face_donk); cnt_f_raise_donk = SUM(HudCache.cnt_f_raise_donk)

### `three_B_flop` — F3B

- **Description**: % 3 bet flop
- **Formula**: `fl3b / fl3b_opp × 100`
- **SQL database field / logic**: fl3b_opp = SUM(HudCache.street1_3BChance); fl3b = SUM(HudCache.street1_3BDone)
- **Note**: The HUD abbreviation `F3B` is shared with: `f_3bet`.

## Turn / 5th street

### `a_freq2` — a2

- **Description**: Aggression frequency turn/5th street
- **Formula**: `aggr_2 / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); aggr_2 = SUM(HudCache.street2Aggr)
- **Detailed HUD text**: `a_fq_2`
- **XML titles**: `TuAFq`

### `avg_bet_size_turn` — avg_bet_t

- **Description**: avg bet size turn (deprecated)
- **Formula**: `no data (deprecated); see `t_bet_made``
- **SQL database field / logic**: none
- **Status**: deprecated

### `bet_frequency_turn` — bet_t

- **Description**: % bet frequency turn
- **Formula**: `street2Bets / saw_t × 100`
- **SQL database field / logic**: saw_t (not selected by the HUD queries); street2Bets (not selected by the HUD queries)
- **Detailed HUD text**: `bet_freq_turn`
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### `call_float_turn` — CvTFl

- **Description**: % calling facing the turn barrel, having called the flop c-bet in position
- **Formula**: `cnt_t_call_float / cnt_t_face_float × 100`
- **SQL database field / logic**: cnt_t_face_float = SUM(HudCache.cnt_t_face_float); cnt_t_call_float = SUM(HudCache.cnt_t_call_float)

### `call_vs_turn_3bet` — CvT3B

- **Description**: % calling facing a turn 3-bet
- **Formula**: `cnt_t_call_3bet / cnt_t_face_3bet × 100`
- **SQL database field / logic**: cnt_t_face_3bet = SUM(HudCache.cnt_t_face_3bet); cnt_t_call_3bet = SUM(HudCache.cnt_t_call_3bet)

### `call_vs_turn_4bet` — CvT4B

- **Description**: % calling facing a turn 4-bet
- **Formula**: `cnt_t_call_4bet / cnt_t_face_4bet × 100`
- **SQL database field / logic**: cnt_t_face_4bet = SUM(HudCache.cnt_t_face_4bet); cnt_t_call_4bet = SUM(HudCache.cnt_t_call_4bet)

### `call_vs_turn_cbet` — CvTCB

- **Description**: % calling facing a turn c-bet
- **Formula**: `cnt_t_call_cbet / cnt_t_face_cbet × 100`
- **SQL database field / logic**: cnt_t_face_cbet = SUM(HudCache.cnt_t_face_cbet); cnt_t_call_cbet = SUM(HudCache.cnt_t_call_cbet)

### `call_vs_turn_donk` — CvTDk

- **Description**: % calling facing a turn donk bet
- **Formula**: `cnt_t_call_donk / cnt_t_face_donk × 100`
- **SQL database field / logic**: cnt_t_face_donk = SUM(HudCache.cnt_t_face_donk); cnt_t_call_donk = SUM(HudCache.cnt_t_call_donk)

### `cb2` — cb2

- **Description**: % continuation bet turn/5th street
- **Formula**: `cb_2 / cb_opp_2 × 100`
- **SQL database field / logic**: cb_opp_2 = SUM(HudCache.street2CBChance); cb_2 = SUM(HudCache.street2CBDone)
- **Detailed HUD text**: `cb_2`

### `cbet_turn` — C-bet Turn

- **Description**: Continuation bet on the turn.
- **Formula**: `100 * street2CBDone / street2CBChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street2CBDone, street2CBChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `cr2` — cr2

- **Description**: % check-raise turn/5th street
- **Formula**: `cr_2 / ccr_opp_2 × 100`
- **SQL database field / logic**: ccr_opp_2 = SUM(HudCache.street2CheckCallRaiseChance); cr_2 = SUM(HudCache.street2CheckRaiseDone)
- **Detailed HUD text**: `cr_2`

### `dbr2` — dbr2

- **Description**: % DonkBetAndRaise turn/5th street
- **Formula**: `(aggr_2 − cb_2) / (saw_2 − cb_opp_2)`
- **SQL database field / logic**: aggr_2 = SUM(HudCache.street2Aggr); cb_2 = SUM(HudCache.street2CBDone); saw_2 = SUM(HudCache.street2Seen); cb_opp_2 = SUM(HudCache.street2CBChance)

### `delayed_cbet_turn` — Delayed C-bet Turn

- **Description**: Bet the turn after checking the flop as the preflop aggressor.
- **Formula**: `100 * street2DelayedCBDone / street2DelayedCBChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street2DelayedCBDone, street2DelayedCBChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `f_cb2` — f_cb2

- **Description**: % fold to continuation bet turn/5th street
- **Formula**: `f_cb_2 / f_cb_opp_2 × 100`
- **SQL database field / logic**: f_cb_opp_2 = SUM(HudCache.foldToStreet2CBChance); f_cb_2 = SUM(HudCache.foldToStreet2CBDone)
- **Detailed HUD text**: `f_cb_2`
- **Note**: The HUD abbreviation `f_cb2` is shared with: `fold_to_cbet_turn`.

### `f_dbr2` — f_dbr2

- **Description**: % Fold to DonkBetAndRaise turn
- **Formula**: `(f_freq_2 − f_cb_2) / (was_raised_2 − f_cb_opp_2) × 100`
- **SQL database field / logic**: f_freq_2 = SUM(HudCache.foldToOtherRaisedStreet2); f_cb_2 = SUM(HudCache.foldToStreet2CBDone); was_raised_2 = SUM(HudCache.otherRaisedStreet2); f_cb_opp_2 = SUM(HudCache.foldToStreet2CBChance)

### `face_raise_turn` — FvRt

- **Description**: % face raise turn
- **Formula**: `t_face_raise / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); t_face_raise = SUM(HudCache.street2FaceRaise)

### `ffreq2` — ff2

- **Description**: % fold frequency turn/5th street
- **Formula**: `f_freq_2 / was_raised_2 × 100`
- **SQL database field / logic**: was_raised_2 = SUM(HudCache.otherRaisedStreet2); f_freq_2 = SUM(HudCache.foldToOtherRaisedStreet2)
- **Detailed HUD text**: `ff_2`

### `first_raise_turn` — 1Rt

- **Description**: % first raise turn
- **Formula**: `t_first_raise / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); t_first_raise = SUM(HudCache.street2FirstRaise)

### `float_bet` — float

- **Description**: % float bet turn
- **Formula**: `floats / opportunities × 100, from street1InPosition, street1Calls, saw_t and street2Bets`
- **SQL database field / logic**: street1InPosition = SUM(HudCache.street1InPosition); street1Calls = SUM(HudCache.street1Calls); saw_t = SUM(HudCache.street2Seen); street2Bets = SUM(HudCache.street2Bets)
- **Status**: input-missing
- **Note**: Turn bet after calling the flop in position. Several inputs use names the HUD queries expose differently (`call_1`, `saw_2`, `bet_2`).

### `float_turn` — FltT

- **Description**: % float turn
- **Formula**: `float_turn_done / float_turn_chance × 100`
- **SQL database field / logic**: float_turn_chance = SUM(HudCache.flg_t_float_opp); float_turn_done = SUM(HudCache.flg_t_float)

### `fold_float_turn` — FvTFl

- **Description**: % folding facing the turn barrel, having called the flop c-bet in position
- **Formula**: `(cnt_t_face_float − cnt_t_call_float − cnt_t_raise_float) / cnt_t_face_float × 100`
- **SQL database field / logic**: cnt_t_face_float = SUM(HudCache.cnt_t_face_float); cnt_t_call_float = SUM(HudCache.cnt_t_call_float); cnt_t_raise_float = SUM(HudCache.cnt_t_raise_float)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_to_cbet_turn` — f_cb2

- **Description**: % fold to continuation bet turn/5th street
- **Formula**: `f_cb_2 / f_cb_opp_2 × 100`
- **SQL database field / logic**: f_cb_opp_2 = SUM(HudCache.foldToStreet2CBChance); f_cb_2 = SUM(HudCache.foldToStreet2CBDone)
- **Detailed HUD text**: `f_cb_2`
- **Note**: The HUD abbreviation `f_cb2` is shared with: `f_cb2`.

### `fold_to_three_B_turn` — FT3B

- **Description**: % fold to turn 3bet
- **Formula**: `ft3b / ft3b_opp × 100`
- **SQL database field / logic**: ft3b_opp = SUM(HudCache.street2_FoldTo3BChance); ft3b = SUM(HudCache.street2_FoldTo3BDone)

### `fold_turn` — Fldt

- **Description**: % fold turn
- **Formula**: `t_fold / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); t_fold = SUM(HudCache.flg_t_fold)

### `fold_vs_turn_3bet` — FvT3B

- **Description**: % folding facing a turn 3-bet
- **Formula**: `(cnt_t_face_3bet − cnt_t_call_3bet − cnt_t_raise_3bet) / cnt_t_face_3bet × 100`
- **SQL database field / logic**: cnt_t_face_3bet = SUM(HudCache.cnt_t_face_3bet); cnt_t_call_3bet = SUM(HudCache.cnt_t_call_3bet); cnt_t_raise_3bet = SUM(HudCache.cnt_t_raise_3bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_turn_4bet` — FvT4B

- **Description**: % folding facing a turn 4-bet
- **Formula**: `(cnt_t_face_4bet − cnt_t_call_4bet − cnt_t_raise_4bet) / cnt_t_face_4bet × 100`
- **SQL database field / logic**: cnt_t_face_4bet = SUM(HudCache.cnt_t_face_4bet); cnt_t_call_4bet = SUM(HudCache.cnt_t_call_4bet); cnt_t_raise_4bet = SUM(HudCache.cnt_t_raise_4bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_turn_cbet` — FvTCB

- **Description**: % folding facing a turn c-bet
- **Formula**: `(cnt_t_face_cbet − cnt_t_call_cbet − cnt_t_raise_cbet) / cnt_t_face_cbet × 100`
- **SQL database field / logic**: cnt_t_face_cbet = SUM(HudCache.cnt_t_face_cbet); cnt_t_call_cbet = SUM(HudCache.cnt_t_call_cbet); cnt_t_raise_cbet = SUM(HudCache.cnt_t_raise_cbet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_turn_donk` — FvTDk

- **Description**: % folding facing a turn donk bet
- **Formula**: `(cnt_t_face_donk − cnt_t_call_donk − cnt_t_raise_donk) / cnt_t_face_donk × 100`
- **SQL database field / logic**: cnt_t_face_donk = SUM(HudCache.cnt_t_face_donk); cnt_t_call_donk = SUM(HudCache.cnt_t_call_donk); cnt_t_raise_donk = SUM(HudCache.cnt_t_raise_donk)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `four_B_turn` — T4B

- **Description**: % 4 bet turn
- **Formula**: `tn4b / tn4b_opp × 100`
- **SQL database field / logic**: tn4b_opp = SUM(HudCache.street2_4BChance); tn4b = SUM(HudCache.street2_4BDone)

### `open_turn` — OPt

- **Description**: % open turn
- **Formula**: `tnopen / tnopen_opp × 100`
- **SQL database field / logic**: tnopen_opp = SUM(HudCache.street2OpenChance); tnopen = SUM(HudCache.street2OpenDone)

### `probe_bet_turn` — probe_t

- **Description**: % probe bet turn
- **Formula**: `min(street2Bets, saw_t − cb_2) / (saw_t − cb_2) × 100`
- **SQL database field / logic**: saw_t = SUM(HudCache.street2Seen); cb_2 = SUM(HudCache.street2CBDone); street2Bets = SUM(HudCache.street2Bets)
- **Status**: input-missing
- **Note**: Turn probe. The HUD queries name the turn-seen count `saw_2` and the bet count `bet_2`, not the keys this stat reads.

### `probe_turn` — Probe Turn

- **Description**: Bet the turn (as non-aggressor) after the preflop raiser checked the flop.
- **Formula**: `100 * street2ProbeDone / street2ProbeChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street2ProbeDone, street2ProbeChance
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `raise_float_turn` — RvTFl

- **Description**: % raising facing the turn barrel, having called the flop c-bet in position
- **Formula**: `cnt_t_raise_float / cnt_t_face_float × 100`
- **SQL database field / logic**: cnt_t_face_float = SUM(HudCache.cnt_t_face_float); cnt_t_raise_float = SUM(HudCache.cnt_t_raise_float)

### `raise_frequency_turn` — raise_t

- **Description**: % raise frequency turn
- **Formula**: `street2Raises / saw_t × 100`
- **SQL database field / logic**: saw_t (not selected by the HUD queries); street2Raises (not selected by the HUD queries)
- **Detailed HUD text**: `raise_freq_turn`
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### `raise_vs_turn_3bet` — RvT3B

- **Description**: % raising facing a turn 3-bet
- **Formula**: `cnt_t_raise_3bet / cnt_t_face_3bet × 100`
- **SQL database field / logic**: cnt_t_face_3bet = SUM(HudCache.cnt_t_face_3bet); cnt_t_raise_3bet = SUM(HudCache.cnt_t_raise_3bet)

### `raise_vs_turn_4bet` — RvT4B

- **Description**: % raising facing a turn 4-bet
- **Formula**: `cnt_t_raise_4bet / cnt_t_face_4bet × 100`
- **SQL database field / logic**: cnt_t_face_4bet = SUM(HudCache.cnt_t_face_4bet); cnt_t_raise_4bet = SUM(HudCache.cnt_t_raise_4bet)

### `raise_vs_turn_cbet` — RvTCB

- **Description**: % raising facing a turn c-bet
- **Formula**: `cnt_t_raise_cbet / cnt_t_face_cbet × 100`
- **SQL database field / logic**: cnt_t_face_cbet = SUM(HudCache.cnt_t_face_cbet); cnt_t_raise_cbet = SUM(HudCache.cnt_t_raise_cbet)

### `raise_vs_turn_donk` — RvTDk

- **Description**: % raising facing a turn donk bet
- **Formula**: `cnt_t_raise_donk / cnt_t_face_donk × 100`
- **SQL database field / logic**: cnt_t_face_donk = SUM(HudCache.cnt_t_face_donk); cnt_t_raise_donk = SUM(HudCache.cnt_t_raise_donk)

### `t_2bet_facing` — T2vs

- **Description**: avg turn 2bet faced (% pot)
- **Formula**: `(t_2bet_facing_bp / t_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_2bet_facing_cnt = SUM(HudCache.cnt_t_2bet_facing); t_2bet_facing_bp = SUM(HudCache.val_t_2bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_3bet_facing` — T3vs

- **Description**: avg turn 3bet faced (% pot)
- **Formula**: `(t_3bet_facing_bp / t_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_3bet_facing_cnt = SUM(HudCache.cnt_t_3bet_facing); t_3bet_facing_bp = SUM(HudCache.val_t_3bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_4bet_facing` — T4vs

- **Description**: avg turn 4bet faced (% pot)
- **Formula**: `(t_4bet_facing_bp / t_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_4bet_facing_cnt = SUM(HudCache.cnt_t_4bet_facing); t_4bet_facing_bp = SUM(HudCache.val_t_4bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_bet_facing` — TBvs

- **Description**: avg turn bet faced (% pot)
- **Formula**: `(t_bet_facing_bp / t_bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_bet_facing_cnt = SUM(HudCache.cnt_t_bet_facing); t_bet_facing_bp = SUM(HudCache.val_t_bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_bet_made` — TBet

- **Description**: avg turn bet made (% pot)
- **Formula**: `(t_bet_made_bp / t_bet_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_bet_made_cnt = SUM(HudCache.cnt_t_bet_made); t_bet_made_bp = SUM(HudCache.val_t_bet_made_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_raise_facing` — TRvs

- **Description**: avg turn raise faced (% pot)
- **Formula**: `(t_raise_facing_bp / t_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_raise_facing_cnt = SUM(HudCache.cnt_t_raise_facing); t_raise_facing_bp = SUM(HudCache.val_t_raise_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_raise_made` — TRz

- **Description**: avg turn raise made (% pot)
- **Formula**: `(t_raise_made_bp / t_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_raise_made_cnt = SUM(HudCache.cnt_t_raise_made); t_raise_made_bp = SUM(HudCache.val_t_raise_made_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_raise_made_2` — TRz2

- **Description**: avg 2nd turn raise made (% pot)
- **Formula**: `(t_raise_made_2_bp / t_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_raise_made_2_cnt = SUM(HudCache.cnt_t_raise_made_2); t_raise_made_2_bp = SUM(HudCache.val_t_raise_made_2_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `t_spr` — tSPR

- **Description**: avg turn SPR
- **Formula**: `0.01 × t_spr_val / t_spr_cnt`
- **SQL database field / logic**: t_spr_cnt = SUM(HudCache.cnt_t_spr); t_spr_val = SUM(HudCache.val_t_spr)

### `three_B_turn` — T3B

- **Description**: % 3 bet turn
- **Formula**: `tn3b / tn3b_opp × 100`
- **SQL database field / logic**: tn3b_opp = SUM(HudCache.street2_3BChance); tn3b = SUM(HudCache.street2_3BDone)

## River / 6th street

### `a_freq3` — a3

- **Description**: Aggression frequency river/6th street
- **Formula**: `aggr_3 / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); aggr_3 = SUM(HudCache.street3Aggr)
- **Detailed HUD text**: `a_fq_3`
- **XML titles**: `RvAFq`

### `avg_bet_size_river` — avg_bet_r

- **Description**: avg bet size river (deprecated)
- **Formula**: `no data (deprecated); see `r_bet_made``
- **SQL database field / logic**: none
- **Status**: deprecated

### `call_float_river` — CvRFl

- **Description**: % calling facing the river barrel, having called the turn bet in position
- **Formula**: `cnt_r_call_float / cnt_r_face_float × 100`
- **SQL database field / logic**: cnt_r_face_float = SUM(HudCache.cnt_r_face_float); cnt_r_call_float = SUM(HudCache.cnt_r_call_float)

### `call_vs_river_3bet` — CvR3B

- **Description**: % calling facing a river 3-bet
- **Formula**: `cnt_r_call_3bet / cnt_r_face_3bet × 100`
- **SQL database field / logic**: cnt_r_face_3bet = SUM(HudCache.cnt_r_face_3bet); cnt_r_call_3bet = SUM(HudCache.cnt_r_call_3bet)

### `call_vs_river_4bet` — CvR4B

- **Description**: % calling facing a river 4-bet
- **Formula**: `cnt_r_call_4bet / cnt_r_face_4bet × 100`
- **SQL database field / logic**: cnt_r_face_4bet = SUM(HudCache.cnt_r_face_4bet); cnt_r_call_4bet = SUM(HudCache.cnt_r_call_4bet)

### `call_vs_river_cbet` — CvRCB

- **Description**: % calling facing a river c-bet
- **Formula**: `cnt_r_call_cbet / cnt_r_face_cbet × 100`
- **SQL database field / logic**: cnt_r_face_cbet = SUM(HudCache.cnt_r_face_cbet); cnt_r_call_cbet = SUM(HudCache.cnt_r_call_cbet)

### `call_vs_river_donk` — CvRDk

- **Description**: % calling facing a river donk bet
- **Formula**: `cnt_r_call_donk / cnt_r_face_donk × 100`
- **SQL database field / logic**: cnt_r_face_donk = SUM(HudCache.cnt_r_face_donk); cnt_r_call_donk = SUM(HudCache.cnt_r_call_donk)

### `cb3` — cb3

- **Description**: % continuation bet river/6th street
- **Formula**: `cb_3 / cb_opp_3 × 100`
- **SQL database field / logic**: cb_opp_3 = SUM(HudCache.street3CBChance); cb_3 = SUM(HudCache.street3CBDone)
- **Detailed HUD text**: `cb_3`

### `cr3` — cr3

- **Description**: % check-raise river/6th street
- **Formula**: `cr_3 / ccr_opp_3 × 100`
- **SQL database field / logic**: ccr_opp_3 = SUM(HudCache.street3CheckCallRaiseChance); cr_3 = SUM(HudCache.street3CheckRaiseDone)
- **Detailed HUD text**: `cr_3`

### `dbr3` — dbr3

- **Description**: % DonkBetAndRaise river/6th street
- **Formula**: `(aggr_3 − cb_3) / (saw_3 − cb_opp_3) × 100`
- **SQL database field / logic**: aggr_3 = SUM(HudCache.street3Aggr); cb_3 = SUM(HudCache.street3CBDone); saw_3 = SUM(HudCache.street3Seen); cb_opp_3 = SUM(HudCache.street3CBChance)

### `f_cb3` — f_cb3

- **Description**: % fold to continuation bet river/6th street
- **Formula**: `f_cb_3 / f_cb_opp_3 × 100`
- **SQL database field / logic**: f_cb_opp_3 = SUM(HudCache.foldToStreet3CBChance); f_cb_3 = SUM(HudCache.foldToStreet3CBDone)
- **Detailed HUD text**: `f_cb_3`
- **Note**: The HUD abbreviation `f_cb3` is shared with: `fold_to_cbet_river`.

### `f_dbr3` — f_dbr3

- **Description**: % Fold to DonkBetAndRaise river
- **Formula**: `(f_freq_3 − f_cb_3) / (was_raised_3 − f_cb_opp_3) × 100`
- **SQL database field / logic**: f_freq_3 = SUM(HudCache.foldToOtherRaisedStreet3); f_cb_3 = SUM(HudCache.foldToStreet3CBDone); was_raised_3 = SUM(HudCache.otherRaisedStreet3); f_cb_opp_3 = SUM(HudCache.foldToStreet3CBChance)

### `face_raise_river` — FvRr

- **Description**: % face raise river
- **Formula**: `r_face_raise / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); r_face_raise = SUM(HudCache.street3FaceRaise)

### `ffreq3` — ff3

- **Description**: % fold frequency river/6th street
- **Formula**: `f_freq_3 / was_raised_3 × 100`
- **SQL database field / logic**: was_raised_3 = SUM(HudCache.otherRaisedStreet3); f_freq_3 = SUM(HudCache.foldToOtherRaisedStreet3)
- **Detailed HUD text**: `ff_3`

### `first_raise_river` — 1Rr

- **Description**: % first raise river
- **Formula**: `r_first_raise / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); r_first_raise = SUM(HudCache.street3FirstRaise)

### `float_river` — FltR

- **Description**: % float river
- **Formula**: `float_river_done / float_river_chance × 100`
- **SQL database field / logic**: float_river_chance = SUM(HudCache.flg_r_float_opp); float_river_done = SUM(HudCache.flg_r_float)

### `fold_float_river` — FvRFl

- **Description**: % folding facing the river barrel, having called the turn bet in position
- **Formula**: `(cnt_r_face_float − cnt_r_call_float − cnt_r_raise_float) / cnt_r_face_float × 100`
- **SQL database field / logic**: cnt_r_face_float = SUM(HudCache.cnt_r_face_float); cnt_r_call_float = SUM(HudCache.cnt_r_call_float); cnt_r_raise_float = SUM(HudCache.cnt_r_raise_float)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_river` — Fldr

- **Description**: % fold river
- **Formula**: `r_fold / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); r_fold = SUM(HudCache.flg_r_fold)

### `fold_to_cbet_river` — f_cb3

- **Description**: % fold to continuation bet river/6th street
- **Formula**: `f_cb_3 / f_cb_opp_3 × 100`
- **SQL database field / logic**: f_cb_opp_3 = SUM(HudCache.foldToStreet3CBChance); f_cb_3 = SUM(HudCache.foldToStreet3CBDone)
- **Detailed HUD text**: `f_cb_3`
- **Note**: The HUD abbreviation `f_cb3` is shared with: `f_cb3`.

### `fold_to_three_B_river` — FR3B

- **Description**: % fold to river 3bet
- **Formula**: `fr3b / fr3b_opp × 100`
- **SQL database field / logic**: fr3b_opp = SUM(HudCache.street3_FoldTo3BChance); fr3b = SUM(HudCache.street3_FoldTo3BDone)

### `fold_vs_river_3bet` — FvR3B

- **Description**: % folding facing a river 3-bet
- **Formula**: `(cnt_r_face_3bet − cnt_r_call_3bet − cnt_r_raise_3bet) / cnt_r_face_3bet × 100`
- **SQL database field / logic**: cnt_r_face_3bet = SUM(HudCache.cnt_r_face_3bet); cnt_r_call_3bet = SUM(HudCache.cnt_r_call_3bet); cnt_r_raise_3bet = SUM(HudCache.cnt_r_raise_3bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_river_4bet` — FvR4B

- **Description**: % folding facing a river 4-bet
- **Formula**: `(cnt_r_face_4bet − cnt_r_call_4bet − cnt_r_raise_4bet) / cnt_r_face_4bet × 100`
- **SQL database field / logic**: cnt_r_face_4bet = SUM(HudCache.cnt_r_face_4bet); cnt_r_call_4bet = SUM(HudCache.cnt_r_call_4bet); cnt_r_raise_4bet = SUM(HudCache.cnt_r_raise_4bet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_river_cbet` — FvRCB

- **Description**: % folding facing a river c-bet
- **Formula**: `(cnt_r_face_cbet − cnt_r_call_cbet − cnt_r_raise_cbet) / cnt_r_face_cbet × 100`
- **SQL database field / logic**: cnt_r_face_cbet = SUM(HudCache.cnt_r_face_cbet); cnt_r_call_cbet = SUM(HudCache.cnt_r_call_cbet); cnt_r_raise_cbet = SUM(HudCache.cnt_r_raise_cbet)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `fold_vs_river_donk` — FvRDk

- **Description**: % folding facing a river donk bet
- **Formula**: `(cnt_r_face_donk − cnt_r_call_donk − cnt_r_raise_donk) / cnt_r_face_donk × 100`
- **SQL database field / logic**: cnt_r_face_donk = SUM(HudCache.cnt_r_face_donk); cnt_r_call_donk = SUM(HudCache.cnt_r_call_donk); cnt_r_raise_donk = SUM(HudCache.cnt_r_raise_donk)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### `four_B_river` — R4B

- **Description**: % 4 bet river
- **Formula**: `rv4b / rv4b_opp × 100`
- **SQL database field / logic**: rv4b_opp = SUM(HudCache.street3_4BChance); rv4b = SUM(HudCache.street3_4BDone)

### `open_river` — OPr

- **Description**: % open river
- **Formula**: `rvopen / rvopen_opp × 100`
- **SQL database field / logic**: rvopen_opp = SUM(HudCache.street3OpenChance); rvopen = SUM(HudCache.street3OpenDone)

### `probe_bet_river` — probe_r

- **Description**: % probe bet river
- **Formula**: `min(street3Bets, saw_r − cb_3) / (saw_r − cb_3) × 100`
- **SQL database field / logic**: saw_r = SUM(HudCache.street3Seen); cb_3 = SUM(HudCache.street3CBDone); street3Bets = SUM(HudCache.street3Bets)
- **Status**: input-missing
- **Note**: River probe. The HUD queries name the river-seen count `saw_3` and the bet count `bet_3`, not the keys this stat reads.

### `r_2bet_facing` — R2vs

- **Description**: avg river 2bet faced (% pot)
- **Formula**: `(r_2bet_facing_bp / r_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_2bet_facing_cnt = SUM(HudCache.cnt_r_2bet_facing); r_2bet_facing_bp = SUM(HudCache.val_r_2bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_3bet_facing` — R3vs

- **Description**: avg river 3bet faced (% pot)
- **Formula**: `(r_3bet_facing_bp / r_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_3bet_facing_cnt = SUM(HudCache.cnt_r_3bet_facing); r_3bet_facing_bp = SUM(HudCache.val_r_3bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_4bet_facing` — R4vs

- **Description**: avg river 4bet faced (% pot)
- **Formula**: `(r_4bet_facing_bp / r_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_4bet_facing_cnt = SUM(HudCache.cnt_r_4bet_facing); r_4bet_facing_bp = SUM(HudCache.val_r_4bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_bet_facing` — RBvs

- **Description**: avg river bet faced (% pot)
- **Formula**: `(r_bet_facing_bp / r_bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_bet_facing_cnt = SUM(HudCache.cnt_r_bet_facing); r_bet_facing_bp = SUM(HudCache.val_r_bet_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_bet_made` — RBet

- **Description**: avg river bet made (% pot)
- **Formula**: `(r_bet_made_bp / r_bet_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_bet_made_cnt = SUM(HudCache.cnt_r_bet_made); r_bet_made_bp = SUM(HudCache.val_r_bet_made_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_raise_facing` — RRvs

- **Description**: avg river raise faced (% pot)
- **Formula**: `(r_raise_facing_bp / r_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_raise_facing_cnt = SUM(HudCache.cnt_r_raise_facing); r_raise_facing_bp = SUM(HudCache.val_r_raise_facing_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_raise_made` — RRz

- **Description**: avg river raise made (% pot)
- **Formula**: `(r_raise_made_bp / r_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_raise_made_cnt = SUM(HudCache.cnt_r_raise_made); r_raise_made_bp = SUM(HudCache.val_r_raise_made_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_raise_made_2` — RRz2

- **Description**: avg 2nd river raise made (% pot)
- **Formula**: `(r_raise_made_2_bp / r_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_raise_made_2_cnt = SUM(HudCache.cnt_r_raise_made_2); r_raise_made_2_bp = SUM(HudCache.val_r_raise_made_2_bp)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### `r_spr` — rSPR

- **Description**: avg river SPR
- **Formula**: `0.01 × r_spr_val / r_spr_cnt`
- **SQL database field / logic**: r_spr_cnt = SUM(HudCache.cnt_r_spr); r_spr_val = SUM(HudCache.val_r_spr)

### `raise_float_river` — RvRFl

- **Description**: % raising facing the river barrel, having called the turn bet in position
- **Formula**: `cnt_r_raise_float / cnt_r_face_float × 100`
- **SQL database field / logic**: cnt_r_face_float = SUM(HudCache.cnt_r_face_float); cnt_r_raise_float = SUM(HudCache.cnt_r_raise_float)

### `raise_vs_river_3bet` — RvR3B

- **Description**: % raising facing a river 3-bet
- **Formula**: `cnt_r_raise_3bet / cnt_r_face_3bet × 100`
- **SQL database field / logic**: cnt_r_face_3bet = SUM(HudCache.cnt_r_face_3bet); cnt_r_raise_3bet = SUM(HudCache.cnt_r_raise_3bet)

### `raise_vs_river_4bet` — RvR4B

- **Description**: % raising facing a river 4-bet
- **Formula**: `cnt_r_raise_4bet / cnt_r_face_4bet × 100`
- **SQL database field / logic**: cnt_r_face_4bet = SUM(HudCache.cnt_r_face_4bet); cnt_r_raise_4bet = SUM(HudCache.cnt_r_raise_4bet)

### `raise_vs_river_cbet` — RvRCB

- **Description**: % raising facing a river c-bet
- **Formula**: `cnt_r_raise_cbet / cnt_r_face_cbet × 100`
- **SQL database field / logic**: cnt_r_face_cbet = SUM(HudCache.cnt_r_face_cbet); cnt_r_raise_cbet = SUM(HudCache.cnt_r_raise_cbet)

### `raise_vs_river_donk` — RvRDk

- **Description**: % raising facing a river donk bet
- **Formula**: `cnt_r_raise_donk / cnt_r_face_donk × 100`
- **SQL database field / logic**: cnt_r_face_donk = SUM(HudCache.cnt_r_face_donk); cnt_r_raise_donk = SUM(HudCache.cnt_r_raise_donk)

### `river_call_efficiency` — RCE

- **Description**: River Call Efficiency
- **Formula**: `wmsd / call_3 × 100`
- **SQL database field / logic**: call_3 = SUM(HudCache.street3Calls); wmsd = SUM(HudCache.wonAtSD)
- **Detailed HUD text**: `RiverCallEff`

### `three_B_river` — R3B

- **Description**: % 3 bet river
- **Formula**: `rv3b / rv3b_opp × 100`
- **SQL database field / logic**: rv3b_opp = SUM(HudCache.street3_3BChance); rv3b = SUM(HudCache.street3_3BDone)

## 7th street

### `a_freq4` — a4

- **Description**: Aggression frequency 7th street
- **Formula**: `aggr_4 / saw_4 × 100`
- **SQL database field / logic**: saw_4 = SUM(HudCache.street4Seen); aggr_4 = SUM(HudCache.street4Aggr)
- **Detailed HUD text**: `a_fq_4`

### `cb4` — cb4

- **Description**: % continuation bet 7th street
- **Formula**: `cb_4 / cb_opp_4 × 100`
- **SQL database field / logic**: cb_opp_4 = SUM(HudCache.street4CBChance); cb_4 = SUM(HudCache.street4CBDone)
- **Detailed HUD text**: `cb_4`

### `cr4` — cr4

- **Description**: % check-raise 7th street
- **Formula**: `cr_4 / ccr_opp_4 × 100`
- **SQL database field / logic**: ccr_opp_4 = SUM(HudCache.street4CheckCallRaiseChance); cr_4 = SUM(HudCache.street4CheckRaiseDone)
- **Detailed HUD text**: `cr_4`

### `f_cb4` — f_cb4

- **Description**: % fold to continuation bet 7th street
- **Formula**: `f_cb_4 / f_cb_opp_4 × 100`
- **SQL database field / logic**: f_cb_opp_4 = SUM(HudCache.foldToStreet4CBChance); f_cb_4 = SUM(HudCache.foldToStreet4CBDone)
- **Detailed HUD text**: `f_cb_4`

### `ffreq4` — ff4

- **Description**: % fold frequency 7th street
- **Formula**: `f_freq_4 / was_raised_4 × 100`
- **SQL database field / logic**: was_raised_4 = SUM(HudCache.otherRaisedStreet4); f_freq_4 = SUM(HudCache.foldToOtherRaisedStreet4)
- **Detailed HUD text**: `ff_4`

## Postflop, all streets

### `a_freq_123` — afq

- **Description**: Post-flop aggression frequency
- **Formula**: `(aggr_1 + aggr_2 + aggr_3) / (saw_1 + saw_2 + saw_3) × 100`
- **SQL database field / logic**: aggr_1 = SUM(HudCache.street1Aggr); aggr_2 = SUM(HudCache.street2Aggr); aggr_3 = SUM(HudCache.street3Aggr); saw_1 = SUM(HudCache.street1Seen); saw_2 = SUM(HudCache.street2Seen); saw_3 = SUM(HudCache.street3Seen)
- **Detailed HUD text**: `post_a_fq`
- **XML titles**: `PoFAFq`

### `agg_fact` — afa

- **Description**: Aggression factor
- **Formula**: `(Σ aggr_1..4) / (Σ call_1..4); the numerator alone when there is no call`
- **SQL database field / logic**: aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4 (flop to 7th street)
- **Detailed HUD text**: `agg_fa`
- **XML titles**: `AggFac`
- **Note**: Postflop aggression factor, raw ratio.

### `agg_fact_pct` — afap

- **Description**: Aggression factor pct
- **Formula**: `(Σ aggr_1..4) / (Σ call_1..4 + Σ aggr_1..4)`
- **SQL database field / logic**: aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4
- **Detailed HUD text**: `agg_fa_pct`
- **Note**: Despite its name the result is a 0..1 fraction (aggression / (aggression + calls)), not multiplied by 100.

### `cbet` — cbet

- **Description**: % continuation bet
- **Formula**: `(Σ cb_1..4) / (Σ cb_opp_1..4) × 100`
- **SQL database field / logic**: cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 4
- **XML titles**: `ContBet`
- **Note**: Continuation bet across all four streets pooled; `cb1`..`cb4` give one street each.

### `check_raise_frequency` — CRF

- **Description**: Check-Raise Frequency
- **Formula**: `(cr_1 + cr_2 + cr_3) / (ccr_opp_1 + ccr_opp_2 + ccr_opp_3) × 100`
- **SQL database field / logic**: cr_1 = SUM(HudCache.street1CheckRaiseDone); cr_2 = SUM(HudCache.street2CheckRaiseDone); cr_3 = SUM(HudCache.street3CheckRaiseDone); ccr_opp_1 = SUM(HudCache.street1CheckCallRaiseChance); ccr_opp_2 = SUM(HudCache.street2CheckCallRaiseChance); ccr_opp_3 = SUM(HudCache.street3CheckCallRaiseChance)
- **Detailed HUD text**: `CheckRaiseFreq`

### `fold_to_allin` — FvAI

- **Description**: % fold to all-in
- **Formula**: `fold_allin / faced_allin × 100`
- **SQL database field / logic**: faced_allin = SUM(HudCache.flg_faced_allin); fold_allin = SUM(HudCache.flg_fold_to_allin)

### `overbet_frequency` — overbet

- **Description**: % overbet frequency
- **Formula**: `constant 15 %, shown once any bet has been seen (Σ street1..3Bets > 0)`
- **SQL database field / logic**: street1Bets, street2Bets, street3Bets = SUM(HudCache.streetNBets) (exposed by the HUD queries as bet_1..3)
- **Detailed HUD text**: `overbet_freq`
- **Status**: estimate
- **Note**: Not measured. The function returns a fixed 15 % estimate; it is kept for old layouts.

### `triple_barrel` — 3barrel

- **Description**: % triple barrel
- **Formula**: `min(cb_opp_1..3) × Π (cb_N / cb_opp_N) / min(cb_opp_1..3) × 100 = Π (cb_N / cb_opp_N) × 100`
- **SQL database field / logic**: cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 3
- **Detailed HUD text**: `triple_barrel`
- **Note**: An estimate: the product of the three street c-bet rates, assuming the streets are independent. It does not follow the same hands through the three streets.

## Results and showdown

### `amt_bet_f` — BetF

- **Description**: avg flop invested
- **Formula**: `0.01 × amt_bet_f / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_f = SUM(HudCache.amt_bet_f)

### `amt_bet_p` — BetP

- **Description**: avg preflop invested
- **Formula**: `0.01 × amt_bet_p / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_p = SUM(HudCache.amt_bet_p)

### `amt_bet_r` — BetR

- **Description**: avg river invested
- **Formula**: `0.01 × amt_bet_r / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_r = SUM(HudCache.amt_bet_r)

### `amt_bet_t` — BetT

- **Description**: avg turn invested
- **Formula**: `0.01 × amt_bet_t / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_t = SUM(HudCache.amt_bet_t)

### `amt_bet_ttl` — BetTtl

- **Description**: avg total invested
- **Formula**: `0.01 × amt_bet_ttl / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_ttl = SUM(HudCache.amt_bet_ttl)

### `BBper100` — BB100

- **Description**: Big bets won per 100 hands
- **Formula**: `50 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)
- **Note**: Big *bets* per 100 hands: the 50 factor counts a big bet as two big blinds. `bbper100` is the big-blind version.

### `bbper100` — bb100

- **Description**: Big blinds won per 100 hands
- **Formula**: `100 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)
- **Note**: Big blinds won per 100 hands.

### `non_sd_winrate` — nsd_wr

- **Description**: % non-showdown winrate
- **Formula**: `(w_w_s_1 − wmsd) / (saw_f − sd)`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); sd = SUM(HudCache.sawShowdown); w_w_s_1 = SUM(HudCache.wonWhenSeenStreet1); wmsd = SUM(HudCache.wonAtSD)

### `profit100` — p

- **Description**: Profit per 100 hands
- **Formula**: `net / n  (net in cents, so cents per hand, shown as per 100 hands in the label)`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); n = SUM(HudCache.n)
- **Detailed HUD text**: `p/100`
- **Note**: The label says per 100 hands but the formula is the average profit per hand, in cents. The HUD abbreviation `p` is shared with: `pfr`, `playerprofile`.

### `saw_f` — sf

- **Description**: Flop/4th street seen %
- **Formula**: `saw_f / n × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); n = SUM(HudCache.n)
- **Detailed HUD text**: `saw_f`
- **XML titles**: `Saw_F`

### `sd_winrate` — sd_wr

- **Description**: % showdown winrate
- **Formula**: `wmsd / sd × 100`
- **SQL database field / logic**: sd = SUM(HudCache.sawShowdown); wmsd = SUM(HudCache.wonAtSD)
- **Detailed HUD text**: `showdown_winrate`

### `totalprofit` — tp

- **Description**: Total Profit
- **Formula**: `net / 100, formatted with the game's currency`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); currency = the game type's currency
- **Detailed HUD text**: `tot_prof`

### `wmsd` — w

- **Description**: % won some money at showdown
- **Formula**: `wmsd / sd × 100`
- **SQL database field / logic**: sd = SUM(HudCache.sawShowdown); wmsd = SUM(HudCache.wonAtSD)
- **Detailed HUD text**: `wmsd`
- **XML titles**: `W$SD`
- **Note**: The HUD abbreviation `w` is shared with: `wtsd`.

### `WMsF` — wf

- **Description**: % won money when seen flop/4th street
- **Formula**: `w_w_s_1 / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); w_w_s_1 = SUM(HudCache.wonWhenSeenStreet1)
- **Detailed HUD text**: `w_w_f`
- **XML titles**: `W$wsF`
- **Note**: The HUD abbreviation `wf` is shared with: `wwsf`.

### `wsd` — W$SD

- **Description**: Won money at showdown.
- **Formula**: `100 * wonAtSD / sawShowdown   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): wonAtSD, sawShowdown
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `wtsd` — w

- **Description**: % went to showdown when seen flop/4th street
- **Formula**: `sd / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); sd = SUM(HudCache.sawShowdown)
- **Detailed HUD text**: `wtsd`
- **XML titles**: `WtSDwsF`
- **Note**: The HUD abbreviation `w` is shared with: `wmsd`.

### `wwsf` — wf

- **Description**: % won money when seen flop/4th street
- **Formula**: `w_w_s_1 / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); w_w_s_1 = SUM(HudCache.wonWhenSeenStreet1)
- **Detailed HUD text**: `w_w_f`
- **Note**: The HUD abbreviation `wf` is shared with: `WMsF`.

## Tournament and stack

### `bbstack` — v

- **Description**: bb stack
- **Formula**: `end stack of the player at the current hand / big blind of that hand`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Detailed HUD text**: `vpip`
- **Note**: Last-hand value, not aggregated over the history. The HUD abbreviation `v` is shared with: `vpip`.

### `bounty` — bounty

- **Description**: bounty (last hand)
- **Formula**: `the player's current bounty after the last hand`
- **SQL database field / logic**: not a HudCache aggregate: read from the hand being displayed (Hand object)
- **Note**: Knockout tournaments only.

### `chipev_3h_bb` — ChipEV 3-handed BB

- **Description**: Chips the player was expected to win at all-in, 3-handed in the big blind.
- **Formula**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `chipev_3h_btn` — ChipEV 3-handed BTN

- **Description**: Chips the player was expected to win at all-in, 3-handed on the button.
- **Formula**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `chipev_3h_sb` — ChipEV 3-handed SB

- **Description**: Chips the player was expected to win at all-in, 3-handed in the small blind.
- **Formula**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `chipev_hu_bb` — ChipEV heads-up BB

- **Description**: Chips the player was expected to win at all-in, heads-up in the big blind.
- **Formula**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `chipev_hu_sb` — ChipEV heads-up SB

- **Description**: Chips the player was expected to win at all-in, heads-up in the small blind (button).
- **Formula**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `chipev_tourney` — ChipEV / tournament

- **Description**: Average all-in chip EV per tournament.
- **Formula**: `allInEV / 100.0 / cnt_tourneys   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV, cnt_tourneys
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### `covers` — covers

- **Description**: who covers whom (last hand)
- **Formula**: `compares the player's end stack with the hero's: +1 you cover, −1 covers you, 0 even`
- **SQL database field / logic**: not a HudCache aggregate: read from the hand being displayed (Hand object)

### `m_ratio` — M

- **Description**: M ratio
- **Formula**: `end stack / (antes + blinds posted in the hand + small blind + big blind)`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Note**: Last-hand value, not aggregated over the history.

### `stack_amount` — stack

- **Description**: stack (last hand)
- **Formula**: `reconstructed stack of the player, in the table's currency`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Note**: Last-hand value. The HUD abbreviation `stack` is shared with: `stack_native_bb`.

### `stack_bb` — stack_bb

- **Description**: stack in bb (last hand)
- **Formula**: `reconstructed stack / big blind`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Note**: Last-hand value.

### `stack_native_bb` — stack

- **Description**: stack and bb stack (last hand)
- **Formula**: `reconstructed stack, followed by the stack / big blind`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Note**: Last-hand value. The HUD abbreviation `stack` is shared with: `stack_amount`.

## All-in or Fold

### `aof_allin` — AI

- **Description**: % all-in on the single All-in or Fold decision
- **Formula**: `vpip / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI)
- **Detailed HUD text**: `all-in`

### `aof_big_wrap13` — W13+

- **Description**: % of observable all-ins with at least thirteen straight outs
- **Formula**: `aof_big_wrap13 / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_big_wrap13 = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.straightOuts>=13 then 1 else 0 end)
- **Detailed HUD text**: `big wrap 13+ 1/1 100.0%`

### `aof_decision_ev` — EV

- **Description**: average modeled decision EV in big blinds, including fold/call branches; pre-rake until the room supplies a verified rake schedule
- **Formula**: `1e-06 × aof_decision_ev_bb_ppm / aof_decision_ev`
- **SQL database field / logic**: aof_decision_ev = SUM(case when e.status in ('weak', 'strong', 'uncertain') then 1 else 0 end); aof_decision_ev_bb_ppm = SUM(case when e.status in ('weak', 'strong', 'uncertain') then e.evBbPpm else 0 end)
- **Detailed HUD text**: `Decision EV`

### `aof_flush` — Flush

- **Description**: % of observable all-ins classified as flush
- **Formula**: `aof_flush / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_flush = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a flush' then 1 else 0 end)
- **Detailed HUD text**: `flush 1/1 100.0%`

### `aof_fold` — F

- **Description**: % folded on the single All-in or Fold decision
- **Formula**: `(vpip_opp − vpip) / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI)
- **Detailed HUD text**: `fold`

### `aof_full_house` — Full

- **Description**: % of observable all-ins classified as full house
- **Formula**: `aof_full_house / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_full_house = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a full house' then 1 else 0 end)
- **Detailed HUD text**: `full house 1/1 100.0%`

### `aof_known_equity` — EqK

- **Description**: average flop equity against actual callers whose complete cards were captured
- **Formula**: `1e-06 × aof_known_equity_ppm / aof_known`
- **SQL database field / logic**: aof_known = SUM(case when a.status='complete' then 1 else 0 end); aof_known_equity_ppm = SUM(case when a.status='complete' then a.equityPpm else 0 end)
- **Detailed HUD text**: `known-card equity`

### `aof_known_ev` — EVact

- **Description**: average EV in BB conditional on the actual callers, using only fully known pockets
- **Formula**: `1e-06 × aof_known_ev_bb_ppm / aof_known`
- **SQL database field / logic**: aof_known = SUM(case when a.status='complete' then 1 else 0 end); aof_known_ev_bb_ppm = SUM(case when a.status='complete' then a.evBbPpm else 0 end)
- **Detailed HUD text**: `EV vs actual callers`

### `aof_made` — Made

- **Description**: % of observable all-ins with a made hand
- **Formula**: `aof_made / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_made = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand<>'no made hand' then 1 else 0 end)
- **Detailed HUD text**: `made hand 1/1 100.0%`

### `aof_nfd` — NFD

- **Description**: % of observable all-ins with the nut flush draw
- **Formula**: `aof_nfd / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_nfd = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.flushDraw='nut flush draw' then 1 else 0 end)
- **Detailed HUD text**: `nut flush draw 1/1 100.0%`

### `aof_no_made` — NoMade

- **Description**: % of observable all-ins with no made hand
- **Formula**: `aof_no_made / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_no_made = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='no made hand' then 1 else 0 end)
- **Detailed HUD text**: `no made hand 1/1 100.0%`

### `aof_non_nfd` — nonNFD

- **Description**: % of observable all-ins with a non-nut flush draw
- **Formula**: `aof_non_nfd / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_non_nfd = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.flushDraw='non-nut flush draw' then 1 else 0 end)
- **Detailed HUD text**: `non-nut flush draw 1/1 100.0%`

### `aof_observed` — Obs

- **Description**: all-ins with complete hole cards and flop captured
- **Formula**: `aof_obs (a count)`
- **SQL database field / logic**: aof_obs = count of all-or-fold decisions with decision = 'allin' and cardsObservable (sql_queries_aof.py)
- **Detailed HUD text**: `observed all-ins`

### `aof_pair` — Pair

- **Description**: % of observable all-ins classified as pair
- **Formula**: `aof_pair / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_pair = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a pair' then 1 else 0 end)
- **Detailed HUD text**: `pair 1/1 100.0%`

### `aof_quads` — Quads

- **Description**: % of observable all-ins classified as quads
- **Formula**: `aof_quads / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_quads = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='quads' then 1 else 0 end)
- **Detailed HUD text**: `quads 1/1 100.0%`

### `aof_range_equity` — EqR

- **Description**: average flop equity against the room/game/role population range; showdown-biased and trained only on earlier hands
- **Formula**: `1e-06 × aof_range_equity_ppm / aof_range`
- **SQL database field / logic**: aof_range = SUM(case when r.status='complete' then 1 else 0 end); aof_range_equity_ppm = SUM(case when r.status='complete' then r.equityPpm else 0 end)
- **Detailed HUD text**: `population-range equity`

### `aof_showdowns` — SD

- **Description**: hands of this player that reached showdown
- **Formula**: `sd (a count, with n as the sample)`
- **SQL database field / logic**: sd = SUM(HudCache.sawShowdown); n = SUM(HudCache.n)
- **Detailed HUD text**: `showdowns`
- **Note**: Hands that reached showdown, not hands whose cards were captured.

### `aof_splash_freq` — Spl%

- **Description**: % of splash hands where the player took a share
- **Formula**: `aof_splash_hit / aof_splash_seen × 100`
- **SQL database field / logic**: aof_splash_seen = SUM(case when h.splashPot>0 then 1 else 0 end); aof_splash_hit = SUM(case when hp.splashWinnings>0 then 1 else 0 end)
- **Detailed HUD text**: `splash taken`

### `aof_splash_won` — Spl

- **Description**: amount collected from splash pots
- **Formula**: `aof_splash_cents / 100`
- **SQL database field / logic**: aof_splash_cents, aof_splash_seen and aof_splash_hit from sql_queries_aof.py (splash pot winnings)
- **Detailed HUD text**: `splash collected`
- **Note**: Money the room adds to the pot from outside; read it together with profit.

### `aof_straight` — Str

- **Description**: % of observable all-ins classified as straight
- **Formula**: `aof_straight / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_straight = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a straight' then 1 else 0 end)
- **Detailed HUD text**: `straight 1/1 100.0%`
- **Note**: The HUD abbreviation `Str` is shared with: `straddle`.

### `aof_straight_flush` — SF

- **Description**: % of observable all-ins classified as straight flush
- **Formula**: `aof_straight_flush / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_straight_flush = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a straight flush' then 1 else 0 end)
- **Detailed HUD text**: `straight flush 1/1 100.0%`

### `aof_summary` — Shows NFD×1 W13×1 W9×1 fd×1

- **Description**: what this player shows up with, over observed all-ins
- **Formula**: `the markers seen over the observed all-ins, for example NFD×10 W9×8 air×4`
- **SQL database field / logic**: aof_obs and one counter per marker (aof_nfd, aof_wrap9, aof_pair…) from sql_queries_aof.py
- **Detailed HUD text**: `NFD×1 W13×1 W9×1 fd×1 3k×1 2p×1 1p×1 air×1 over 1 observed all-ins`

### `aof_trips` — Trips

- **Description**: % of observable all-ins classified as trips
- **Formula**: `aof_trips / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_trips = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='trips' then 1 else 0 end)
- **Detailed HUD text**: `trips 1/1 100.0%`

### `aof_two_pair` — 2P

- **Description**: % of observable all-ins classified as two pair
- **Formula**: `aof_two_pair / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_two_pair = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='two pair' then 1 else 0 end)
- **Detailed HUD text**: `two pair 1/1 100.0%`

### `aof_weak` — W

- **Description**: all-ins whose modeled pre-rake EV is negative even at the upper 95% confidence bound; uncertain and unmodeled decisions are not counted as weak
- **Formula**: `aof_weak / aof_decision_ev × 100`
- **SQL database field / logic**: aof_decision_ev = SUM(case when e.status in ('weak', 'strong', 'uncertain') then 1 else 0 end); aof_weak = SUM(case when e.status='weak' then 1 else 0 end)
- **Detailed HUD text**: `Weak AI`

### `aof_wrap9` — W9+

- **Description**: % of observable all-ins with at least nine straight outs
- **Formula**: `aof_wrap9 / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_wrap9 = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.straightOuts>=9 then 1 else 0 end)
- **Detailed HUD text**: `wrap 9+ 1/1 100.0%`

## Other

### `draw_decision_distribution` — Draw decisions by round and cards drawn

- **Description**: Counts explicit stand-pat and discard decisions for every draw round present in the hand history. Zero means stand pat; unknown discard counts remain in an unknown group.
- **Formula**: `metric opportunities over the decisions matching the filters`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'game_base': ['draw'], 'action_taken': ['discards', 'stands pat']}; grouped by draw_number, cards_drawn
- **Note**: Analytics definition (metric opportunities): a HUD cell shows it only with the data_* attributes the editor writes.

## Legacy Ring Player Stats columns

| Column | XML title | SQL logic |
| --- | --- | --- |
| `game` | Game | `—` |
| `hand` | Hand | `—` |
| `plposition` | Posn | `<position>` |
| `pname` | Name | `<playerName>` |
| `n` | Hds | `count(1)` |
| `avgseats` | Seats | `avg(h.seats+0.0)` |
| `vpip` | VPIP | `case when sum(street0VPIChance) = 0 then -999 else 100.0*sum(street0VPI)/sum(street0VPIChance) end` |
| `pfr` | PFR | `case when sum(street0AggrChance) = 0 then -999 else 100.0*sum(street0Aggr)/sum(street0AggrChance) end` |
| `pf3` | PF3 | `case when sum(street0_3Bchance) = 0 then -999 else 100.0*sum(street0_3Bdone)/sum(street0_3Bchance) end` |
| `pf4` | PF4 | `case when sum(street0_4Bchance) = 0 then -999 else 100.0*sum(street0_4Bdone)/sum(street0_4Bchance) end` |
| `pff3` | PFF3 | `case when sum(street0_FoldTo3Bchance) = 0 then -999 else 100.0*sum(street0_FoldTo3Bdone)/sum(street0_FoldTo3Bchance) end` |
| `pff4` | PFF4 | `case when sum(street0_FoldTo4Bchance) = 0 then -999 else 100.0*sum(street0_FoldTo4Bdone)/sum(street0_FoldTo4Bchance) end` |
| `aggfac` | AggFac | `case when sum(street1Calls)+ sum(street2Calls)+ sum(street3Calls)+ sum(street4Calls) = 0 then -999 else (sum(street1Aggr) + sum(street2Aggr) + sum(street3Aggr) + sum(street4Aggr)) /(0.0+sum(street1Calls)+ sum(street2Calls)+ sum(street3Calls)+ sum(street4Calls)) end` |
| `aggfrq` | AggFreq | `100.0*(sum(street1Aggr) + sum(street2Aggr) + sum(street3Aggr) + sum(street4Aggr)) / ((sum(foldToOtherRaisedStreet1)+ sum(foldToOtherRaisedStreet2)+ sum(foldToOtherRaisedStreet3)+ sum(foldToOtherRaisedStreet4)) + (sum(street1Calls)+ sum(street2Calls)+ sum(street3Calls)+ sum(street4Calls)) + (sum(street1Aggr) + sum(street2Aggr) + sum(street3Aggr) + sum(street4Aggr)) )` |
| `conbet` | ContBet | `100.0*(sum(street1CBDone) + sum(street2CBDone) + sum(street3CBDone) + sum(street4CBDone)) / (sum(street1CBChance)+ sum(street2CBChance)+ sum(street3CBChance)+ sum(street4CBChance))` |
| `rfi` | RFI | `case when sum(raiseFirstInChance) = 0 then -999 else 100.0 * sum(raisedFirstIn) / sum(raiseFirstInChance) end` |
| `steals` | Steals | `case when sum(stealChance) = 0 then -999 else 100.0 * sum(stealDone) / sum(stealChance) end` |
| `car0` | CARpre | `case when sum(street0CalledRaiseChance) = 0 then -999 else 100.0*sum(street0CalledRaiseDone)/sum(street0CalledRaiseChance) end` |
| `saw_f` | Saw_F | `100.0*sum(street1Seen)/count(1)` |
| `sawsd` | SawSD | `100.0*sum(sawShowdown)/count(1)` |
| `wtsdwsf` | WtSDwsF | `case when sum(street1Seen) = 0 then -999 else 100.0*sum(sawShowdown)/sum(street1Seen) end` |
| `wmsf` | W$wsF | `case when sum(street1Seen) = 0 then -999 else 100.0*sum(wonWhenSeenStreet1)/sum(street1Seen) end` |
| `wmsd` | W$SD | `case when sum(sawShowdown) = 0 then -999 else 100.0*sum(wonAtSD)/sum(sawShowdown) end` |
| `flafq` | FlAFq | `case when sum(street1Seen) = 0 then -999 else 100.0*sum(street1Aggr)/sum(street1Seen) end` |
| `tuafq` | TuAFq | `case when sum(street2Seen) = 0 then -999 else 100.0*sum(street2Aggr)/sum(street2Seen) end` |
| `rvafq` | RvAFq | `case when sum(street3Seen) = 0 then -999 else 100.0*sum(street3Aggr)/sum(street3Seen) end` |
| `pofafq` | PoFAFq | `case when sum(street1Seen)+sum(street2Seen)+sum(street3Seen) = 0 then -999 else 100.0*(sum(street1Aggr)+sum(street2Aggr)+sum(street3Aggr)) /(sum(street1Seen)+sum(street2Seen)+sum(street3Seen)) end` |
| `net` | Net($) | `sum(totalProfit)/100.0` |
| `evnet` | All-in EV($) | `sum(allInEV)/100.0` |
| `evbbper100` | EV bb/100 | `100.0*avg(allInEV/(gt.bigBlind+0.0))` |
| `luck` | Net − EV($) | `sum(totalProfit-allInEV)/100.0` |
| `evhands` | EV hands | `sum(case when allInEVCalculated then 1 else 0 end)` |
| `allinhands` | EV eligible | `sum(case when wentAllIn or allInEVCalculated then 1 else 0 end)` |
| `evcoverage` | EV coverage % | `case when sum(case when wentAllIn or allInEVCalculated then 1 else 0 end) = 0 then -999 else 100.0*sum(case when allInEVCalculated then 1 else 0 end)/ sum(case when wentAllIn or allInEVCalculated then 1 else 0 end) end` |
| `bbper100` | bb/100 | `100.0*avg(totalProfit/(gt.bigBlind+0.0))` |
| `rake` | Rake($) | `sum(rake)/100.0` |
| `bb100xr` | bbxr/100 | `100.0*avg((totalProfit+rake)/(gt.bigBlind+0.0))` |
| `variance` | Variance / hand² | `variance(totalProfit/100.0)` |
| `stddev` | Std Dev / hand | `sqrt(variance(totalProfit/100.0))` |
