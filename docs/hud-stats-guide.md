# HUD Stats Guide

Generated from the code by `tools/gen_stats_guide.py`; do not edit by hand. The same data feeds the in-app **Stats Guide**.

## How to read an entry

- **Code identifier**: the name written in a HUD layout (`<stat stat_name=...>`). It is what the Add/Edit Statistic picker stores.
- **HUD abbreviation**: the short text the HUD draws; it is the first part of the value the stat function returns.
- **XML titles**: the `col_title` of the legacy Ring Player Stats columns that show the same measure. They are display titles only.
- **Formula** and **SQL database field / logic**: the numerator and denominator the stat function really uses, and the HudCache expression that fills each input.

Stats installed as user stat packs (`stat_packs`) or custom `stats.d` files are extensible and are **not** listed here.

## Games and variants

The HUD sums each player's history per game type: cash and tournament hands are never mixed, nor are
two variants. Tournaments are one game type whatever their format, so MTT and SnG hands are counted
together.

The database numbers the betting rounds, and each stat reads one of those numbers. What a round is
depends on the game family:

| Round in the database | Hold'em / Omaha | Stud / Razz | Draw |
| --- | --- | --- | --- |
| 0 | preflop | 3rd street | before the first draw |
| 1 | flop | 4th street | after the first draw |
| 2 | turn | 5th street | after the second draw (triple draw only) |
| 3 | river | 6th street | after the third draw (triple draw only) |
| 4 | (none) | 7th street | (none) |

So a "flop" stat is a 4th-street stat in stud and an after-the-first-draw stat in draw. Two exceptions:
5-card stud starts at 2nd street (round 0 = 2nd street), and All-in or Fold Omaha has no preflop round
(round 0 is its single flop decision).

Whether a stat has data in a family is measured, not assumed: every regression hand history of the
project is parsed and run through DerivedStats, and a stat applies to a family when all the columns
it reads get a value there. The corpus: 178 ring draw, 2647 ring hold, 166 ring stud, 1 tour draw, 434 tour hold hands. "No data" for a family means those columns stayed empty on every test hand of it.

## Player

### Blank cell — `blank`

- **HUD abbreviation**: (none)
- **Description**: An empty cell used to space a HUD layout. It shows nothing.
- **Formula (code)**: `an empty cell, used as a spacer in layouts`
- **SQL database field / logic**: none
- **Tooltip**: <blank>
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Game — `game_abbr`

- **HUD abbreviation**: `game`
- **Description**: The abbreviation of the game played at the table, for example NL Hold'em.
- **Formula (code)**: `abbreviation of the game being played (for example Hold'em NL)`
- **SQL database field / logic**: read from the game type of the table; not a HudCache aggregate
- **Tooltip**: Game abbreviation
- **Detailed HUD text**: `game_abbr`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Hands — `n`

- **HUD abbreviation**: `n`
- **Description**: The number of hands the HUD has for this player, over the aggregation period the HUD uses. Shown as 12.3k from 10,000 hands.
- **Formula**: Number of hands played
- **Formula (code)**: `n (hand count; shown as 12.3k from 10 000)`
- **SQL database field / logic**: n = SUM(HudCache.n)
- **Tooltip**: Number of hands seen
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Player note — `player_note`

- **HUD abbreviation**: `📝`
- **Description**: An icon shown when you have written a note on this player.
- **Formula (code)**: `an icon when the player has a note`
- **SQL database field / logic**: screen_name = Players.name; the note is read from the notes of that player
- **Tooltip**: Player note icon
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Player name — `playername`

- **HUD abbreviation**: `1`
- **Description**: The player's screen name.
- **Formula (code)**: `the player's name`
- **SQL database field / logic**: screen_name = Players.name
- **Tooltip**: Player name
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: The HUD abbreviation `1` is shared with: `playershort`.

### Player profile — `playerprofile`

- **HUD abbreviation**: `p`
- **Description**: A player type (for example nit, TAG, LAG, fish) chosen from the player's VPIP, PFR and aggression. It is a label, not a number.
- **Formula (code)**: `player type (for example nit, TAG, LAG, fish) chosen by PlayerProfiler.classify_player from VPIP, PFR and aggression`
- **SQL database field / logic**: uses the HUD stat row of the player (VPIP, PFR, aggression inputs)
- **Tooltip**: Player Profile
- **Detailed HUD text**: `playerprofile`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: A label, not a number. The HUD abbreviation `p` is shared with: `pfr`, `profit100`.

### Player name (short) — `playershort`

- **HUD abbreviation**: `1`
- **Description**: The player's screen name, shortened to fit the cell.
- **Formula (code)**: `the player's name, shortened to fit the cell`
- **SQL database field / logic**: screen_name = Players.name
- **Tooltip**: Player Name 1-5
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: The HUD abbreviation `1` is shared with: `playername`.

### Starting hands seen — `starthands`

- **HUD abbreviation**: (none)
- **Description**: The hands this player voluntarily played in the current hand-history file, grouped as limped, raised, called a raise, and defended the big blind, with a position letter. It reads one file, not the cache, so it ignores the HUD's aggregation settings; use it in a popup.
- **Formula (code)**: `lists the hands the player voluntarily played in the current history file, grouped as limped, raised, called a raise, defended the BB`
- **SQL database field / logic**: SELECT DISTINCT startCards, street0Aggr, street0CalledRaiseDone, position FROM Hands, HandsPlayers, Gametypes WHERE street0VPI AND fileId = the current file
- **Tooltip**: Hands seen at this table
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: Hold'em only (the query is limited to holdem)
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: Meant for popups: it reads one history file, not the cache, so it ignores the HUD's aggregation settings.

## Preflop

### Call vs Preflop 3-Bet — `call_vs_preflop_3bet`

- **HUD abbreviation**: `Cv3B`
- **Description**: Percentage of the time that a player called when facing a 3-bet on the preflop.
- **Formula**: Number of times the player called a 3-bet on the preflop / Number of times the player faced a 3-bet on the preflop × 100
- **Formula (code)**: `cnt_p_call_3bet / cnt_p_face_3bet × 100`
- **SQL database field / logic**: cnt_p_face_3bet = SUM(HudCache.cnt_p_face_3bet); cnt_p_call_3bet = SUM(HudCache.cnt_p_call_3bet)
- **Tooltip**: % calling facing a preflop 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Call vs Preflop 4-Bet — `call_vs_preflop_4bet`

- **HUD abbreviation**: `Cv4B`
- **Description**: Percentage of the time that a player called when facing a 4-bet on the preflop.
- **Formula**: Number of times the player called a 4-bet on the preflop / Number of times the player faced a 4-bet on the preflop × 100
- **Formula (code)**: `cnt_p_call_4bet / cnt_p_face_4bet × 100`
- **SQL database field / logic**: cnt_p_face_4bet = SUM(HudCache.cnt_p_face_4bet); cnt_p_call_4bet = SUM(HudCache.cnt_p_call_4bet)
- **Tooltip**: % calling facing a preflop 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs Preflop Squeeze — `call_vs_preflop_squeeze`

- **HUD abbreviation**: `CvSQ`
- **Description**: Percentage of the time that a player called when facing a squeeze on the preflop.
- **Formula**: Number of times the player called a squeeze on the preflop / Number of times the player faced a squeeze on the preflop × 100
- **Formula (code)**: `cnt_p_call_squeeze / cnt_p_face_squeeze × 100`
- **SQL database field / logic**: cnt_p_face_squeeze = SUM(HudCache.cnt_p_face_squeeze); cnt_p_call_squeeze = SUM(HudCache.cnt_p_call_squeeze)
- **Tooltip**: % calling facing a preflop squeeze
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Called a Raise Preflop — `car0`

- **HUD abbreviation**: `CAR0`
- **Description**: Percentage of preflop decisions facing a raise that were calls. Every decision facing a raise counts, so one hand can add several.
- **Formula**: Number of calls of a preflop raise (each call counts; after a call, counting resumes at the next raise) / Number of preflop actions the player took while facing a raise (fold, call or raise; several per hand are possible) × 100
- **Formula (code)**: `car_0 / car_opp_0 × 100`
- **SQL database field / logic**: car_opp_0 = SUM(HudCache.street0CalledRaiseChance); car_0 = SUM(HudCache.street0CalledRaiseDone)
- **Tooltip**: % called a raise preflop
- **Detailed HUD text**: `CAR_pf`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **XML titles**: `CARpre`
- **Note**: Gives the same value as `cold_call` (same counters, same formula).

### Cold 4-Bet — `cfour_B`

- **HUD abbreviation**: `C4B`
- **Description**: Percentage of the time that a player who had not raised before 4-bet when facing a raise and a 3-bet.
- **Formula**: Number of cold 4-bets (a 4-bet by a player who had not raised before) / Number of times a player who had not raised faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `cfb_0 / cfb_opp_0 × 100`
- **SQL database field / logic**: cfb_opp_0 = SUM(HudCache.street0_C4BChance); cfb_0 = SUM(HudCache.street0_C4BDone)
- **Tooltip**: % cold 4 bet preflop/3rd street
- **Detailed HUD text**: `C4B_pf`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### Cold Call Preflop — `cold_call`

- **HUD abbreviation**: `cc`
- **Description**: Percentage of preflop decisions facing a raise that were calls. Reads the same counters as `car0`, so it also counts calls by a player who had already put money in.
- **Formula**: Number of calls of a preflop raise (each call counts; after a call, counting resumes at the next raise) / Number of preflop actions the player took while facing a raise (fold, call or raise; several per hand are possible) × 100
- **Formula (code)**: `CAR_0 / CAR_opp_0 × 100`
- **SQL database field / logic**: CAR_opp_0 = SUM(HudCache.street0CalledRaiseChance); CAR_0 = SUM(HudCache.street0CalledRaiseDone)
- **Tooltip**: % cold call preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **Note**: Gives the same value as `car0` (same counters, same formula).

### Call Preflop 3-Bet — `ctb`

- **HUD abbreviation**: `ctb`
- **Description**: Percentage of the time that the original raiser called a 3-bet: the 3-bets faced that were neither folded to nor 4-bet. Derived by subtraction, so it is an estimate when the counters disagree.
- **Formula**: (Number of times the original raiser faced a 3-bet minus Number of times the original raiser folded to a 3-bet minus Number of preflop 4-bets made by the original raiser) / Number of times the original raiser faced a 3-bet × 100
- **Formula (code)**: `(f3b_opp_0 − f3b_0 − fb_0) / f3b_opp_0 × 100`
- **SQL database field / logic**: f3b_opp_0 = SUM(HudCache.street0_FoldTo3BChance); f3b_0 = SUM(HudCache.street0_FoldTo3BDone); fb_0 = SUM(HudCache.street0_4BDone)
- **Tooltip**: % call 3 bet
- **Detailed HUD text**: `call3B`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### Fold to Preflop 3-Bet — `f_3bet`

- **HUD abbreviation**: `F3B`
- **Description**: Percentage of the time that the original preflop raiser folded when 3-bet.
- **Formula**: Number of times the original raiser folded to a 3-bet / Number of times the original raiser faced a 3-bet × 100
- **Formula (code)**: `f3b_0 / f3b_opp_0 × 100`
- **SQL database field / logic**: f3b_opp_0 = SUM(HudCache.street0_FoldTo3BChance); f3b_0 = SUM(HudCache.street0_FoldTo3BDone)
- **Tooltip**: % fold to 3 bet preflop/3rd street
- **Detailed HUD text**: `F3B_pf`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 equivalent**: Fold to PF 3Bet — `(street0_FoldTo3BDone / street0_FoldTo3BChance) * 100` (same formula)
- **XML titles**: `PFF3`
- **Note**: The HUD abbreviation `F3B` is shared with: `three_B_flop`.

### Fold to Preflop 4-Bet — `f_4bet`

- **HUD abbreviation**: `F4B`
- **Description**: Percentage of the time that a player other than the original raiser (usually the 3-bettor) folded when facing a 4-bet.
- **Formula**: Number of times a player other than the original raiser folded facing a 4-bet / Number of times a player other than the original raiser acted facing a 4-bet × 100
- **Formula (code)**: `f4b_0 / f4b_opp_0 × 100`
- **SQL database field / logic**: f4b_opp_0 = SUM(HudCache.street0_FoldTo4BChance); f4b_0 = SUM(HudCache.street0_FoldTo4BDone)
- **Tooltip**: % fold to 4 bet preflop/3rd street
- **Detailed HUD text**: `F4B_pf`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **XML titles**: `PFF4`
- **Note**: Gives the same value as `fold_vs_4bet` (same counters, same formula). The HUD abbreviation `F4B` is shared with: `four_B_flop`.

### Limpers Faced — `face_limpers`

- **HUD abbreviation**: `FLmp`
- **Description**: The average number of limpers already in the pot when the player first acted preflop, per hand played (limpers are counted only while the pot is unraised). Not a percentage.
- **Formula**: Number of limpers faced, summed over hands (only counted while the pot is unraised) / Number of hands played
- **Formula (code)**: `face_limpers / n`
- **SQL database field / logic**: n = SUM(HudCache.n); face_limpers = SUM(HudCache.street0_FaceLimpers)
- **Tooltip**: avg limpers faced preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_calc_squeeze_defense.py`

### Faced a Raise Preflop — `face_raise_preflop`

- **HUD abbreviation**: `FvRp`
- **Description**: Percentage of hands where the player had to act preflop after someone raised.
- **Formula**: Number of hands where the player acted preflop after a raise / Number of hands played × 100
- **Formula (code)**: `p_face_raise / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); p_face_raise = SUM(HudCache.street0FaceRaise)
- **Tooltip**: % face raise preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### 4-Bet Range (estimate) — `fbr`

- **HUD abbreviation**: `fbr`
- **Description**: An estimate of the share of hands the player 4-bets: the 4-bet rate multiplied by the share of hands that were preflop raises.
- **Formula**: (Number of preflop 4-bets / Number of 4-bet opportunities) × (Number of preflop raises / Number of hands played) × 100
- **Formula (code)**: `(fb_0 / fb_opp_0) × (pfr / n) × 100`
- **SQL database field / logic**: fb_0 = SUM(HudCache.street0_4BDone); fb_opp_0 = SUM(HudCache.street0_4BChance); pfr = SUM(HudCache.street0Aggr); n = SUM(HudCache.n)
- **Tooltip**: 4 bet range
- **Detailed HUD text**: `4Brange`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Note**: Historical estimate of the four-bet range: the four-bet rate multiplied by the share of hands that were preflop raises.

### How often the player folded when facing a preflop 3-bet. — `fold_to_3bet_preflop`

- **HUD abbreviation**: `Fold to 3-bet (preflop)`
- **Description**: How often the player folded when facing a preflop 3-bet.
- **Formula (code)**: `decisions matching the numerator {'response': 'fold'} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'preflop', 'situation': 'facing_3bet'}
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Analytics definition (metric fold_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### Fold to Squeeze — `fold_to_squeeze`

- **HUD abbreviation**: `FvSq`
- **Description**: Percentage of the time that a player folded to a squeeze after having opened or called the raise.
- **Formula**: Number of times the player folded to a squeeze / Number of times the player faced a squeeze after opening or calling × 100
- **Formula (code)**: `sqzdef_fold / sqzdef_opp × 100`
- **SQL database field / logic**: sqzdef_opp = SUM(HudCache.street0_FoldToSqueezeChance); sqzdef_fold = SUM(HudCache.street0_FoldToSqueezeDone)
- **Tooltip**: % fold to squeeze
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_squeeze_defense.py`

### Fold to Preflop 4-Bet — `fold_vs_4bet`

- **HUD abbreviation**: `f4b`
- **Description**: Percentage of the time that a player other than the original raiser (usually the 3-bettor) folded when facing a 4-bet. Reads the same counters as `f_4bet`.
- **Formula**: Number of times a player other than the original raiser folded facing a 4-bet / Number of times a player other than the original raiser acted facing a 4-bet × 100
- **Formula (code)**: `F4B_0 / F4B_opp_0 × 100`
- **SQL database field / logic**: F4B_opp_0 = SUM(HudCache.street0_FoldTo4BChance); F4B_0 = SUM(HudCache.street0_FoldTo4BDone)
- **Tooltip**: % fold vs 4bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **Note**: Gives the same value as `f_4bet` (same counters, same formula).

### Fold vs Preflop 3-Bet — `fold_vs_preflop_3bet`

- **HUD abbreviation**: `Fv3B`
- **Description**: Percentage of the time that a player folded when facing a 3-bet on the preflop. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 3-bet on the preflop minus Number of times the player called a 3-bet on the preflop minus Number of times the player raised a 3-bet on the preflop) / Number of times the player faced a 3-bet on the preflop × 100
- **Formula (code)**: `(cnt_p_face_3bet − cnt_p_call_3bet − cnt_p_raise_3bet) / cnt_p_face_3bet × 100`
- **SQL database field / logic**: cnt_p_face_3bet = SUM(HudCache.cnt_p_face_3bet); cnt_p_call_3bet = SUM(HudCache.cnt_p_call_3bet); cnt_p_raise_3bet = SUM(HudCache.cnt_p_raise_3bet)
- **Tooltip**: % folding facing a preflop 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Preflop 4-Bet — `fold_vs_preflop_4bet`

- **HUD abbreviation**: `Fv4B`
- **Description**: Percentage of the time that a player folded when facing a 4-bet on the preflop. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 4-bet on the preflop minus Number of times the player called a 4-bet on the preflop minus Number of times the player raised a 4-bet on the preflop) / Number of times the player faced a 4-bet on the preflop × 100
- **Formula (code)**: `(cnt_p_face_4bet − cnt_p_call_4bet − cnt_p_raise_4bet) / cnt_p_face_4bet × 100`
- **SQL database field / logic**: cnt_p_face_4bet = SUM(HudCache.cnt_p_face_4bet); cnt_p_call_4bet = SUM(HudCache.cnt_p_call_4bet); cnt_p_raise_4bet = SUM(HudCache.cnt_p_raise_4bet)
- **Tooltip**: % folding facing a preflop 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Preflop Squeeze — `fold_vs_preflop_squeeze`

- **HUD abbreviation**: `FvSQ`
- **Description**: Percentage of the time that a player folded when facing a squeeze on the preflop. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a squeeze on the preflop minus Number of times the player called a squeeze on the preflop minus Number of times the player raised a squeeze on the preflop) / Number of times the player faced a squeeze on the preflop × 100
- **Formula (code)**: `(cnt_p_face_squeeze − cnt_p_call_squeeze − cnt_p_raise_squeeze) / cnt_p_face_squeeze × 100`
- **SQL database field / logic**: cnt_p_face_squeeze = SUM(HudCache.cnt_p_face_squeeze); cnt_p_call_squeeze = SUM(HudCache.cnt_p_call_squeeze); cnt_p_raise_squeeze = SUM(HudCache.cnt_p_raise_squeeze)
- **Tooltip**: % folding facing a preflop squeeze
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Preflop 4-Bet — `four_B`

- **HUD abbreviation**: `4B`
- **Description**: Percentage of the time that the original raiser re-raised (4-bet) after being 3-bet.
- **Formula**: Number of preflop 4-bets made by the original raiser / Number of times the original raiser faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fb_0 / fb_opp_0 × 100`
- **SQL database field / logic**: fb_opp_0 = SUM(HudCache.street0_4BChance); fb_0 = SUM(HudCache.street0_4BDone)
- **Tooltip**: % 4 bet preflop/3rd street
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **XML titles**: `PF4`

### Preflop 4-bet. — `four_bet`

- **HUD abbreviation**: `4Bet`
- **Description**: Preflop 4-bet.
- **Formula (code)**: `100 * street0_4BDone / street0_4BChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street0_4BDone, street0_4BChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### 4-Bet from Big Blind — `four_bet_bb`

- **HUD abbreviation**: `4B BB`
- **Description**: Percentage of the time that a player in the big blind 4-bet after being 3-bet.
- **Formula**: Number of preflop 4-bets made from the big blind / Number of times the player, in the big blind, faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fb_bb / fb_opp_bb × 100`
- **SQL database field / logic**: fb_opp_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_4BChance ELSE 0 END); fb_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_4BDone ELSE 0 END)
- **Tooltip**: % 4B BB preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### 4-Bet from Button — `four_bet_btn`

- **HUD abbreviation**: `4B BTN`
- **Description**: Percentage of the time that a player in the button 4-bet after being 3-bet.
- **Formula**: Number of preflop 4-bets made from the button / Number of times the player, in the button, faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fb_btn / fb_opp_btn × 100`
- **SQL database field / logic**: fb_opp_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_4BChance ELSE 0 END); fb_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_4BDone ELSE 0 END)
- **Tooltip**: % 4B BTN preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### 4-Bet from Cutoff — `four_bet_co`

- **HUD abbreviation**: `4B CO`
- **Description**: Percentage of the time that a player in the cutoff 4-bet after being 3-bet.
- **Formula**: Number of preflop 4-bets made from the cutoff / Number of times the player, in the cutoff, faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fb_co / fb_opp_co × 100`
- **SQL database field / logic**: fb_opp_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_4BChance ELSE 0 END); fb_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_4BDone ELSE 0 END)
- **Tooltip**: % 4B CO preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### 4-Bet from Early Position — `four_bet_ep`

- **HUD abbreviation**: `4B EP`
- **Description**: Percentage of the time that a player in early position 4-bet after being 3-bet.
- **Formula**: Number of preflop 4-bets made from early position / Number of times the player, in early position, faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fb_ep / fb_opp_ep × 100`
- **SQL database field / logic**: fb_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_4BChance ELSE 0 END); fb_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_4BDone ELSE 0 END)
- **Tooltip**: % 4B EP preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### 4-Bet from Middle Position — `four_bet_mp`

- **HUD abbreviation**: `4B MP`
- **Description**: Percentage of the time that a player in middle position 4-bet after being 3-bet.
- **Formula**: Number of preflop 4-bets made from middle position / Number of times the player, in middle position, faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fb_mp / fb_opp_mp × 100`
- **SQL database field / logic**: fb_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_4BChance ELSE 0 END); fb_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_4BDone ELSE 0 END)
- **Tooltip**: % 4B MP preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### 4-Bet Range — `four_bet_range`

- **HUD abbreviation**: `4BR`
- **Description**: Preflop 4-bets as a share of all hands played.
- **Formula**: Number of preflop 4-bets made by the original raiser / Number of hands played × 100
- **Formula (code)**: `fb_0 / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); fb_0 = SUM(HudCache.street0_4BDone)
- **Tooltip**: 4-bet range
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### 4-Bet from Small Blind — `four_bet_sb`

- **HUD abbreviation**: `4B SB`
- **Description**: Percentage of the time that a player in the small blind 4-bet after being 3-bet.
- **Formula**: Number of preflop 4-bets made from the small blind / Number of times the player, in the small blind, faced a 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fb_sb / fb_opp_sb × 100`
- **SQL database field / logic**: fb_opp_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_4BChance ELSE 0 END); fb_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_4BDone ELSE 0 END)
- **Tooltip**: % 4B SB preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### Open Raise (small) — `gp_2x`

- **HUD abbreviation**: `2X`
- **Description**: Percentage of the time that a player opened an unopened pot with a raise of less than 40% of their stack.
- **Formula**: Number of open raises of less than 40% of the stack / Number of times the player could open an unopened pot × 100
- **Formula (code)**: `gp_2x / gp_open_opp × 100`
- **SQL database field / logic**: gp_open_opp = SUM(HudCache.cnt_gp_open_opp); gp_2x = SUM(HudCache.cnt_gp_2x)
- **Tooltip**: % open-raise (<40% stack)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Open Limp (GP) — `gp_limp`

- **HUD abbreviation**: `Limp`
- **Description**: Percentage of the time that a player opened an unopened pot by limping, over the same opportunities as the open raise and open shove.
- **Formula**: Number of open limps / Number of times the player could open an unopened pot × 100
- **Formula (code)**: `gp_limp / gp_open_opp × 100`
- **SQL database field / logic**: gp_open_opp = SUM(HudCache.cnt_gp_open_opp); gp_limp = SUM(HudCache.cnt_gp_limp)
- **Tooltip**: % open-limp
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Open Shove — `gp_os`

- **HUD abbreviation**: `OS`
- **Description**: Percentage of the time that a player opened an unopened pot with a raise of 40% of their stack or more.
- **Formula**: Number of open shoves (open raises of 40% of the stack or more) / Number of times the player could open an unopened pot × 100
- **Formula (code)**: `gp_os / gp_open_opp × 100`
- **SQL database field / logic**: gp_open_opp = SUM(HudCache.cnt_gp_open_opp); gp_os = SUM(HudCache.cnt_gp_os)
- **Tooltip**: % open-shove (>=40% stack)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Isolation Raise (deprecated) — `iso`

- **HUD abbreviation**: `iso`
- **Description**: Shows no data: isolation raises cannot be aggregated from the cache.
- **Formula (code)**: `no data (deprecated)`
- **SQL database field / logic**: none: isolation raises cannot be aggregated from HudCache
- **Tooltip**: % isolation raise (deprecated)
- **Games**: none (shows no data)
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: deprecated

### Limp — `limp`

- **HUD abbreviation**: `limp`
- **Description**: Percentage of the time that a player put money in preflop without raising (VPIP hands that were not PFR hands), over their VPIP opportunities.
- **Formula**: (Number of hands where the player voluntarily put money in the pot preflop (call, raise or complete; posting a blind does not count) minus Number of hands where the player raised preflop) / Number of hands where the player had the chance to put money in voluntarily (excludes walks and blinds folded or all-in without a decision) × 100
- **Formula (code)**: `(vpip − pfr) / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI); pfr = SUM(HudCache.street0Aggr)
- **Tooltip**: % limp preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### Open Limp — `open_limp`

- **HUD abbreviation**: `openlimp`
- **Description**: Percentage of the time that a player, first to enter an unopened pot, called the big blind instead of raising or folding.
- **Formula**: Number of open limps (first to enter the pot, by calling) / Number of times the pot was unopened when the player acted × 100
- **Formula (code)**: `open_limp / open_limp_opp × 100`
- **SQL database field / logic**: open_limp_opp = SUM(HudCache.street0OpenLimpChance); open_limp = SUM(HudCache.street0OpenLimp)
- **Tooltip**: % open limp preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw

### Price of Preflop Raise Faced — `p_2bet_facing`

- **HUD abbreviation**: `2Bvs`
- **Description**: The average price the player was offered when facing a preflop raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the preflop raises faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of preflop raises faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(p_2bet_facing_bp / p_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_2bet_facing_cnt = SUM(HudCache.cnt_p_2bet_facing); p_2bet_facing_bp = SUM(HudCache.val_p_2bet_facing_bp)
- **Tooltip**: avg 2bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_preflop_raise_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Preflop 3-Bet Faced — `p_3bet_facing`

- **HUD abbreviation**: `3Bvs`
- **Description**: The average price the player was offered when facing a preflop 3-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the preflop 3-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of preflop 3-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(p_3bet_facing_bp / p_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_3bet_facing_cnt = SUM(HudCache.cnt_p_3bet_facing); p_3bet_facing_bp = SUM(HudCache.val_p_3bet_facing_bp)
- **Tooltip**: avg 3bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_preflop_raise_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Preflop 4-Bet Faced — `p_4bet_facing`

- **HUD abbreviation**: `4Bvs`
- **Description**: The average price the player was offered when facing a preflop 4-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the preflop 4-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of preflop 4-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(p_4bet_facing_bp / p_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_4bet_facing_cnt = SUM(HudCache.cnt_p_4bet_facing); p_4bet_facing_bp = SUM(HudCache.val_p_4bet_facing_bp)
- **Tooltip**: avg 4bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Preflop 5-Bet Faced — `p_5bet_facing`

- **HUD abbreviation**: `5Bvs`
- **Description**: The average price the player was offered when facing a preflop 5-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the preflop 5-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of preflop 5-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(p_5bet_facing_bp / p_5bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_5bet_facing_cnt = SUM(HudCache.cnt_p_5bet_facing); p_5bet_facing_bp = SUM(HudCache.val_p_5bet_facing_bp)
- **Tooltip**: avg 5bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Preflop Raise Faced — `p_raise_facing`

- **HUD abbreviation**: `PRvs`
- **Description**: The average price the player was offered when facing a preflop raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot. When several raises are faced on the street, the last one counts.
- **Formula**: Sum of prices of the preflop raises (most recent level) faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of preflop raises (most recent level) faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(p_raise_facing_bp / p_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_raise_facing_cnt = SUM(HudCache.cnt_p_raise_facing); p_raise_facing_bp = SUM(HudCache.val_p_raise_facing_bp)
- **Tooltip**: avg preflop raise faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`, `test_calc_preflop_raise_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Preflop Raise Size — `p_raise_made`

- **HUD abbreviation**: `PRz`
- **Description**: The average size of the player's first preflop raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those raises: raise-to amount / pot before the raise, in basis points / Number of first raises made on the preflop / 10 000 × 100
- **Formula (code)**: `(p_raise_made_bp / p_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_raise_made_cnt = SUM(HudCache.cnt_p_raise_made); p_raise_made_bp = SUM(HudCache.val_p_raise_made_bp)
- **Tooltip**: avg preflop raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`, `test_calc_raise_made.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Preflop Raise Size (2nd raise) — `p_raise_made_2`

- **HUD abbreviation**: `PRz2`
- **Description**: The average size of the player's second preflop raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those second raises: raise-to amount / pot before the raise, in basis points / Number of second raises made by the player on the preflop / 10 000 × 100
- **Formula (code)**: `(p_raise_made_2_bp / p_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: p_raise_made_2_cnt = SUM(HudCache.cnt_p_raise_made_2); p_raise_made_2_bp = SUM(HudCache.val_p_raise_made_2_bp)
- **Tooltip**: avg 2nd preflop raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Preflop Raise (PFR) — `pfr`

- **HUD abbreviation**: `p`
- **Description**: Percentage of the time that a player raised preflop when they had the chance to.
- **Formula**: Number of hands where the player raised preflop / Number of hands where the player had the chance to raise preflop × 100
- **Formula (code)**: `pfr / pfr_opp × 100`
- **SQL database field / logic**: pfr_opp = SUM(HudCache.street0AggrChance); pfr = SUM(HudCache.street0Aggr)
- **Tooltip**: Preflop/3rd street raise %
- **Detailed HUD text**: `pfr`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 equivalent**: PFR — `(street0Aggr / street0AggrChance) * 100` (same formula)
- **PT4 difference**: PT4 counts a preflop raise opportunity from the player's preflop actions and stack; fpdb's street0AggrChance is any preflop decision with a raise still possible.
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `PFR`
- **Note**: The HUD abbreviation `p` is shared with: `playerprofile`, `profit100`.

### How often each seat raised when it had a preflop decision. — `preflop_raise_frequency_by_position`

- **HUD abbreviation**: `Preflop raise frequency by position`
- **Description**: How often each seat raised when it had a preflop decision.
- **Formula (code)**: `decisions matching the numerator {'response': ['raise', 'complete']} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'preflop'}; grouped by position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Analytics definition (metric raise_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### Raise vs Preflop 3-Bet — `raise_vs_preflop_3bet`

- **HUD abbreviation**: `Rv3B`
- **Description**: Percentage of the time that a player raised when facing a 3-bet on the preflop.
- **Formula**: Number of times the player raised a 3-bet on the preflop / Number of times the player faced a 3-bet on the preflop × 100
- **Formula (code)**: `cnt_p_raise_3bet / cnt_p_face_3bet × 100`
- **SQL database field / logic**: cnt_p_face_3bet = SUM(HudCache.cnt_p_face_3bet); cnt_p_raise_3bet = SUM(HudCache.cnt_p_raise_3bet)
- **Tooltip**: % raising facing a preflop 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Raise vs Preflop 4-Bet — `raise_vs_preflop_4bet`

- **HUD abbreviation**: `Rv4B`
- **Description**: Percentage of the time that a player raised when facing a 4-bet on the preflop.
- **Formula**: Number of times the player raised a 4-bet on the preflop / Number of times the player faced a 4-bet on the preflop × 100
- **Formula (code)**: `cnt_p_raise_4bet / cnt_p_face_4bet × 100`
- **SQL database field / logic**: cnt_p_face_4bet = SUM(HudCache.cnt_p_face_4bet); cnt_p_raise_4bet = SUM(HudCache.cnt_p_raise_4bet)
- **Tooltip**: % raising facing a preflop 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs Preflop Squeeze — `raise_vs_preflop_squeeze`

- **HUD abbreviation**: `RvSQ`
- **Description**: Percentage of the time that a player raised when facing a squeeze on the preflop.
- **Formula**: Number of times the player raised a squeeze on the preflop / Number of times the player faced a squeeze on the preflop × 100
- **Formula (code)**: `cnt_p_raise_squeeze / cnt_p_face_squeeze × 100`
- **SQL database field / logic**: cnt_p_face_squeeze = SUM(HudCache.cnt_p_face_squeeze); cnt_p_raise_squeeze = SUM(HudCache.cnt_p_raise_squeeze)
- **Tooltip**: % raising facing a preflop squeeze
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise first in (open raise). — `rfi`

- **HUD abbreviation**: `RFI`
- **Description**: Raise first in (open raise).
- **Formula (code)**: `100 * raisedFirstIn / raiseFirstInChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): raisedFirstIn, raiseFirstInChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Raise First In from Early Position — `rfi_early_position`

- **HUD abbreviation**: `rfi_ep`
- **Description**: Percentage of the time that a player in early position raised when the pot was unopened.
- **Formula**: Number of raises first in from early position / Number of times the player was first to act into an unopened pot in early position × 100
- **Formula (code)**: `rfi_ep / rfi_opp_ep × 100`
- **SQL database field / logic**: rfi_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.raiseFirstInChance ELSE 0 END); rfi_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.raisedFirstIn ELSE 0 END)
- **Tooltip**: % RFI early position
- **Detailed HUD text**: `rfi_early_pos`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Raise First In from Late Position — `rfi_late_position`

- **HUD abbreviation**: `rfi_lp`
- **Description**: Percentage of the time that a player in the cutoff raised when the pot was unopened. The button is counted apart, so it is not included.
- **Formula**: Number of raises first in from the cutoff (late position) / Number of times the player was first to act into an unopened pot in the cutoff (late position) × 100
- **Formula (code)**: `rfi_lp / rfi_opp_lp × 100`
- **SQL database field / logic**: rfi_opp_lp = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.raiseFirstInChance ELSE 0 END); rfi_lp = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.raisedFirstIn ELSE 0 END)
- **Tooltip**: % RFI late position
- **Detailed HUD text**: `rfi_late_pos`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Raise First In from Middle Position — `rfi_middle_position`

- **HUD abbreviation**: `rfi_mp`
- **Description**: Percentage of the time that a player in middle position raised when the pot was unopened.
- **Formula**: Number of raises first in from middle position / Number of times the player was first to act into an unopened pot in middle position × 100
- **Formula (code)**: `rfi_mp / rfi_opp_mp × 100`
- **SQL database field / logic**: rfi_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.raiseFirstInChance ELSE 0 END); rfi_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.raisedFirstIn ELSE 0 END)
- **Tooltip**: % RFI middle position
- **Detailed HUD text**: `rfi_middle_pos`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Raise First In (total) — `rfi_total`

- **HUD abbreviation**: `rfi`
- **Description**: Meant as the percentage of the time that a player opened the pot with a raise. As written it is PFR minus a `3bet` key the HUD never fills, so in practice it equals PFR.
- **Formula**: (Number of preflop raises − Number of preflop 3-bets under the never-filled key 3bet, never below 0) / Number of preflop raise opportunities × 100
- **Formula (code)**: `max(0, pfr − 3bet) / pfr_opp × 100`
- **SQL database field / logic**: pfr = SUM(HudCache.street0Aggr); pfr_opp = SUM(HudCache.street0AggrChance); 3bet is not selected by any HUD query, so it is always 0
- **Tooltip**: % raise first in
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Note**: In practice this equals PFR. The measured raise-first-in rate is `rfi_early_position`, `rfi_middle_position` and `rfi_late_position` pooled by the position queries.

### Squeeze — `squeeze`

- **HUD abbreviation**: `SQZ`
- **Description**: Percentage of the time that a player 3-bet after a raise and at least one call.
- **Formula**: Number of squeezes (a 3-bet after a raise and at least one call) / Number of times the player faced a raise and at least one call with the chance to 3-bet × 100
- **Formula (code)**: `sqz_0 / sqz_opp_0 × 100`
- **SQL database field / logic**: sqz_opp_0 = SUM(HudCache.street0_SqueezeChance); sqz_0 = SUM(HudCache.street0_SqueezeDone)
- **Tooltip**: % squeeze preflop
- **Detailed HUD text**: `SQZ_pf`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Squeeze from Big Blind — `squeeze_bb`

- **HUD abbreviation**: `SQZ BB`
- **Description**: Percentage of the time that a player in the big blind 3-bet after a raise and at least one call.
- **Formula**: Number of squeezes made from the big blind / Number of squeeze opportunities in the big blind × 100
- **Formula (code)**: `sqz_bb / sqz_opp_bb × 100`
- **SQL database field / logic**: sqz_opp_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_SqueezeDone ELSE 0 END)
- **Tooltip**: % SQZ BB preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Squeeze from Button — `squeeze_btn`

- **HUD abbreviation**: `SQZ BTN`
- **Description**: Percentage of the time that a player in the button 3-bet after a raise and at least one call.
- **Formula**: Number of squeezes made from the button / Number of squeeze opportunities in the button × 100
- **Formula (code)**: `sqz_btn / sqz_opp_btn × 100`
- **SQL database field / logic**: sqz_opp_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_SqueezeDone ELSE 0 END)
- **Tooltip**: % SQZ BTN preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Squeeze from Cutoff — `squeeze_co`

- **HUD abbreviation**: `SQZ CO`
- **Description**: Percentage of the time that a player in the cutoff 3-bet after a raise and at least one call.
- **Formula**: Number of squeezes made from the cutoff / Number of squeeze opportunities in the cutoff × 100
- **Formula (code)**: `sqz_co / sqz_opp_co × 100`
- **SQL database field / logic**: sqz_opp_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_SqueezeDone ELSE 0 END)
- **Tooltip**: % SQZ CO preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Squeeze from Early Position — `squeeze_ep`

- **HUD abbreviation**: `SQZ EP`
- **Description**: Percentage of the time that a player in early position 3-bet after a raise and at least one call.
- **Formula**: Number of squeezes made from early position / Number of squeeze opportunities in early position × 100
- **Formula (code)**: `sqz_ep / sqz_opp_ep × 100`
- **SQL database field / logic**: sqz_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_SqueezeDone ELSE 0 END)
- **Tooltip**: % SQZ EP preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Squeeze from Middle Position — `squeeze_mp`

- **HUD abbreviation**: `SQZ MP`
- **Description**: Percentage of the time that a player in middle position 3-bet after a raise and at least one call.
- **Formula**: Number of squeezes made from middle position / Number of squeeze opportunities in middle position × 100
- **Formula (code)**: `sqz_mp / sqz_opp_mp × 100`
- **SQL database field / logic**: sqz_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_SqueezeDone ELSE 0 END)
- **Tooltip**: % SQZ MP preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Squeeze Range — `squeeze_range`

- **HUD abbreviation**: `SQZR`
- **Description**: Squeezes as a share of all hands played.
- **Formula**: Number of squeezes (a 3-bet after a raise and at least one call) / Number of hands played × 100
- **Formula (code)**: `sqz_0 / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); sqz_0 = SUM(HudCache.street0_SqueezeDone)
- **Tooltip**: squeeze range
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Squeeze from Small Blind — `squeeze_sb`

- **HUD abbreviation**: `SQZ SB`
- **Description**: Percentage of the time that a player in the small blind 3-bet after a raise and at least one call.
- **Formula**: Number of squeezes made from the small blind / Number of squeeze opportunities in the small blind × 100
- **Formula (code)**: `sqz_sb / sqz_opp_sb × 100`
- **SQL database field / logic**: sqz_opp_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_SqueezeChance ELSE 0 END); sqz_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_SqueezeDone ELSE 0 END)
- **Tooltip**: % SQZ SB preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_player_situations.py`

### Straddle — `straddle`

- **HUD abbreviation**: `Str`
- **Description**: Percentage of hands where the player posted a straddle.
- **Formula**: Number of straddles posted / Number of hands played × 100
- **Formula (code)**: `straddle_done / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); straddle_done = SUM(HudCache.flg_blind_k)
- **Tooltip**: % straddle
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_special_blinds.py`
- **Note**: The HUD abbreviation `Str` is shared with: `aof_straight`.

### Preflop 3-Bet — `three_B`

- **HUD abbreviation**: `3B`
- **Description**: Percentage of the time that a player re-raised (3-bet) when facing a single preflop raise.
- **Formula**: Number of preflop 3-bets made / Number of times the player faced a single preflop raise with the chance to 3-bet × 100
- **Formula (code)**: `tb_0 / tb_opp_0 × 100`
- **SQL database field / logic**: tb_opp_0 = SUM(HudCache.street0_3BChance); tb_0 = SUM(HudCache.street0_3BDone)
- **Tooltip**: % 3 bet preflop/3rd street
- **Detailed HUD text**: `3B_pf`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 equivalent**: 3Bet Preflop — `(street0_3BDone / street0_3BChance) * 100` (same formula)
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `PF3`

### Preflop 3-bet. — `three_bet`

- **HUD abbreviation**: `3Bet`
- **Description**: Preflop 3-bet.
- **Formula (code)**: `100 * street0_3BDone / street0_3BChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street0_3BDone, street0_3BChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### 3-Bet from Big Blind — `three_bet_bb`

- **HUD abbreviation**: `3B BB`
- **Description**: Percentage of the time that a player in the big blind 3-bet when facing a single raise.
- **Formula**: Number of preflop 3-bets made from the big blind / Number of times the player faced a single preflop raise from the big blind with the chance to 3-bet × 100
- **Formula (code)**: `tb_bb / tb_opp_bb × 100`
- **SQL database field / logic**: tb_opp_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_3BChance ELSE 0 END); tb_bb = SUM(CASE WHEN HudCache.position = 'B' THEN HudCache.street0_3BDone ELSE 0 END)
- **Tooltip**: % 3B BB preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### 3-Bet from Button — `three_bet_btn`

- **HUD abbreviation**: `3B BTN`
- **Description**: Percentage of the time that a player in the button 3-bet when facing a single raise.
- **Formula**: Number of preflop 3-bets made from the button / Number of times the player faced a single preflop raise from the button with the chance to 3-bet × 100
- **Formula (code)**: `tb_btn / tb_opp_btn × 100`
- **SQL database field / logic**: tb_opp_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_3BChance ELSE 0 END); tb_btn = SUM(CASE WHEN HudCache.position = 'D' THEN HudCache.street0_3BDone ELSE 0 END)
- **Tooltip**: % 3B BTN preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### 3-Bet from Cutoff — `three_bet_co`

- **HUD abbreviation**: `3B CO`
- **Description**: Percentage of the time that a player in the cutoff 3-bet when facing a single raise.
- **Formula**: Number of preflop 3-bets made from the cutoff / Number of times the player faced a single preflop raise from the cutoff with the chance to 3-bet × 100
- **Formula (code)**: `tb_co / tb_opp_co × 100`
- **SQL database field / logic**: tb_opp_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_3BChance ELSE 0 END); tb_co = SUM(CASE WHEN HudCache.position = 'C' THEN HudCache.street0_3BDone ELSE 0 END)
- **Tooltip**: % 3B CO preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### 3-Bet from Early Position — `three_bet_ep`

- **HUD abbreviation**: `3B EP`
- **Description**: Percentage of the time that a player in early position 3-bet when facing a single raise.
- **Formula**: Number of preflop 3-bets made from early position / Number of times the player faced a single preflop raise from early position with the chance to 3-bet × 100
- **Formula (code)**: `tb_ep / tb_opp_ep × 100`
- **SQL database field / logic**: tb_opp_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_3BChance ELSE 0 END); tb_ep = SUM(CASE WHEN HudCache.position = 'E' THEN HudCache.street0_3BDone ELSE 0 END)
- **Tooltip**: % 3B EP preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### 3-Bet from Middle Position — `three_bet_mp`

- **HUD abbreviation**: `3B MP`
- **Description**: Percentage of the time that a player in middle position 3-bet when facing a single raise.
- **Formula**: Number of preflop 3-bets made from middle position / Number of times the player faced a single preflop raise from middle position with the chance to 3-bet × 100
- **Formula (code)**: `tb_mp / tb_opp_mp × 100`
- **SQL database field / logic**: tb_opp_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_3BChance ELSE 0 END); tb_mp = SUM(CASE WHEN HudCache.position = 'M' THEN HudCache.street0_3BDone ELSE 0 END)
- **Tooltip**: % 3B MP preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### 3-Bet Range — `three_bet_range`

- **HUD abbreviation**: `3BR`
- **Description**: Preflop 3-bets as a share of all hands played: how wide a range the player 3-bets with.
- **Formula**: Number of preflop 3-bets made / Number of hands played × 100
- **Formula (code)**: `tb_0 / n × 100`
- **SQL database field / logic**: n = SUM(HudCache.n); tb_0 = SUM(HudCache.street0_3BDone)
- **Tooltip**: 3-bet range
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### 3-Bet from Small Blind — `three_bet_sb`

- **HUD abbreviation**: `3B SB`
- **Description**: Percentage of the time that a player in the small blind 3-bet when facing a single raise.
- **Formula**: Number of preflop 3-bets made from the small blind / Number of times the player faced a single preflop raise from the small blind with the chance to 3-bet × 100
- **Formula (code)**: `tb_sb / tb_opp_sb × 100`
- **SQL database field / logic**: tb_opp_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_3BChance ELSE 0 END); tb_sb = SUM(CASE WHEN HudCache.position = 'S' THEN HudCache.street0_3BDone ELSE 0 END)
- **Tooltip**: % 3B SB preflop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### Voluntarily Put $ In Pot (VPIP) — `vpip`

- **HUD abbreviation**: `v`
- **Description**: Percentage of the time that a player put money in the pot preflop by choice: calling, raising or completing. Posting a blind is not voluntary, and walks or blinds folded without a decision are left out of the opportunities.
- **Formula**: Number of hands where the player voluntarily put money in the pot preflop (call, raise or complete; posting a blind does not count) / Number of hands where the player had the chance to put money in voluntarily (excludes walks and blinds folded or all-in without a decision) × 100
- **Formula (code)**: `vpip / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI)
- **Tooltip**: Voluntarily put in preflop/3rd street %
- **Detailed HUD text**: `vpip`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 equivalent**: VPIP — `(street0VPI / (street0VPIChance)) * 100` (same formula)
- **PT4 difference**: PT4's VPIP opportunity is every hand but a walk; fpdb's also leaves out a blind that is all-in before acting, or folds without having called or raised.
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `VPIP`
- **Note**: Gives the same value as `aof_allin` (same counters, same formula). The HUD abbreviation `v` is shared with: `bbstack`.

### VPIP / PFR ratio — `vpip_pfr_ratio`

- **HUD abbreviation**: `v/p`
- **Description**: How much of a player's voluntary play is raising: VPIP divided by PFR. 1.0 means every hand played was raised; large values mean a lot of calling. Infinite when PFR is 0.
- **Formula**: (Number of VPIP hands / VPIP opportunities) / (Number of preflop raises / raise opportunities)
- **Formula (code)**: `(vpip / vpip_opp) / (pfr / pfr_opp)`
- **SQL database field / logic**: vpip = SUM(HudCache.street0VPI); vpip_opp = SUM(HudCache.street0VPIChance); pfr = SUM(HudCache.street0Aggr); pfr_opp = SUM(HudCache.street0AggrChance)
- **Tooltip**: VPIP/PFR ratio
- **Detailed HUD text**: `vpip/pfr`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Note**: A plain ratio of the two percentages (not multiplied by 100); shows infinity when PFR is 0.

## Steal and blinds

### Average Blinds Posted — `amt_blind`

- **HUD abbreviation**: `Blind`
- **Description**: The average amount of blinds and antes the player posted per hand, in the table's currency.
- **Formula**: Sum of blinds and antes posted, in cents / Number of hands played × 0.01
- **Formula (code)**: `0.01 × amt_blind / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_blind = SUM(HudCache.amt_blind)
- **Tooltip**: avg blinds posted
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`

### Call vs Steal (deprecated) — `call_vs_steal`

- **HUD abbreviation**: `cvs`
- **Description**: Shows no data: it needs information about the other players that the cache cannot aggregate.
- **Formula (code)**: `no data (deprecated)`
- **SQL database field / logic**: none: needs data about other players that HudCache cannot aggregate
- **Tooltip**: % call vs steal (deprecated)
- **Games**: none (shows no data)
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: deprecated

### Fold Big Blind to Steal — `f_BB_steal`

- **HUD abbreviation**: `fBB`
- **Description**: Percentage of the time that a player in the big blind folded to a steal attempt.
- **Formula**: Number of times the player folded the big blind to a steal attempt / Number of times the player was in the big blind facing a steal attempt × 100
- **Formula (code)**: `bbnotdef / bbstolen × 100`
- **SQL database field / logic**: bbstolen = SUM(HudCache.foldBbToStealChance); bbnotdef = SUM(HudCache.foldedBbToSteal)
- **Tooltip**: % folded BB to steal
- **Detailed HUD text**: `fBB_s`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Fold Small Blind to Steal — `f_SB_steal`

- **HUD abbreviation**: `fSB`
- **Description**: Percentage of the time that a player in the small blind folded to a steal attempt.
- **Formula**: Number of times the player folded the small blind to a steal attempt / Number of times the player was in the small blind facing a steal attempt × 100
- **Formula (code)**: `sbnotdef / sbstolen × 100`
- **SQL database field / logic**: sbstolen = SUM(HudCache.foldSbToStealChance); sbnotdef = SUM(HudCache.foldedSbToSteal)
- **Tooltip**: % folded SB to steal
- **Detailed HUD text**: `fSB_s`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Fold Blind to Steal — `f_steal`

- **HUD abbreviation**: `fB`
- **Description**: Percentage of the time that a player in either blind folded to a steal attempt.
- **Formula**: (Number of times the player folded the small blind to a steal attempt plus Number of times the player folded the big blind to a steal attempt) / (Number of times the player was in the small blind facing a steal attempt plus Number of times the player was in the big blind facing a steal attempt) × 100
- **Formula (code)**: `(sbnotdef + bbnotdef) / (sbstolen + bbstolen) × 100`
- **SQL database field / logic**: sbnotdef = SUM(HudCache.foldedSbToSteal); bbnotdef = SUM(HudCache.foldedBbToSteal); sbstolen = SUM(HudCache.foldSbToStealChance); bbstolen = SUM(HudCache.foldBbToStealChance)
- **Tooltip**: % folded blind to steal
- **Detailed HUD text**: `fB_s`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **PT4 equivalent**: Fold to Steal — `((foldedSbToSteal + foldedBbToSteal) / (foldSbToStealChance + foldBbToStealChance)) * 100` (same formula)

### Fold the big blind facing a steal attempt. — `fold_bb_to_steal`

- **HUD abbreviation**: `Fold BB to Steal`
- **Description**: Fold the big blind facing a steal attempt.
- **Formula (code)**: `100 * foldedBbToSteal / foldBbToStealChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): foldedBbToSteal, foldBbToStealChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Re-raise Steal — `raiseToSteal`

- **HUD abbreviation**: `RST`
- **Description**: Percentage of the time that a player in the blinds re-raised a steal attempt.
- **Formula**: Number of times the player re-raised a steal attempt from the blinds / Number of times the player was in the blinds facing a steal attempt × 100
- **Formula (code)**: `rts / rts_opp × 100`
- **SQL database field / logic**: rts_opp = SUM(HudCache.raiseToStealChance); rts = SUM(HudCache.raiseToStealDone)
- **Tooltip**: % raise to steal
- **Detailed HUD text**: `RST_pf`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Re-steal (estimate) — `resteal`

- **HUD abbreviation**: `resteal`
- **Description**: An estimate of how often the player re-steals, built from the overall 3-bet counts with fixed 0.7 and 0.6 factors. It is not a count of re-steals: use Re-raise Steal for the measured value.
- **Formula**: (0.7 × Number of preflop 3-bets) / (0.6 × Number of 3-bet opportunities) × 100
- **Formula (code)**: `(0.7 × tb_0) / (0.6 × tb_opp_0) × 100`
- **SQL database field / logic**: tb_0 = SUM(HudCache.street0_3BDone); tb_opp_0 = SUM(HudCache.street0_3BChance)
- **Tooltip**: % resteal
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Status**: estimate
- **Note**: An estimate built from the 3-bet counts with fixed 0.7 and 0.6 factors (the share assumed to be from the blinds); it is not a count of re-steals. Use `raiseToSteal` for the measured value.

### Successful Steal — `s_steal`

- **HUD abbreviation**: `s_st`
- **Description**: Percentage of steal attempts that won the blinds without a fight (the blinds folded).
- **Formula**: Number of steal attempts that won the blinds uncontested / Number of steal attempts (first raise from the cutoff, button or small blind into an unopened pot) × 100
- **Formula (code)**: `suc_st / steal × 100`
- **SQL database field / logic**: steal = SUM(HudCache.stealDone); suc_st = SUM(HudCache.success_Steal)
- **Tooltip**: % steal success
- **Detailed HUD text**: `s_steal`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Attempt to Steal Blinds — `steal`

- **HUD abbreviation**: `st`
- **Description**: Percentage of the time that a player raised first in from the cutoff, button or small blind when the pot was unopened.
- **Formula**: Number of steal attempts (first raise from the cutoff, button or small blind into an unopened pot) / Number of times the player was in the cutoff, button or small blind with the pot unopened × 100
- **Formula (code)**: `steal / steal_opp × 100`
- **SQL database field / logic**: steal_opp = SUM(HudCache.stealChance); steal = SUM(HudCache.stealDone)
- **Tooltip**: % steal attempted
- **Detailed HUD text**: `steal`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **PT4 equivalent**: Att To Steal — `(stealDone / stealChance) * 100` (same formula)
- **XML titles**: `Steals`

### 3-Bet vs Steal (deprecated) — `three_bet_vs_steal`

- **HUD abbreviation**: `3bvs`
- **Description**: Shows no data: it needs information about the other players that the cache cannot aggregate.
- **Formula (code)**: `no data (deprecated)`
- **SQL database field / logic**: none: needs data about other players that HudCache cannot aggregate
- **Tooltip**: % 3bet vs steal (deprecated)
- **Games**: none (shows no data)
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: deprecated

## Flop / 4th street

### Flop Aggression Frequency — `a_freq1`

- **HUD abbreviation**: `a1`
- **Description**: Percentage of the time that a player bet or raised at least once on the flop, given that they saw it.
- **Formula**: Number of hands where the player bet or raised on the flop / Number of hands where the player saw the flop × 100
- **Formula (code)**: `aggr_1 / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); aggr_1 = SUM(HudCache.street1Aggr)
- **Tooltip**: Aggression frequency flop/4th street
- **Detailed HUD text**: `a_fq_1`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 equivalent**: Flop AFq — `((street1Bets + street1Raises) / (street1Calls + flg_f_fold + street1Bets + street1Raises)) * 100` (different formula)
- **PT4 difference**: PT4: flop bets and raises / (flop calls + folds + bets + raises), over actions. FPDB: flops on which the player bet or raised at least once / flops seen, over hands.
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `FlAFq`

### Average Bet Size Flop (deprecated) — `avg_bet_size_flop`

- **HUD abbreviation**: `avg_bet_f`
- **Description**: Shows no data. Use Average Flop Bet Made (`f_bet_made`).
- **Formula (code)**: `no data (deprecated); see `f_bet_made``
- **SQL database field / logic**: none
- **Tooltip**: avg bet size flop (deprecated)
- **Games**: none (shows no data)
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: deprecated

### Flop Bet Frequency — `bet_frequency_flop`

- **HUD abbreviation**: `bet_f`
- **Description**: Meant as bets per flop seen. Reads keys the HUD queries do not select, so the value is not reliable.
- **Formula**: Number of flop bets (key not selected by the HUD queries, which name it bet_1) / Number of hands where the player saw the flop × 100
- **Formula (code)**: `street1Bets / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); street1Bets (not selected by the HUD queries)
- **Tooltip**: % bet frequency flop
- **Detailed HUD text**: `bet_freq_flop`
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### Call vs Flop 3-Bet — `call_vs_flop_3bet`

- **HUD abbreviation**: `CvF3B`
- **Description**: Percentage of the time that a player called when facing a 3-bet on the flop.
- **Formula**: Number of times the player called a 3-bet on the flop / Number of times the player faced a 3-bet on the flop × 100
- **Formula (code)**: `cnt_f_call_3bet / cnt_f_face_3bet × 100`
- **SQL database field / logic**: cnt_f_face_3bet = SUM(HudCache.cnt_f_face_3bet); cnt_f_call_3bet = SUM(HudCache.cnt_f_call_3bet)
- **Tooltip**: % calling facing a flop 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs Flop 4-Bet — `call_vs_flop_4bet`

- **HUD abbreviation**: `CvF4B`
- **Description**: Percentage of the time that a player called when facing a 4-bet on the flop.
- **Formula**: Number of times the player called a 4-bet on the flop / Number of times the player faced a 4-bet on the flop × 100
- **Formula (code)**: `cnt_f_call_4bet / cnt_f_face_4bet × 100`
- **SQL database field / logic**: cnt_f_face_4bet = SUM(HudCache.cnt_f_face_4bet); cnt_f_call_4bet = SUM(HudCache.cnt_f_call_4bet)
- **Tooltip**: % calling facing a flop 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs Flop C-Bet — `call_vs_flop_cbet`

- **HUD abbreviation**: `CvFCB`
- **Description**: Percentage of the time that a player called when facing a continuation bet on the flop.
- **Formula**: Number of times the player called a continuation bet on the flop / Number of times the player faced a continuation bet on the flop × 100
- **Formula (code)**: `cnt_f_call_cbet / cnt_f_face_cbet × 100`
- **SQL database field / logic**: cnt_f_face_cbet = SUM(HudCache.cnt_f_face_cbet); cnt_f_call_cbet = SUM(HudCache.cnt_f_call_cbet)
- **Tooltip**: % calling facing a flop c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Call vs Flop Donk Bet — `call_vs_flop_donk`

- **HUD abbreviation**: `CvFDk`
- **Description**: Percentage of the time that a player called when facing a donk bet (a bet into the preflop raiser) on the flop.
- **Formula**: Number of times the player called a donk bet (a bet into the preflop raiser) on the flop / Number of times the player faced a donk bet (a bet into the preflop raiser) on the flop × 100
- **Formula (code)**: `cnt_f_call_donk / cnt_f_face_donk × 100`
- **SQL database field / logic**: cnt_f_face_donk = SUM(HudCache.cnt_f_face_donk); cnt_f_call_donk = SUM(HudCache.cnt_f_call_donk)
- **Tooltip**: % calling facing a flop donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Flop Continuation Bet — `cb1`

- **HUD abbreviation**: `cb1`
- **Description**: Percentage of the time that the last preflop raiser bet (or raised) on the flop when they had the chance.
- **Formula**: Number of continuation bets on the flop (the last preflop raiser bet or raised on the street) / Number of flop continuation-bet opportunities (the last preflop raiser, not folded yet) × 100
- **Formula (code)**: `cb_1 / cb_opp_1 × 100`
- **SQL database field / logic**: cb_opp_1 = SUM(HudCache.street1CBChance); cb_1 = SUM(HudCache.street1CBDone)
- **Tooltip**: % continuation bet flop/4th street
- **Detailed HUD text**: `cb_1`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 equivalent**: CBet Flop — `(street1CBDone / street1CBChance) * 100` (same formula)
- **PT4 derivation tests**: `test_player_situations.py`

### Flop C-Bet In Position (not split) — `cb_ip`

- **HUD abbreviation**: `cb_ip`
- **Description**: Meant as the flop continuation-bet rate in position. The cache has no c-bet counts by position, so the stat scales both counts by the share of flops played in position; the share cancels and the value is the overall flop c-bet (`cb1`).
- **Formula**: (Number of flop continuation bets × r) / (Number of flop continuation-bet opportunities × r) × 100, r = share of flops in position (cancels)
- **Formula (code)**: `(cb_1 × r) / (cb_opp_1 × r) × 100 with r = street1InPosition / saw_f; r cancels, so = cb_1 / cb_opp_1 × 100`
- **SQL database field / logic**: cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); saw_f = SUM(HudCache.street1Seen); street1InPosition = SUM(HudCache.street1InPosition)
- **Tooltip**: % c-bet in position
- **Detailed HUD text**: `cbet_in_position`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_player_situations.py`, `test_pt4_adapter.py`
- **Status**: estimate
- **Note**: Not split by position: both counts are scaled by the same in-position share of flops seen, which cancels out, so the value always equals `cb1`. HudCache has no c-bet count by position.

### Flop C-Bet Out of Position (not split) — `cb_oop`

- **HUD abbreviation**: `cb_oop`
- **Description**: Meant as the flop continuation-bet rate out of position. The cache has no c-bet counts by position, so the stat scales both counts by the share of flops played out of position; the share cancels and the value is the overall flop c-bet (`cb1`).
- **Formula**: (Number of flop continuation bets × r) / (Number of flop continuation-bet opportunities × r) × 100, r = share of flops out of position (cancels)
- **Formula (code)**: `(cb_1 × r) / (cb_opp_1 × r) × 100 with r = (saw_f − street1InPosition) / saw_f; r cancels, so = cb_1 / cb_opp_1 × 100`
- **SQL database field / logic**: cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); saw_f = SUM(HudCache.street1Seen); street1InPosition = SUM(HudCache.street1InPosition)
- **Tooltip**: % c-bet out of position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_player_situations.py`, `test_pt4_adapter.py`
- **Status**: estimate
- **Note**: Not split by position: both counts are scaled by the same out-of-position share of flops seen, which cancels out, so the value always equals `cb1`. HudCache has no c-bet count by position.

### Continuation bet on the flop. — `cbet_flop`

- **HUD abbreviation**: `C-bet Flop`
- **Description**: Continuation bet on the flop.
- **Formula (code)**: `100 * street1CBDone / street1CBChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street1CBDone, street1CBChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Flop Check-Raise — `cr1`

- **HUD abbreviation**: `cr1`
- **Description**: Percentage of the time that a player check-raised the flop, given that they checked and acted again on it.
- **Formula**: Number of check-raises on the flop / Number of times the player checked on the flop and acted again on that street × 100
- **Formula (code)**: `cr_1 / ccr_opp_1 × 100`
- **SQL database field / logic**: ccr_opp_1 = SUM(HudCache.street1CheckCallRaiseChance); cr_1 = SUM(HudCache.street1CheckRaiseDone)
- **Tooltip**: % check-raise flop/4th street
- **Detailed HUD text**: `cr_1`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Flop Bet/Raise when not the C-Bettor — `dbr1`

- **HUD abbreviation**: `dbr1`
- **Description**: Percentage of the flops a player saw outside a continuation-bet spot on which they bet or raised: aggression that is not a c-bet (donk bets and raises).
- **Formula**: (Number of hands where the player bet or raised on the flop minus Number of continuation bets on the flop (the last preflop raiser bet or raised on the street)) / (Number of hands where the player saw the flop minus Number of flop continuation-bet opportunities (the last preflop raiser, not folded yet)) × 100
- **Formula (code)**: `(aggr_1 − cb_1) / (saw_f − cb_opp_1) × 100`
- **SQL database field / logic**: aggr_1 = SUM(HudCache.street1Aggr); cb_1 = SUM(HudCache.street1CBDone); saw_f = SUM(HudCache.street1Seen); cb_opp_1 = SUM(HudCache.street1CBChance)
- **Tooltip**: % DonkBetAndRaise flop/4th street
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_player_situations.py`, `test_pt4_adapter.py`

### Price of Flop Raise Faced — `f_2bet_facing`

- **HUD abbreviation**: `F2vs`
- **Description**: The average price the player was offered when facing a flop raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the flop raises faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of flop raises faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(f_2bet_facing_bp / f_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_2bet_facing_cnt = SUM(HudCache.cnt_f_2bet_facing); f_2bet_facing_bp = SUM(HudCache.val_f_2bet_facing_bp)
- **Tooltip**: avg flop 2bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`, `test_calc_postflop_raise_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Flop 3-Bet Faced — `f_3bet_facing`

- **HUD abbreviation**: `F3vs`
- **Description**: The average price the player was offered when facing a flop 3-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the flop 3-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of flop 3-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(f_3bet_facing_bp / f_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_3bet_facing_cnt = SUM(HudCache.cnt_f_3bet_facing); f_3bet_facing_bp = SUM(HudCache.val_f_3bet_facing_bp)
- **Tooltip**: avg flop 3bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_postflop_raise_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Flop 4-Bet Faced — `f_4bet_facing`

- **HUD abbreviation**: `F4vs`
- **Description**: The average price the player was offered when facing a flop 4-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the flop 4-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of flop 4-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(f_4bet_facing_bp / f_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_4bet_facing_cnt = SUM(HudCache.cnt_f_4bet_facing); f_4bet_facing_bp = SUM(HudCache.val_f_4bet_facing_bp)
- **Tooltip**: avg flop 4bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Flop Bet Faced — `f_bet_facing`

- **HUD abbreviation**: `FBvs`
- **Description**: The average price the player was offered when facing a flop bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the flop bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of flop bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(f_bet_facing_bp / f_bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_bet_facing_cnt = SUM(HudCache.cnt_f_bet_facing); f_bet_facing_bp = SUM(HudCache.val_f_bet_facing_bp)
- **Tooltip**: avg flop bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_flop_bet_facing.py`, `test_calc_postflop_raise_facing.py`, `test_calc_turn_river_bet_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Flop Bet Size — `f_bet_made`

- **HUD abbreviation**: `FBet`
- **Description**: The average size of the player's first flop bet, as a percentage of the pot before the bet.
- **Formula**: Sum of sizes of those bets: bet / pot before the bet, in basis points / Number of first bets made on the flop / 10 000 × 100
- **Formula (code)**: `(f_bet_made_bp / f_bet_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_bet_made_cnt = SUM(HudCache.cnt_f_bet_made); f_bet_made_bp = SUM(HudCache.val_f_bet_made_bp)
- **Tooltip**: avg flop bet made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_made.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Fold to Flop Continuation Bet — `f_cb1`

- **HUD abbreviation**: `f_cb1`
- **Description**: Percentage of the time that a player folded when facing a flop continuation bet.
- **Formula**: Number of folds to a flop continuation bet / Number of times the player acted after a flop continuation bet × 100
- **Formula (code)**: `f_cb_1 / f_cb_opp_1 × 100`
- **SQL database field / logic**: f_cb_opp_1 = SUM(HudCache.foldToStreet1CBChance); f_cb_1 = SUM(HudCache.foldToStreet1CBDone)
- **Tooltip**: % fold to continuation bet flop/4th street
- **Detailed HUD text**: `f_cb_1`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 equivalent**: Fold to F CBet — `(foldToStreet1CBDone / foldToStreet1CBChance) * 100` (same formula)
- **Note**: Gives the same value as `fold_to_cbet_flop` (same counters, same formula). The HUD abbreviation `f_cb1` is shared with: `fold_to_cbet_flop`.

### Fold to Flop Bet/Raise (not a C-Bet) — `f_dbr1`

- **HUD abbreviation**: `f_dbr1`
- **Description**: Percentage of the time that a player folded on the flop to a bet or raise that was not a continuation bet.
- **Formula**: (Number of times the player folded on the flop after someone else bet or raised minus Number of folds to a flop continuation bet) / (Number of times the player acted on the flop after someone else bet or raised minus Number of times the player acted after a flop continuation bet) × 100
- **Formula (code)**: `(f_freq_1 − f_cb_1) / (was_raised_1 − f_cb_opp_1) × 100`
- **SQL database field / logic**: f_freq_1 = SUM(HudCache.foldToOtherRaisedStreet1); f_cb_1 = SUM(HudCache.foldToStreet1CBDone); was_raised_1 = SUM(HudCache.otherRaisedStreet1); f_cb_opp_1 = SUM(HudCache.foldToStreet1CBChance)
- **Tooltip**: % Fold to DonkBetAndRaise flop/4th street
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw

### Price of Flop Raise Faced — `f_raise_facing`

- **HUD abbreviation**: `FRvs`
- **Description**: The average price the player was offered when facing a flop raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot. When several raises are faced on the street, the last one counts.
- **Formula**: Sum of prices of the flop raises (most recent level) faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of flop raises (most recent level) faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(f_raise_facing_bp / f_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_raise_facing_cnt = SUM(HudCache.cnt_f_raise_facing); f_raise_facing_bp = SUM(HudCache.val_f_raise_facing_bp)
- **Tooltip**: avg flop raise faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Flop Raise Size — `f_raise_made`

- **HUD abbreviation**: `FRz`
- **Description**: The average size of the player's first flop raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those raises: raise-to amount / pot before the raise, in basis points / Number of first raises made on the flop / 10 000 × 100
- **Formula (code)**: `(f_raise_made_bp / f_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_raise_made_cnt = SUM(HudCache.cnt_f_raise_made); f_raise_made_bp = SUM(HudCache.val_f_raise_made_bp)
- **Tooltip**: avg flop raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_raise_made.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Flop Raise Size (2nd raise) — `f_raise_made_2`

- **HUD abbreviation**: `FRz2`
- **Description**: The average size of the player's second flop raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those second raises: raise-to amount / pot before the raise, in basis points / Number of second raises made by the player on the flop / 10 000 × 100
- **Formula (code)**: `(f_raise_made_2_bp / f_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: f_raise_made_2_cnt = SUM(HudCache.cnt_f_raise_made_2); f_raise_made_2_bp = SUM(HudCache.val_f_raise_made_2_bp)
- **Tooltip**: avg 2nd flop raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Flop Stack-to-Pot Ratio — `f_spr`

- **HUD abbreviation**: `fSPR`
- **Description**: The average stack-to-pot ratio entering the flop: the effective stack (smallest of the player's and the deepest active opponent's) divided by the pot.
- **Formula**: Sum of stack-to-pot ratios entering the flop (effective stack / pot), stored ×100 / Number of flops with a recorded stack-to-pot ratio × 0.01
- **Formula (code)**: `0.01 × f_spr_val / f_spr_cnt`
- **SQL database field / logic**: f_spr_cnt = SUM(HudCache.cnt_f_spr); f_spr_val = SUM(HudCache.val_f_spr)
- **Tooltip**: avg flop SPR
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Faced a Raise on the Flop — `face_raise_flop`

- **HUD abbreviation**: `FvRf`
- **Description**: Percentage of the flops a player saw on which they acted after a raise.
- **Formula**: Number of flops where the player acted after a raise / Number of hands where the player saw the flop × 100
- **Formula (code)**: `f_face_raise / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); f_face_raise = SUM(HudCache.street1FaceRaise)
- **Tooltip**: % face raise flop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### Flop Fold to Bet or Raise — `ffreq1`

- **HUD abbreviation**: `ff1`
- **Description**: Percentage of the time that a player folded on the flop after someone else bet or raised there.
- **Formula**: Number of times the player folded on the flop after someone else bet or raised / Number of times the player acted on the flop after someone else bet or raised × 100
- **Formula (code)**: `f_freq_1 / was_raised_1 × 100`
- **SQL database field / logic**: was_raised_1 = SUM(HudCache.otherRaisedStreet1); f_freq_1 = SUM(HudCache.foldToOtherRaisedStreet1)
- **Tooltip**: % fold frequency flop/4th street
- **Detailed HUD text**: `ff_1`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw

### Flop First Raise — `first_raise_flop`

- **HUD abbreviation**: `1Rf`
- **Description**: Percentage of the flops a player saw on which they made the first raise.
- **Formula**: Number of times the player made the first raise on the flop / Number of hands where the player saw the flop × 100
- **Formula (code)**: `f_first_raise / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); f_first_raise = SUM(HudCache.street1FirstRaise)
- **Tooltip**: % first raise flop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### Flop Fold — `fold_flop`

- **HUD abbreviation**: `Fldf`
- **Description**: Percentage of the flops a player saw that they folded.
- **Formula**: Number of flops the player folded / Number of hands where the player saw the flop × 100
- **Formula (code)**: `f_fold / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); f_fold = SUM(HudCache.flg_f_fold)
- **Tooltip**: % fold flop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### Fold to Flop Continuation Bet — `fold_to_cbet_flop`

- **HUD abbreviation**: `f_cb1`
- **Description**: Percentage of the time that a player folded when facing a flop continuation bet.
- **Formula**: Number of folds to a flop continuation bet / Number of times the player acted after a flop continuation bet × 100
- **Formula (code)**: `f_cb_1 / f_cb_opp_1 × 100`
- **SQL database field / logic**: f_cb_opp_1 = SUM(HudCache.foldToStreet1CBChance); f_cb_1 = SUM(HudCache.foldToStreet1CBDone)
- **Tooltip**: % fold to continuation bet flop/4th street
- **Detailed HUD text**: `f_cb_1`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **Note**: Alias: this stat calls `f_cb1` and returns its value unchanged. The HUD abbreviation `f_cb1` is shared with: `f_cb1`.

### How often the player folded when facing a continuation bet on the flop. — `fold_to_cbet_flop`

- **HUD abbreviation**: `Fold to flop c-bet`
- **Description**: How often the player folded when facing a continuation bet on the flop.
- **Formula (code)**: `decisions matching the numerator {'response': 'fold'} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'flop', 'situation': 'facing_cbet'}
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Analytics definition (metric fold_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### How often the player folded to a flop c-bet, split by the size faced. — `fold_to_cbet_flop_by_size`

- **HUD abbreviation**: `Fold to flop c-bet by bet size`
- **Description**: How often the player folded to a flop c-bet, split by the size faced.
- **Formula (code)**: `decisions matching the numerator {'response': 'fold'} / decisions matching the filters × 100`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'street': 'flop', 'situation': 'facing_cbet'}; grouped by facing_sizing_bucket
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Analytics definition (metric fold_frequency): a HUD cell shows it only with the data_* attributes the editor writes.

### Fold to Flop 3-Bet — `fold_to_three_B_flop`

- **HUD abbreviation**: `FF3B`
- **Description**: Percentage of the time that a player who raised the flop folded to a 3-bet.
- **Formula**: Number of times the player folded to a flop 3-bet after raising / Number of times the player raised the flop and faced a 3-bet × 100
- **Formula (code)**: `ff3b / ff3b_opp × 100`
- **SQL database field / logic**: ff3b_opp = SUM(HudCache.street1_FoldTo3BChance); ff3b = SUM(HudCache.street1_FoldTo3BDone)
- **Tooltip**: % fold to flop 3bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_3bet_postflop.py`

### Fold vs Flop 3-Bet — `fold_vs_flop_3bet`

- **HUD abbreviation**: `FvF3B`
- **Description**: Percentage of the time that a player folded when facing a 3-bet on the flop. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 3-bet on the flop minus Number of times the player called a 3-bet on the flop minus Number of times the player raised a 3-bet on the flop) / Number of times the player faced a 3-bet on the flop × 100
- **Formula (code)**: `(cnt_f_face_3bet − cnt_f_call_3bet − cnt_f_raise_3bet) / cnt_f_face_3bet × 100`
- **SQL database field / logic**: cnt_f_face_3bet = SUM(HudCache.cnt_f_face_3bet); cnt_f_call_3bet = SUM(HudCache.cnt_f_call_3bet); cnt_f_raise_3bet = SUM(HudCache.cnt_f_raise_3bet)
- **Tooltip**: % folding facing a flop 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Flop 4-Bet — `fold_vs_flop_4bet`

- **HUD abbreviation**: `FvF4B`
- **Description**: Percentage of the time that a player folded when facing a 4-bet on the flop. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 4-bet on the flop minus Number of times the player called a 4-bet on the flop minus Number of times the player raised a 4-bet on the flop) / Number of times the player faced a 4-bet on the flop × 100
- **Formula (code)**: `(cnt_f_face_4bet − cnt_f_call_4bet − cnt_f_raise_4bet) / cnt_f_face_4bet × 100`
- **SQL database field / logic**: cnt_f_face_4bet = SUM(HudCache.cnt_f_face_4bet); cnt_f_call_4bet = SUM(HudCache.cnt_f_call_4bet); cnt_f_raise_4bet = SUM(HudCache.cnt_f_raise_4bet)
- **Tooltip**: % folding facing a flop 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Flop C-Bet — `fold_vs_flop_cbet`

- **HUD abbreviation**: `FvFCB`
- **Description**: Percentage of the time that a player folded when facing a continuation bet on the flop. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a continuation bet on the flop minus Number of times the player called a continuation bet on the flop minus Number of times the player raised a continuation bet on the flop) / Number of times the player faced a continuation bet on the flop × 100
- **Formula (code)**: `(cnt_f_face_cbet − cnt_f_call_cbet − cnt_f_raise_cbet) / cnt_f_face_cbet × 100`
- **SQL database field / logic**: cnt_f_face_cbet = SUM(HudCache.cnt_f_face_cbet); cnt_f_call_cbet = SUM(HudCache.cnt_f_call_cbet); cnt_f_raise_cbet = SUM(HudCache.cnt_f_raise_cbet)
- **Tooltip**: % folding facing a flop c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Flop Donk Bet — `fold_vs_flop_donk`

- **HUD abbreviation**: `FvFDk`
- **Description**: Percentage of the time that a player folded when facing a donk bet (a bet into the preflop raiser) on the flop. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a donk bet (a bet into the preflop raiser) on the flop minus Number of times the player called a donk bet (a bet into the preflop raiser) on the flop minus Number of times the player raised a donk bet (a bet into the preflop raiser) on the flop) / Number of times the player faced a donk bet (a bet into the preflop raiser) on the flop × 100
- **Formula (code)**: `(cnt_f_face_donk − cnt_f_call_donk − cnt_f_raise_donk) / cnt_f_face_donk × 100`
- **SQL database field / logic**: cnt_f_face_donk = SUM(HudCache.cnt_f_face_donk); cnt_f_call_donk = SUM(HudCache.cnt_f_call_donk); cnt_f_raise_donk = SUM(HudCache.cnt_f_raise_donk)
- **Tooltip**: % folding facing a flop donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Flop 4-Bet — `four_B_flop`

- **HUD abbreviation**: `F4B`
- **Description**: Percentage of the time that a player re-raised when facing a 3-bet on the flop.
- **Formula**: Number of flop 4-bets / Number of times the player faced a flop 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `fl4b / fl4b_opp × 100`
- **SQL database field / logic**: fl4b_opp = SUM(HudCache.street1_4BChance); fl4b = SUM(HudCache.street1_4BDone)
- **Tooltip**: % 4 bet flop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **Note**: The HUD abbreviation `F4B` is shared with: `f_4bet`.

### Flop Open (first bet) — `open_flop`

- **HUD abbreviation**: `OPf`
- **Description**: Percentage of the time that a player made the first bet on the flop when nobody had bet before them.
- **Formula**: Number of times the player made the first bet on the flop / Number of times the player acted on the flop before anyone had bet × 100
- **Formula (code)**: `flopen / flopen_opp × 100`
- **SQL database field / logic**: flopen_opp = SUM(HudCache.street1OpenChance); flopen = SUM(HudCache.street1OpenDone)
- **Tooltip**: % open flop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw

### Flop Probe Bet — `probe_bet`

- **HUD abbreviation**: `probe`
- **Description**: Meant as the percentage of flops seen without having c-bet on which the player bet. Reads `street1Bets`, which the HUD queries do not select, so the value is not reliable.
- **Formula**: min(flop bets, flops seen − flop c-bets) / (Number of flops seen − Number of flop c-bets) × 100
- **Formula (code)**: `min(street1Bets, saw_f − cb_1) / (saw_f − cb_1) × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); cb_1 = SUM(HudCache.street1CBDone); street1Bets = SUM(HudCache.street1Bets)
- **Tooltip**: % probe bet flop
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **PT4 derivation tests**: `test_player_situations.py`, `test_pt4_adapter.py`
- **Status**: input-missing
- **Note**: Flop probe: bets over the flops seen where the player did not c-bet. Reads `street1Bets`, which the HUD queries expose as `bet_1`.

### Flop Raise Frequency — `raise_frequency_flop`

- **HUD abbreviation**: `raise_f`
- **Description**: Meant as raises per flop seen. Reads keys the HUD queries do not select, so the value is not reliable.
- **Formula**: Number of flop raises (key not selected by the HUD queries, which name it raise_1) / Number of hands where the player saw the flop × 100
- **Formula (code)**: `street1Raises / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); street1Raises (not selected by the HUD queries)
- **Tooltip**: % raise frequency flop
- **Detailed HUD text**: `raise_freq_flop`
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### Raise vs Flop 3-Bet — `raise_vs_flop_3bet`

- **HUD abbreviation**: `RvF3B`
- **Description**: Percentage of the time that a player raised when facing a 3-bet on the flop.
- **Formula**: Number of times the player raised a 3-bet on the flop / Number of times the player faced a 3-bet on the flop × 100
- **Formula (code)**: `cnt_f_raise_3bet / cnt_f_face_3bet × 100`
- **SQL database field / logic**: cnt_f_face_3bet = SUM(HudCache.cnt_f_face_3bet); cnt_f_raise_3bet = SUM(HudCache.cnt_f_raise_3bet)
- **Tooltip**: % raising facing a flop 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs Flop 4-Bet — `raise_vs_flop_4bet`

- **HUD abbreviation**: `RvF4B`
- **Description**: Percentage of the time that a player raised when facing a 4-bet on the flop.
- **Formula**: Number of times the player raised a 4-bet on the flop / Number of times the player faced a 4-bet on the flop × 100
- **Formula (code)**: `cnt_f_raise_4bet / cnt_f_face_4bet × 100`
- **SQL database field / logic**: cnt_f_face_4bet = SUM(HudCache.cnt_f_face_4bet); cnt_f_raise_4bet = SUM(HudCache.cnt_f_raise_4bet)
- **Tooltip**: % raising facing a flop 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs Flop C-Bet — `raise_vs_flop_cbet`

- **HUD abbreviation**: `RvFCB`
- **Description**: Percentage of the time that a player raised when facing a continuation bet on the flop.
- **Formula**: Number of times the player raised a continuation bet on the flop / Number of times the player faced a continuation bet on the flop × 100
- **Formula (code)**: `cnt_f_raise_cbet / cnt_f_face_cbet × 100`
- **SQL database field / logic**: cnt_f_face_cbet = SUM(HudCache.cnt_f_face_cbet); cnt_f_raise_cbet = SUM(HudCache.cnt_f_raise_cbet)
- **Tooltip**: % raising facing a flop c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Raise vs Flop Donk Bet — `raise_vs_flop_donk`

- **HUD abbreviation**: `RvFDk`
- **Description**: Percentage of the time that a player raised when facing a donk bet (a bet into the preflop raiser) on the flop.
- **Formula**: Number of times the player raised a donk bet (a bet into the preflop raiser) on the flop / Number of times the player faced a donk bet (a bet into the preflop raiser) on the flop × 100
- **Formula (code)**: `cnt_f_raise_donk / cnt_f_face_donk × 100`
- **SQL database field / logic**: cnt_f_face_donk = SUM(HudCache.cnt_f_face_donk); cnt_f_raise_donk = SUM(HudCache.cnt_f_raise_donk)
- **Tooltip**: % raising facing a flop donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Flop 3-Bet — `three_B_flop`

- **HUD abbreviation**: `F3B`
- **Description**: Percentage of the time that a player re-raised when facing a bet and a raise on the flop.
- **Formula**: Number of flop 3-bets (re-raise of a bet and a raise) / Number of times the player faced a bet and a raise on the flop × 100
- **Formula (code)**: `fl3b / fl3b_opp × 100`
- **SQL database field / logic**: fl3b_opp = SUM(HudCache.street1_3BChance); fl3b = SUM(HudCache.street1_3BDone)
- **Tooltip**: % 3 bet flop
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_calc_3bet_postflop.py`
- **Note**: The HUD abbreviation `F3B` is shared with: `f_3bet`.

## Turn / 5th street

### Turn Aggression Frequency — `a_freq2`

- **HUD abbreviation**: `a2`
- **Description**: Percentage of the time that a player bet or raised at least once on the turn, given that they saw it.
- **Formula**: Number of hands where the player bet or raised on the turn / Number of hands where the player saw the turn × 100
- **Formula (code)**: `aggr_2 / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); aggr_2 = SUM(HudCache.street2Aggr)
- **Tooltip**: Aggression frequency turn/5th street
- **Detailed HUD text**: `a_fq_2`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)
- **XML titles**: `TuAFq`

### Average Bet Size Turn (deprecated) — `avg_bet_size_turn`

- **HUD abbreviation**: `avg_bet_t`
- **Description**: Shows no data. Use Average Turn Bet Made (`t_bet_made`).
- **Formula (code)**: `no data (deprecated); see `t_bet_made``
- **SQL database field / logic**: none
- **Tooltip**: avg bet size turn (deprecated)
- **Games**: none (shows no data)
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: deprecated

### Turn Bet Frequency — `bet_frequency_turn`

- **HUD abbreviation**: `bet_t`
- **Description**: Meant as bets per turn seen. Reads keys the HUD queries do not select, so the value is not reliable.
- **Formula**: Number of turn bets (key not selected by the HUD queries, which name it bet_2) / Number of hands where the player saw the turn (key not selected by the HUD queries) × 100
- **Formula (code)**: `street2Bets / saw_t × 100`
- **SQL database field / logic**: saw_t (not selected by the HUD queries); street2Bets (not selected by the HUD queries)
- **Tooltip**: % bet frequency turn
- **Detailed HUD text**: `bet_freq_turn`
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### Call vs Turn Barrel after Float — `call_float_turn`

- **HUD abbreviation**: `CvTFl`
- **Description**: Percentage of the time that a player who called the flop c-bet in position called when the aggressor bet the turn again.
- **Formula**: Number of times the player called a bet after having called the previous street's bet in position (a float spot) on the turn / Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the turn × 100
- **Formula (code)**: `cnt_t_call_float / cnt_t_face_float × 100`
- **SQL database field / logic**: cnt_t_face_float = SUM(HudCache.cnt_t_face_float); cnt_t_call_float = SUM(HudCache.cnt_t_call_float)
- **Tooltip**: % calling facing the turn barrel, having called the flop c-bet in position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Call vs Turn 3-Bet — `call_vs_turn_3bet`

- **HUD abbreviation**: `CvT3B`
- **Description**: Percentage of the time that a player called when facing a 3-bet on the turn.
- **Formula**: Number of times the player called a 3-bet on the turn / Number of times the player faced a 3-bet on the turn × 100
- **Formula (code)**: `cnt_t_call_3bet / cnt_t_face_3bet × 100`
- **SQL database field / logic**: cnt_t_face_3bet = SUM(HudCache.cnt_t_face_3bet); cnt_t_call_3bet = SUM(HudCache.cnt_t_call_3bet)
- **Tooltip**: % calling facing a turn 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs Turn 4-Bet — `call_vs_turn_4bet`

- **HUD abbreviation**: `CvT4B`
- **Description**: Percentage of the time that a player called when facing a 4-bet on the turn.
- **Formula**: Number of times the player called a 4-bet on the turn / Number of times the player faced a 4-bet on the turn × 100
- **Formula (code)**: `cnt_t_call_4bet / cnt_t_face_4bet × 100`
- **SQL database field / logic**: cnt_t_face_4bet = SUM(HudCache.cnt_t_face_4bet); cnt_t_call_4bet = SUM(HudCache.cnt_t_call_4bet)
- **Tooltip**: % calling facing a turn 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs Turn C-Bet — `call_vs_turn_cbet`

- **HUD abbreviation**: `CvTCB`
- **Description**: Percentage of the time that a player called when facing a continuation bet on the turn.
- **Formula**: Number of times the player called a continuation bet on the turn / Number of times the player faced a continuation bet on the turn × 100
- **Formula (code)**: `cnt_t_call_cbet / cnt_t_face_cbet × 100`
- **SQL database field / logic**: cnt_t_face_cbet = SUM(HudCache.cnt_t_face_cbet); cnt_t_call_cbet = SUM(HudCache.cnt_t_call_cbet)
- **Tooltip**: % calling facing a turn c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs Turn Donk Bet — `call_vs_turn_donk`

- **HUD abbreviation**: `CvTDk`
- **Description**: Percentage of the time that a player called when facing a donk bet (a bet into the preflop raiser) on the turn.
- **Formula**: Number of times the player called a donk bet (a bet into the preflop raiser) on the turn / Number of times the player faced a donk bet (a bet into the preflop raiser) on the turn × 100
- **Formula (code)**: `cnt_t_call_donk / cnt_t_face_donk × 100`
- **SQL database field / logic**: cnt_t_face_donk = SUM(HudCache.cnt_t_face_donk); cnt_t_call_donk = SUM(HudCache.cnt_t_call_donk)
- **Tooltip**: % calling facing a turn donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Turn Continuation Bet — `cb2`

- **HUD abbreviation**: `cb2`
- **Description**: Percentage of the time that the last preflop raiser bet (or raised) on the turn when they had the chance.
- **Formula**: Number of continuation bets on the turn (the last preflop raiser bet or raised on the street) / Number of turn continuation-bet opportunities (the last preflop raiser, not folded yet) × 100
- **Formula (code)**: `cb_2 / cb_opp_2 × 100`
- **SQL database field / logic**: cb_opp_2 = SUM(HudCache.street2CBChance); cb_2 = SUM(HudCache.street2CBDone)
- **Tooltip**: % continuation bet turn/5th street
- **Detailed HUD text**: `cb_2`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Continuation bet on the turn. — `cbet_turn`

- **HUD abbreviation**: `C-bet Turn`
- **Description**: Continuation bet on the turn.
- **Formula (code)**: `100 * street2CBDone / street2CBChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street2CBDone, street2CBChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Turn Check-Raise — `cr2`

- **HUD abbreviation**: `cr2`
- **Description**: Percentage of the time that a player check-raised the turn, given that they checked and acted again on it.
- **Formula**: Number of check-raises on the turn / Number of times the player checked on the turn and acted again on that street × 100
- **Formula (code)**: `cr_2 / ccr_opp_2 × 100`
- **SQL database field / logic**: ccr_opp_2 = SUM(HudCache.street2CheckCallRaiseChance); cr_2 = SUM(HudCache.street2CheckRaiseDone)
- **Tooltip**: % check-raise turn/5th street
- **Detailed HUD text**: `cr_2`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Turn Bet/Raise when not the C-Bettor — `dbr2`

- **HUD abbreviation**: `dbr2`
- **Description**: Percentage of the turns a player saw outside a continuation-bet spot on which they bet or raised: aggression that is not a c-bet (donk bets and raises).
- **Formula**: (Number of hands where the player bet or raised on the turn minus Number of continuation bets on the turn (the last preflop raiser bet or raised on the street)) / (Number of hands where the player saw the turn minus Number of turn continuation-bet opportunities (the last preflop raiser, not folded yet)) × 100
- **Formula (code)**: `(aggr_2 − cb_2) / (saw_2 − cb_opp_2) × 100`
- **SQL database field / logic**: aggr_2 = SUM(HudCache.street2Aggr); cb_2 = SUM(HudCache.street2CBDone); saw_2 = SUM(HudCache.street2Seen); cb_opp_2 = SUM(HudCache.street2CBChance)
- **Tooltip**: % DonkBetAndRaise turn/5th street
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Bet the turn after checking the flop as the preflop aggressor. — `delayed_cbet_turn`

- **HUD abbreviation**: `Delayed C-bet Turn`
- **Description**: Bet the turn after checking the flop as the preflop aggressor.
- **Formula (code)**: `100 * street2DelayedCBDone / street2DelayedCBChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street2DelayedCBDone, street2DelayedCBChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Fold to Turn Continuation Bet — `f_cb2`

- **HUD abbreviation**: `f_cb2`
- **Description**: Percentage of the time that a player folded when facing a turn continuation bet.
- **Formula**: Number of folds to a turn continuation bet / Number of times the player acted after a turn continuation bet × 100
- **Formula (code)**: `f_cb_2 / f_cb_opp_2 × 100`
- **SQL database field / logic**: f_cb_opp_2 = SUM(HudCache.foldToStreet2CBChance); f_cb_2 = SUM(HudCache.foldToStreet2CBDone)
- **Tooltip**: % fold to continuation bet turn/5th street
- **Detailed HUD text**: `f_cb_2`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)
- **Note**: Gives the same value as `fold_to_cbet_turn` (same counters, same formula). The HUD abbreviation `f_cb2` is shared with: `fold_to_cbet_turn`.

### Fold to Turn Bet/Raise (not a C-Bet) — `f_dbr2`

- **HUD abbreviation**: `f_dbr2`
- **Description**: Percentage of the time that a player folded on the turn to a bet or raise that was not a continuation bet.
- **Formula**: (Number of times the player folded on the turn after someone else bet or raised minus Number of folds to a turn continuation bet) / (Number of times the player acted on the turn after someone else bet or raised minus Number of times the player acted after a turn continuation bet) × 100
- **Formula (code)**: `(f_freq_2 − f_cb_2) / (was_raised_2 − f_cb_opp_2) × 100`
- **SQL database field / logic**: f_freq_2 = SUM(HudCache.foldToOtherRaisedStreet2); f_cb_2 = SUM(HudCache.foldToStreet2CBDone); was_raised_2 = SUM(HudCache.otherRaisedStreet2); f_cb_opp_2 = SUM(HudCache.foldToStreet2CBChance)
- **Tooltip**: % Fold to DonkBetAndRaise turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Faced a Raise on the Turn — `face_raise_turn`

- **HUD abbreviation**: `FvRt`
- **Description**: Percentage of the turns a player saw on which they acted after a raise.
- **Formula**: Number of turns where the player acted after a raise / Number of hands where the player saw the turn × 100
- **Formula (code)**: `t_face_raise / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); t_face_raise = SUM(HudCache.street2FaceRaise)
- **Tooltip**: % face raise turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Turn Fold to Bet or Raise — `ffreq2`

- **HUD abbreviation**: `ff2`
- **Description**: Percentage of the time that a player folded on the turn after someone else bet or raised there.
- **Formula**: Number of times the player folded on the turn after someone else bet or raised / Number of times the player acted on the turn after someone else bet or raised × 100
- **Formula (code)**: `f_freq_2 / was_raised_2 × 100`
- **SQL database field / logic**: was_raised_2 = SUM(HudCache.otherRaisedStreet2); f_freq_2 = SUM(HudCache.foldToOtherRaisedStreet2)
- **Tooltip**: % fold frequency turn/5th street
- **Detailed HUD text**: `ff_2`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Turn First Raise — `first_raise_turn`

- **HUD abbreviation**: `1Rt`
- **Description**: Percentage of the turns a player saw on which they made the first raise.
- **Formula**: Number of times the player made the first raise on the turn / Number of hands where the player saw the turn × 100
- **Formula (code)**: `t_first_raise / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); t_first_raise = SUM(HudCache.street2FirstRaise)
- **Tooltip**: % first raise turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Float Bet Turn — `float_bet`

- **HUD abbreviation**: `float`
- **Description**: Meant as the percentage of turns on which the player bet after calling the flop in position. Reads keys the HUD queries do not select.
- **Formula**: min(Number of turn bets, opp) / opp × 100, where opp = the smallest of Number of flops in position, Number of flop calls, Number of turns seen
- **Formula (code)**: `min(street2Bets, opp) / opp × 100 with opp = min(street1InPosition, street1Calls, saw_t)`
- **SQL database field / logic**: street1InPosition = SUM(HudCache.street1InPosition); street1Calls = SUM(HudCache.street1Calls); saw_t = SUM(HudCache.street2Seen); street2Bets = SUM(HudCache.street2Bets)
- **Tooltip**: % float bet turn
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: input-missing
- **Note**: An estimate from totals, not the same hands: the opportunities are the smallest of flops in position, flop calls and turns seen. Several inputs use names the HUD queries expose differently (`call_1`, `saw_2`, `bet_2`).

### Turn Float — `float_turn`

- **HUD abbreviation**: `FltT`
- **Description**: Percentage of the time that a player who called the flop aggressor's bet bet or raised the turn after that aggressor checked to them.
- **Formula**: Number of times the player then bet or raised the turn (float) / Number of times the player had called the flop aggressor's bet, saw the turn and acted after that aggressor checked it × 100
- **Formula (code)**: `float_turn_done / float_turn_chance × 100`
- **SQL database field / logic**: float_turn_chance = SUM(HudCache.flg_t_float_opp); float_turn_done = SUM(HudCache.flg_t_float)
- **Tooltip**: % float turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Fold vs Turn Barrel after Float — `fold_float_turn`

- **HUD abbreviation**: `FvTFl`
- **Description**: Percentage of the time that a player who called the flop c-bet in position folded when the aggressor bet the turn again.
- **Formula**: (Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the turn minus Number of times the player called a bet after having called the previous street's bet in position (a float spot) on the turn minus Number of times the player raised a bet after having called the previous street's bet in position (a float spot) on the turn) / Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the turn × 100
- **Formula (code)**: `(cnt_t_face_float − cnt_t_call_float − cnt_t_raise_float) / cnt_t_face_float × 100`
- **SQL database field / logic**: cnt_t_face_float = SUM(HudCache.cnt_t_face_float); cnt_t_call_float = SUM(HudCache.cnt_t_call_float); cnt_t_raise_float = SUM(HudCache.cnt_t_raise_float)
- **Tooltip**: % folding facing the turn barrel, having called the flop c-bet in position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold to Turn Continuation Bet — `fold_to_cbet_turn`

- **HUD abbreviation**: `f_cb2`
- **Description**: Percentage of the time that a player folded when facing a turn continuation bet.
- **Formula**: Number of folds to a turn continuation bet / Number of times the player acted after a turn continuation bet × 100
- **Formula (code)**: `f_cb_2 / f_cb_opp_2 × 100`
- **SQL database field / logic**: f_cb_opp_2 = SUM(HudCache.foldToStreet2CBChance); f_cb_2 = SUM(HudCache.foldToStreet2CBDone)
- **Tooltip**: % fold to continuation bet turn/5th street
- **Detailed HUD text**: `f_cb_2`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)
- **Note**: Alias: this stat calls `f_cb2` and returns its value unchanged. The HUD abbreviation `f_cb2` is shared with: `f_cb2`.

### Fold to Turn 3-Bet — `fold_to_three_B_turn`

- **HUD abbreviation**: `FT3B`
- **Description**: Percentage of the time that a player who raised the turn folded to a 3-bet.
- **Formula**: Number of times the player folded to a turn 3-bet after raising / Number of times the player raised the turn and faced a 3-bet × 100
- **Formula (code)**: `ft3b / ft3b_opp × 100`
- **SQL database field / logic**: ft3b_opp = SUM(HudCache.street2_FoldTo3BChance); ft3b = SUM(HudCache.street2_FoldTo3BDone)
- **Tooltip**: % fold to turn 3bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Turn Fold — `fold_turn`

- **HUD abbreviation**: `Fldt`
- **Description**: Percentage of the turns a player saw that they folded.
- **Formula**: Number of turns the player folded / Number of hands where the player saw the turn × 100
- **Formula (code)**: `t_fold / saw_2 × 100`
- **SQL database field / logic**: saw_2 = SUM(HudCache.street2Seen); t_fold = SUM(HudCache.flg_t_fold)
- **Tooltip**: % fold turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Fold vs Turn 3-Bet — `fold_vs_turn_3bet`

- **HUD abbreviation**: `FvT3B`
- **Description**: Percentage of the time that a player folded when facing a 3-bet on the turn. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 3-bet on the turn minus Number of times the player called a 3-bet on the turn minus Number of times the player raised a 3-bet on the turn) / Number of times the player faced a 3-bet on the turn × 100
- **Formula (code)**: `(cnt_t_face_3bet − cnt_t_call_3bet − cnt_t_raise_3bet) / cnt_t_face_3bet × 100`
- **SQL database field / logic**: cnt_t_face_3bet = SUM(HudCache.cnt_t_face_3bet); cnt_t_call_3bet = SUM(HudCache.cnt_t_call_3bet); cnt_t_raise_3bet = SUM(HudCache.cnt_t_raise_3bet)
- **Tooltip**: % folding facing a turn 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Turn 4-Bet — `fold_vs_turn_4bet`

- **HUD abbreviation**: `FvT4B`
- **Description**: Percentage of the time that a player folded when facing a 4-bet on the turn. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 4-bet on the turn minus Number of times the player called a 4-bet on the turn minus Number of times the player raised a 4-bet on the turn) / Number of times the player faced a 4-bet on the turn × 100
- **Formula (code)**: `(cnt_t_face_4bet − cnt_t_call_4bet − cnt_t_raise_4bet) / cnt_t_face_4bet × 100`
- **SQL database field / logic**: cnt_t_face_4bet = SUM(HudCache.cnt_t_face_4bet); cnt_t_call_4bet = SUM(HudCache.cnt_t_call_4bet); cnt_t_raise_4bet = SUM(HudCache.cnt_t_raise_4bet)
- **Tooltip**: % folding facing a turn 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Turn C-Bet — `fold_vs_turn_cbet`

- **HUD abbreviation**: `FvTCB`
- **Description**: Percentage of the time that a player folded when facing a continuation bet on the turn. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a continuation bet on the turn minus Number of times the player called a continuation bet on the turn minus Number of times the player raised a continuation bet on the turn) / Number of times the player faced a continuation bet on the turn × 100
- **Formula (code)**: `(cnt_t_face_cbet − cnt_t_call_cbet − cnt_t_raise_cbet) / cnt_t_face_cbet × 100`
- **SQL database field / logic**: cnt_t_face_cbet = SUM(HudCache.cnt_t_face_cbet); cnt_t_call_cbet = SUM(HudCache.cnt_t_call_cbet); cnt_t_raise_cbet = SUM(HudCache.cnt_t_raise_cbet)
- **Tooltip**: % folding facing a turn c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs Turn Donk Bet — `fold_vs_turn_donk`

- **HUD abbreviation**: `FvTDk`
- **Description**: Percentage of the time that a player folded when facing a donk bet (a bet into the preflop raiser) on the turn. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a donk bet (a bet into the preflop raiser) on the turn minus Number of times the player called a donk bet (a bet into the preflop raiser) on the turn minus Number of times the player raised a donk bet (a bet into the preflop raiser) on the turn) / Number of times the player faced a donk bet (a bet into the preflop raiser) on the turn × 100
- **Formula (code)**: `(cnt_t_face_donk − cnt_t_call_donk − cnt_t_raise_donk) / cnt_t_face_donk × 100`
- **SQL database field / logic**: cnt_t_face_donk = SUM(HudCache.cnt_t_face_donk); cnt_t_call_donk = SUM(HudCache.cnt_t_call_donk); cnt_t_raise_donk = SUM(HudCache.cnt_t_raise_donk)
- **Tooltip**: % folding facing a turn donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Turn 4-Bet — `four_B_turn`

- **HUD abbreviation**: `T4B`
- **Description**: Percentage of the time that a player re-raised when facing a 3-bet on the turn.
- **Formula**: Number of turn 4-bets / Number of times the player faced a turn 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `tn4b / tn4b_opp × 100`
- **SQL database field / logic**: tn4b_opp = SUM(HudCache.street2_4BChance); tn4b = SUM(HudCache.street2_4BDone)
- **Tooltip**: % 4 bet turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Turn Open (first bet) — `open_turn`

- **HUD abbreviation**: `OPt`
- **Description**: Percentage of the time that a player made the first bet on the turn when nobody had bet before them.
- **Formula**: Number of times the player made the first bet on the turn / Number of times the player acted on the turn before anyone had bet × 100
- **Formula (code)**: `tnopen / tnopen_opp × 100`
- **SQL database field / logic**: tnopen_opp = SUM(HudCache.street2OpenChance); tnopen = SUM(HudCache.street2OpenDone)
- **Tooltip**: % open turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)

### Turn Probe Bet — `probe_bet_turn`

- **HUD abbreviation**: `probe_t`
- **Description**: Meant as the percentage of turns seen without having c-bet on which the player bet. Reads keys the HUD queries do not select.
- **Formula**: min(turn bets, turns seen − turn c-bets) / (Number of turns seen − Number of turn c-bets) × 100
- **Formula (code)**: `min(street2Bets, saw_t − cb_2) / (saw_t − cb_2) × 100`
- **SQL database field / logic**: saw_t = SUM(HudCache.street2Seen); cb_2 = SUM(HudCache.street2CBDone); street2Bets = SUM(HudCache.street2Bets)
- **Tooltip**: % probe bet turn
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: input-missing
- **Note**: Turn probe. The HUD queries name the turn-seen count `saw_2` and the bet count `bet_2`, not the keys this stat reads.

### Bet the turn (as non-aggressor) after the preflop raiser checked the flop. — `probe_turn`

- **HUD abbreviation**: `Probe Turn`
- **Description**: Bet the turn (as non-aggressor) after the preflop raiser checked the flop.
- **Formula (code)**: `100 * street2ProbeDone / street2ProbeChance   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): street2ProbeDone, street2ProbeChance
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Raise vs Turn Barrel after Float — `raise_float_turn`

- **HUD abbreviation**: `RvTFl`
- **Description**: Percentage of the time that a player who called the flop c-bet in position raised when the aggressor bet the turn again.
- **Formula**: Number of times the player raised a bet after having called the previous street's bet in position (a float spot) on the turn / Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the turn × 100
- **Formula (code)**: `cnt_t_raise_float / cnt_t_face_float × 100`
- **SQL database field / logic**: cnt_t_face_float = SUM(HudCache.cnt_t_face_float); cnt_t_raise_float = SUM(HudCache.cnt_t_raise_float)
- **Tooltip**: % raising facing the turn barrel, having called the flop c-bet in position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Turn Raise Frequency — `raise_frequency_turn`

- **HUD abbreviation**: `raise_t`
- **Description**: Meant as raises per turn seen. Reads keys the HUD queries do not select, so the value is not reliable.
- **Formula**: Number of turn raises (key not selected by the HUD queries, which name it raise_2) / Number of hands where the player saw the turn (key not selected by the HUD queries) × 100
- **Formula (code)**: `street2Raises / saw_t × 100`
- **SQL database field / logic**: saw_t (not selected by the HUD queries); street2Raises (not selected by the HUD queries)
- **Tooltip**: % raise frequency turn
- **Detailed HUD text**: `raise_freq_turn`
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: input-missing
- **Note**: An input is read under a name the HUD queries do not select, so the value is computed from a missing column. Check the HUD queries before relying on it.

### Raise vs Turn 3-Bet — `raise_vs_turn_3bet`

- **HUD abbreviation**: `RvT3B`
- **Description**: Percentage of the time that a player raised when facing a 3-bet on the turn.
- **Formula**: Number of times the player raised a 3-bet on the turn / Number of times the player faced a 3-bet on the turn × 100
- **Formula (code)**: `cnt_t_raise_3bet / cnt_t_face_3bet × 100`
- **SQL database field / logic**: cnt_t_face_3bet = SUM(HudCache.cnt_t_face_3bet); cnt_t_raise_3bet = SUM(HudCache.cnt_t_raise_3bet)
- **Tooltip**: % raising facing a turn 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs Turn 4-Bet — `raise_vs_turn_4bet`

- **HUD abbreviation**: `RvT4B`
- **Description**: Percentage of the time that a player raised when facing a 4-bet on the turn.
- **Formula**: Number of times the player raised a 4-bet on the turn / Number of times the player faced a 4-bet on the turn × 100
- **Formula (code)**: `cnt_t_raise_4bet / cnt_t_face_4bet × 100`
- **SQL database field / logic**: cnt_t_face_4bet = SUM(HudCache.cnt_t_face_4bet); cnt_t_raise_4bet = SUM(HudCache.cnt_t_raise_4bet)
- **Tooltip**: % raising facing a turn 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs Turn C-Bet — `raise_vs_turn_cbet`

- **HUD abbreviation**: `RvTCB`
- **Description**: Percentage of the time that a player raised when facing a continuation bet on the turn.
- **Formula**: Number of times the player raised a continuation bet on the turn / Number of times the player faced a continuation bet on the turn × 100
- **Formula (code)**: `cnt_t_raise_cbet / cnt_t_face_cbet × 100`
- **SQL database field / logic**: cnt_t_face_cbet = SUM(HudCache.cnt_t_face_cbet); cnt_t_raise_cbet = SUM(HudCache.cnt_t_raise_cbet)
- **Tooltip**: % raising facing a turn c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs Turn Donk Bet — `raise_vs_turn_donk`

- **HUD abbreviation**: `RvTDk`
- **Description**: Percentage of the time that a player raised when facing a donk bet (a bet into the preflop raiser) on the turn.
- **Formula**: Number of times the player raised a donk bet (a bet into the preflop raiser) on the turn / Number of times the player faced a donk bet (a bet into the preflop raiser) on the turn × 100
- **Formula (code)**: `cnt_t_raise_donk / cnt_t_face_donk × 100`
- **SQL database field / logic**: cnt_t_face_donk = SUM(HudCache.cnt_t_face_donk); cnt_t_raise_donk = SUM(HudCache.cnt_t_raise_donk)
- **Tooltip**: % raising facing a turn donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Price of Turn Raise Faced — `t_2bet_facing`

- **HUD abbreviation**: `T2vs`
- **Description**: The average price the player was offered when facing a turn raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the turn raises faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of turn raises faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(t_2bet_facing_bp / t_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_2bet_facing_cnt = SUM(HudCache.cnt_t_2bet_facing); t_2bet_facing_bp = SUM(HudCache.val_t_2bet_facing_bp)
- **Tooltip**: avg turn 2bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_postflop_raise_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Turn 3-Bet Faced — `t_3bet_facing`

- **HUD abbreviation**: `T3vs`
- **Description**: The average price the player was offered when facing a turn 3-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the turn 3-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of turn 3-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(t_3bet_facing_bp / t_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_3bet_facing_cnt = SUM(HudCache.cnt_t_3bet_facing); t_3bet_facing_bp = SUM(HudCache.val_t_3bet_facing_bp)
- **Tooltip**: avg turn 3bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Turn 4-Bet Faced — `t_4bet_facing`

- **HUD abbreviation**: `T4vs`
- **Description**: The average price the player was offered when facing a turn 4-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the turn 4-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of turn 4-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(t_4bet_facing_bp / t_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_4bet_facing_cnt = SUM(HudCache.cnt_t_4bet_facing); t_4bet_facing_bp = SUM(HudCache.val_t_4bet_facing_bp)
- **Tooltip**: avg turn 4bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Turn Bet Faced — `t_bet_facing`

- **HUD abbreviation**: `TBvs`
- **Description**: The average price the player was offered when facing a turn bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the turn bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of turn bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(t_bet_facing_bp / t_bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_bet_facing_cnt = SUM(HudCache.cnt_t_bet_facing); t_bet_facing_bp = SUM(HudCache.val_t_bet_facing_bp)
- **Tooltip**: avg turn bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_turn_river_bet_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Turn Bet Size — `t_bet_made`

- **HUD abbreviation**: `TBet`
- **Description**: The average size of the player's first turn bet, as a percentage of the pot before the bet.
- **Formula**: Sum of sizes of those bets: bet / pot before the bet, in basis points / Number of first bets made on the turn / 10 000 × 100
- **Formula (code)**: `(t_bet_made_bp / t_bet_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_bet_made_cnt = SUM(HudCache.cnt_t_bet_made); t_bet_made_bp = SUM(HudCache.val_t_bet_made_bp)
- **Tooltip**: avg turn bet made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_made.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of Turn Raise Faced — `t_raise_facing`

- **HUD abbreviation**: `TRvs`
- **Description**: The average price the player was offered when facing a turn raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot. When several raises are faced on the street, the last one counts.
- **Formula**: Sum of prices of the turn raises (most recent level) faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of turn raises (most recent level) faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(t_raise_facing_bp / t_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_raise_facing_cnt = SUM(HudCache.cnt_t_raise_facing); t_raise_facing_bp = SUM(HudCache.val_t_raise_facing_bp)
- **Tooltip**: avg turn raise faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Turn Raise Size — `t_raise_made`

- **HUD abbreviation**: `TRz`
- **Description**: The average size of the player's first turn raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those raises: raise-to amount / pot before the raise, in basis points / Number of first raises made on the turn / 10 000 × 100
- **Formula (code)**: `(t_raise_made_bp / t_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_raise_made_cnt = SUM(HudCache.cnt_t_raise_made); t_raise_made_bp = SUM(HudCache.val_t_raise_made_bp)
- **Tooltip**: avg turn raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average Turn Raise Size (2nd raise) — `t_raise_made_2`

- **HUD abbreviation**: `TRz2`
- **Description**: The average size of the player's second turn raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those second raises: raise-to amount / pot before the raise, in basis points / Number of second raises made by the player on the turn / 10 000 × 100
- **Formula (code)**: `(t_raise_made_2_bp / t_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: t_raise_made_2_cnt = SUM(HudCache.cnt_t_raise_made_2); t_raise_made_2_bp = SUM(HudCache.val_t_raise_made_2_bp)
- **Tooltip**: avg 2nd turn raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Turn Stack-to-Pot Ratio — `t_spr`

- **HUD abbreviation**: `tSPR`
- **Description**: The average stack-to-pot ratio entering the turn: the effective stack (smallest of the player's and the deepest active opponent's) divided by the pot.
- **Formula**: Sum of stack-to-pot ratios entering the turn (effective stack / pot), stored ×100 / Number of turns with a recorded stack-to-pot ratio × 0.01
- **Formula (code)**: `0.01 × t_spr_val / t_spr_cnt`
- **SQL database field / logic**: t_spr_cnt = SUM(HudCache.cnt_t_spr); t_spr_val = SUM(HudCache.val_t_spr)
- **Tooltip**: avg turn SPR
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Turn 3-Bet — `three_B_turn`

- **HUD abbreviation**: `T3B`
- **Description**: Percentage of the time that a player re-raised when facing a bet and a raise on the turn.
- **Formula**: Number of turn 3-bets (re-raise of a bet and a raise) / Number of times the player faced a bet and a raise on the turn × 100
- **Formula (code)**: `tn3b / tn3b_opp × 100`
- **SQL database field / logic**: tn3b_opp = SUM(HudCache.street2_3BChance); tn3b = SUM(HudCache.street2_3BDone)
- **Tooltip**: % 3 bet turn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: yes, on 5th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the second draw (triple draw)
- **PT4 derivation tests**: `test_calc_3bet_postflop.py`

## River / 6th street

### River Aggression Frequency — `a_freq3`

- **HUD abbreviation**: `a3`
- **Description**: Percentage of the time that a player bet or raised at least once on the river, given that they saw it.
- **Formula**: Number of hands where the player bet or raised on the river / Number of hands where the player saw the river × 100
- **Formula (code)**: `aggr_3 / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); aggr_3 = SUM(HudCache.street3Aggr)
- **Tooltip**: Aggression frequency river/6th street
- **Detailed HUD text**: `a_fq_3`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)
- **XML titles**: `RvAFq`

### Average Bet Size River (deprecated) — `avg_bet_size_river`

- **HUD abbreviation**: `avg_bet_r`
- **Description**: Shows no data. Use Average River Bet Made (`r_bet_made`).
- **Formula (code)**: `no data (deprecated); see `r_bet_made``
- **SQL database field / logic**: none
- **Tooltip**: avg bet size river (deprecated)
- **Games**: none (shows no data)
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: deprecated

### Call vs River Barrel after Float — `call_float_river`

- **HUD abbreviation**: `CvRFl`
- **Description**: Percentage of the time that a player who called the turn bet in position called when the aggressor bet the river again.
- **Formula**: Number of times the player called a bet after having called the previous street's bet in position (a float spot) on the river / Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the river × 100
- **Formula (code)**: `cnt_r_call_float / cnt_r_face_float × 100`
- **SQL database field / logic**: cnt_r_face_float = SUM(HudCache.cnt_r_face_float); cnt_r_call_float = SUM(HudCache.cnt_r_call_float)
- **Tooltip**: % calling facing the river barrel, having called the turn bet in position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Call vs River 3-Bet — `call_vs_river_3bet`

- **HUD abbreviation**: `CvR3B`
- **Description**: Percentage of the time that a player called when facing a 3-bet on the river.
- **Formula**: Number of times the player called a 3-bet on the river / Number of times the player faced a 3-bet on the river × 100
- **Formula (code)**: `cnt_r_call_3bet / cnt_r_face_3bet × 100`
- **SQL database field / logic**: cnt_r_face_3bet = SUM(HudCache.cnt_r_face_3bet); cnt_r_call_3bet = SUM(HudCache.cnt_r_call_3bet)
- **Tooltip**: % calling facing a river 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs River 4-Bet — `call_vs_river_4bet`

- **HUD abbreviation**: `CvR4B`
- **Description**: Percentage of the time that a player called when facing a 4-bet on the river.
- **Formula**: Number of times the player called a 4-bet on the river / Number of times the player faced a 4-bet on the river × 100
- **Formula (code)**: `cnt_r_call_4bet / cnt_r_face_4bet × 100`
- **SQL database field / logic**: cnt_r_face_4bet = SUM(HudCache.cnt_r_face_4bet); cnt_r_call_4bet = SUM(HudCache.cnt_r_call_4bet)
- **Tooltip**: % calling facing a river 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs River C-Bet — `call_vs_river_cbet`

- **HUD abbreviation**: `CvRCB`
- **Description**: Percentage of the time that a player called when facing a continuation bet on the river.
- **Formula**: Number of times the player called a continuation bet on the river / Number of times the player faced a continuation bet on the river × 100
- **Formula (code)**: `cnt_r_call_cbet / cnt_r_face_cbet × 100`
- **SQL database field / logic**: cnt_r_face_cbet = SUM(HudCache.cnt_r_face_cbet); cnt_r_call_cbet = SUM(HudCache.cnt_r_call_cbet)
- **Tooltip**: % calling facing a river c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Call vs River Donk Bet — `call_vs_river_donk`

- **HUD abbreviation**: `CvRDk`
- **Description**: Percentage of the time that a player called when facing a donk bet (a bet into the preflop raiser) on the river.
- **Formula**: Number of times the player called a donk bet (a bet into the preflop raiser) on the river / Number of times the player faced a donk bet (a bet into the preflop raiser) on the river × 100
- **Formula (code)**: `cnt_r_call_donk / cnt_r_face_donk × 100`
- **SQL database field / logic**: cnt_r_face_donk = SUM(HudCache.cnt_r_face_donk); cnt_r_call_donk = SUM(HudCache.cnt_r_call_donk)
- **Tooltip**: % calling facing a river donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### River Continuation Bet — `cb3`

- **HUD abbreviation**: `cb3`
- **Description**: Percentage of the time that the last preflop raiser bet (or raised) on the river when they had the chance.
- **Formula**: Number of continuation bets on the river (the last preflop raiser bet or raised on the street) / Number of river continuation-bet opportunities (the last preflop raiser, not folded yet) × 100
- **Formula (code)**: `cb_3 / cb_opp_3 × 100`
- **SQL database field / logic**: cb_opp_3 = SUM(HudCache.street3CBChance); cb_3 = SUM(HudCache.street3CBDone)
- **Tooltip**: % continuation bet river/6th street
- **Detailed HUD text**: `cb_3`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### River Check-Raise — `cr3`

- **HUD abbreviation**: `cr3`
- **Description**: Percentage of the time that a player check-raised the river, given that they checked and acted again on it.
- **Formula**: Number of check-raises on the river / Number of times the player checked on the river and acted again on that street × 100
- **Formula (code)**: `cr_3 / ccr_opp_3 × 100`
- **SQL database field / logic**: ccr_opp_3 = SUM(HudCache.street3CheckCallRaiseChance); cr_3 = SUM(HudCache.street3CheckRaiseDone)
- **Tooltip**: % check-raise river/6th street
- **Detailed HUD text**: `cr_3`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### River Bet/Raise when not the C-Bettor — `dbr3`

- **HUD abbreviation**: `dbr3`
- **Description**: Percentage of the rivers a player saw outside a continuation-bet spot on which they bet or raised: aggression that is not a c-bet (donk bets and raises).
- **Formula**: (Number of hands where the player bet or raised on the river minus Number of continuation bets on the river (the last preflop raiser bet or raised on the street)) / (Number of hands where the player saw the river minus Number of river continuation-bet opportunities (the last preflop raiser, not folded yet)) × 100
- **Formula (code)**: `(aggr_3 − cb_3) / (saw_3 − cb_opp_3) × 100`
- **SQL database field / logic**: aggr_3 = SUM(HudCache.street3Aggr); cb_3 = SUM(HudCache.street3CBDone); saw_3 = SUM(HudCache.street3Seen); cb_opp_3 = SUM(HudCache.street3CBChance)
- **Tooltip**: % DonkBetAndRaise river/6th street
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### Fold to River Continuation Bet — `f_cb3`

- **HUD abbreviation**: `f_cb3`
- **Description**: Percentage of the time that a player folded when facing a river continuation bet.
- **Formula**: Number of folds to a river continuation bet / Number of times the player acted after a river continuation bet × 100
- **Formula (code)**: `f_cb_3 / f_cb_opp_3 × 100`
- **SQL database field / logic**: f_cb_opp_3 = SUM(HudCache.foldToStreet3CBChance); f_cb_3 = SUM(HudCache.foldToStreet3CBDone)
- **Tooltip**: % fold to continuation bet river/6th street
- **Detailed HUD text**: `f_cb_3`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)
- **Note**: Gives the same value as `fold_to_cbet_river` (same counters, same formula). The HUD abbreviation `f_cb3` is shared with: `fold_to_cbet_river`.

### Fold to River Bet/Raise (not a C-Bet) — `f_dbr3`

- **HUD abbreviation**: `f_dbr3`
- **Description**: Percentage of the time that a player folded on the river to a bet or raise that was not a continuation bet.
- **Formula**: (Number of times the player folded on the river after someone else bet or raised minus Number of folds to a river continuation bet) / (Number of times the player acted on the river after someone else bet or raised minus Number of times the player acted after a river continuation bet) × 100
- **Formula (code)**: `(f_freq_3 − f_cb_3) / (was_raised_3 − f_cb_opp_3) × 100`
- **SQL database field / logic**: f_freq_3 = SUM(HudCache.foldToOtherRaisedStreet3); f_cb_3 = SUM(HudCache.foldToStreet3CBDone); was_raised_3 = SUM(HudCache.otherRaisedStreet3); f_cb_opp_3 = SUM(HudCache.foldToStreet3CBChance)
- **Tooltip**: % Fold to DonkBetAndRaise river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### Faced a Raise on the River — `face_raise_river`

- **HUD abbreviation**: `FvRr`
- **Description**: Percentage of the rivers a player saw on which they acted after a raise.
- **Formula**: Number of rivers where the player acted after a raise / Number of hands where the player saw the river × 100
- **Formula (code)**: `r_face_raise / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); r_face_raise = SUM(HudCache.street3FaceRaise)
- **Tooltip**: % face raise river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### River Fold to Bet or Raise — `ffreq3`

- **HUD abbreviation**: `ff3`
- **Description**: Percentage of the time that a player folded on the river after someone else bet or raised there.
- **Formula**: Number of times the player folded on the river after someone else bet or raised / Number of times the player acted on the river after someone else bet or raised × 100
- **Formula (code)**: `f_freq_3 / was_raised_3 × 100`
- **SQL database field / logic**: was_raised_3 = SUM(HudCache.otherRaisedStreet3); f_freq_3 = SUM(HudCache.foldToOtherRaisedStreet3)
- **Tooltip**: % fold frequency river/6th street
- **Detailed HUD text**: `ff_3`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### River First Raise — `first_raise_river`

- **HUD abbreviation**: `1Rr`
- **Description**: Percentage of the rivers a player saw on which they made the first raise.
- **Formula**: Number of times the player made the first raise on the river / Number of hands where the player saw the river × 100
- **Formula (code)**: `r_first_raise / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); r_first_raise = SUM(HudCache.street3FirstRaise)
- **Tooltip**: % first raise river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### River Float — `float_river`

- **HUD abbreviation**: `FltR`
- **Description**: Percentage of the time that a player who called the turn aggressor's bet bet or raised the river after that aggressor checked to them.
- **Formula**: Number of times the player then bet or raised the river (float) / Number of times the player had called the turn aggressor's bet, saw the river and acted after that aggressor checked it × 100
- **Formula (code)**: `float_river_done / float_river_chance × 100`
- **SQL database field / logic**: float_river_chance = SUM(HudCache.flg_r_float_opp); float_river_done = SUM(HudCache.flg_r_float)
- **Tooltip**: % float river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### Fold vs River Barrel after Float — `fold_float_river`

- **HUD abbreviation**: `FvRFl`
- **Description**: Percentage of the time that a player who called the turn bet in position folded when the aggressor bet the river again.
- **Formula**: (Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the river minus Number of times the player called a bet after having called the previous street's bet in position (a float spot) on the river minus Number of times the player raised a bet after having called the previous street's bet in position (a float spot) on the river) / Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the river × 100
- **Formula (code)**: `(cnt_r_face_float − cnt_r_call_float − cnt_r_raise_float) / cnt_r_face_float × 100`
- **SQL database field / logic**: cnt_r_face_float = SUM(HudCache.cnt_r_face_float); cnt_r_call_float = SUM(HudCache.cnt_r_call_float); cnt_r_raise_float = SUM(HudCache.cnt_r_raise_float)
- **Tooltip**: % folding facing the river barrel, having called the turn bet in position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### River Fold — `fold_river`

- **HUD abbreviation**: `Fldr`
- **Description**: Percentage of the rivers a player saw that they folded.
- **Formula**: Number of rivers the player folded / Number of hands where the player saw the river × 100
- **Formula (code)**: `r_fold / saw_3 × 100`
- **SQL database field / logic**: saw_3 = SUM(HudCache.street3Seen); r_fold = SUM(HudCache.flg_r_fold)
- **Tooltip**: % fold river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### Fold to River Continuation Bet — `fold_to_cbet_river`

- **HUD abbreviation**: `f_cb3`
- **Description**: Percentage of the time that a player folded when facing a river continuation bet.
- **Formula**: Number of folds to a river continuation bet / Number of times the player acted after a river continuation bet × 100
- **Formula (code)**: `f_cb_3 / f_cb_opp_3 × 100`
- **SQL database field / logic**: f_cb_opp_3 = SUM(HudCache.foldToStreet3CBChance); f_cb_3 = SUM(HudCache.foldToStreet3CBDone)
- **Tooltip**: % fold to continuation bet river/6th street
- **Detailed HUD text**: `f_cb_3`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)
- **Note**: Alias: this stat calls `f_cb3` and returns its value unchanged. The HUD abbreviation `f_cb3` is shared with: `f_cb3`.

### Fold to River 3-Bet — `fold_to_three_B_river`

- **HUD abbreviation**: `FR3B`
- **Description**: Percentage of the time that a player who raised the river folded to a 3-bet.
- **Formula**: Number of times the player folded to a river 3-bet after raising / Number of times the player raised the river and faced a 3-bet × 100
- **Formula (code)**: `fr3b / fr3b_opp × 100`
- **SQL database field / logic**: fr3b_opp = SUM(HudCache.street3_FoldTo3BChance); fr3b = SUM(HudCache.street3_FoldTo3BDone)
- **Tooltip**: % fold to river 3bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Fold vs River 3-Bet — `fold_vs_river_3bet`

- **HUD abbreviation**: `FvR3B`
- **Description**: Percentage of the time that a player folded when facing a 3-bet on the river. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 3-bet on the river minus Number of times the player called a 3-bet on the river minus Number of times the player raised a 3-bet on the river) / Number of times the player faced a 3-bet on the river × 100
- **Formula (code)**: `(cnt_r_face_3bet − cnt_r_call_3bet − cnt_r_raise_3bet) / cnt_r_face_3bet × 100`
- **SQL database field / logic**: cnt_r_face_3bet = SUM(HudCache.cnt_r_face_3bet); cnt_r_call_3bet = SUM(HudCache.cnt_r_call_3bet); cnt_r_raise_3bet = SUM(HudCache.cnt_r_raise_3bet)
- **Tooltip**: % folding facing a river 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs River 4-Bet — `fold_vs_river_4bet`

- **HUD abbreviation**: `FvR4B`
- **Description**: Percentage of the time that a player folded when facing a 4-bet on the river. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a 4-bet on the river minus Number of times the player called a 4-bet on the river minus Number of times the player raised a 4-bet on the river) / Number of times the player faced a 4-bet on the river × 100
- **Formula (code)**: `(cnt_r_face_4bet − cnt_r_call_4bet − cnt_r_raise_4bet) / cnt_r_face_4bet × 100`
- **SQL database field / logic**: cnt_r_face_4bet = SUM(HudCache.cnt_r_face_4bet); cnt_r_call_4bet = SUM(HudCache.cnt_r_call_4bet); cnt_r_raise_4bet = SUM(HudCache.cnt_r_raise_4bet)
- **Tooltip**: % folding facing a river 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs River C-Bet — `fold_vs_river_cbet`

- **HUD abbreviation**: `FvRCB`
- **Description**: Percentage of the time that a player folded when facing a continuation bet on the river. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a continuation bet on the river minus Number of times the player called a continuation bet on the river minus Number of times the player raised a continuation bet on the river) / Number of times the player faced a continuation bet on the river × 100
- **Formula (code)**: `(cnt_r_face_cbet − cnt_r_call_cbet − cnt_r_raise_cbet) / cnt_r_face_cbet × 100`
- **SQL database field / logic**: cnt_r_face_cbet = SUM(HudCache.cnt_r_face_cbet); cnt_r_call_cbet = SUM(HudCache.cnt_r_call_cbet); cnt_r_raise_cbet = SUM(HudCache.cnt_r_raise_cbet)
- **Tooltip**: % folding facing a river c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### Fold vs River Donk Bet — `fold_vs_river_donk`

- **HUD abbreviation**: `FvRDk`
- **Description**: Percentage of the time that a player folded when facing a donk bet (a bet into the preflop raiser) on the river. Folds are not stored: they are the spots faced minus calls and raises, so call, raise and fold add up to 100%.
- **Formula**: (Number of times the player faced a donk bet (a bet into the preflop raiser) on the river minus Number of times the player called a donk bet (a bet into the preflop raiser) on the river minus Number of times the player raised a donk bet (a bet into the preflop raiser) on the river) / Number of times the player faced a donk bet (a bet into the preflop raiser) on the river × 100
- **Formula (code)**: `(cnt_r_face_donk − cnt_r_call_donk − cnt_r_raise_donk) / cnt_r_face_donk × 100`
- **SQL database field / logic**: cnt_r_face_donk = SUM(HudCache.cnt_r_face_donk); cnt_r_call_donk = SUM(HudCache.cnt_r_call_donk); cnt_r_raise_donk = SUM(HudCache.cnt_r_raise_donk)
- **Tooltip**: % folding facing a river donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise.

### River 4-Bet — `four_B_river`

- **HUD abbreviation**: `R4B`
- **Description**: Percentage of the time that a player re-raised when facing a 3-bet on the river.
- **Formula**: Number of river 4-bets / Number of times the player faced a river 3-bet with the chance to 4-bet × 100
- **Formula (code)**: `rv4b / rv4b_opp × 100`
- **SQL database field / logic**: rv4b_opp = SUM(HudCache.street3_4BChance); rv4b = SUM(HudCache.street3_4BDone)
- **Tooltip**: % 4 bet river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### River Open (first bet) — `open_river`

- **HUD abbreviation**: `OPr`
- **Description**: Percentage of the time that a player made the first bet on the river when nobody had bet before them.
- **Formula**: Number of times the player made the first bet on the river / Number of times the player acted on the river before anyone had bet × 100
- **Formula (code)**: `rvopen / rvopen_opp × 100`
- **SQL database field / logic**: rvopen_opp = SUM(HudCache.street3OpenChance); rvopen = SUM(HudCache.street3OpenDone)
- **Tooltip**: % open river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### River Probe Bet — `probe_bet_river`

- **HUD abbreviation**: `probe_r`
- **Description**: Meant as the percentage of rivers seen without having c-bet on which the player bet. Reads keys the HUD queries do not select.
- **Formula**: min(river bets, rivers seen − river c-bets) / (Number of rivers seen − Number of river c-bets) × 100
- **Formula (code)**: `min(street3Bets, saw_r − cb_3) / (saw_r − cb_3) × 100`
- **SQL database field / logic**: saw_r = SUM(HudCache.street3Seen); cb_3 = SUM(HudCache.street3CBDone); street3Bets = SUM(HudCache.street3Bets)
- **Tooltip**: % probe bet river
- **Games**: none: the stat shows no data
- **Hold'em / Omaha (flop games)**: no data
- **Stud / Razz**: no data
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data
- **Status**: input-missing
- **Note**: River probe. The HUD queries name the river-seen count `saw_3` and the bet count `bet_3`, not the keys this stat reads.

### Price of River Raise Faced — `r_2bet_facing`

- **HUD abbreviation**: `R2vs`
- **Description**: The average price the player was offered when facing a river raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the river raises faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of river raises faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(r_2bet_facing_bp / r_2bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_2bet_facing_cnt = SUM(HudCache.cnt_r_2bet_facing); r_2bet_facing_bp = SUM(HudCache.val_r_2bet_facing_bp)
- **Tooltip**: avg river 2bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of River 3-Bet Faced — `r_3bet_facing`

- **HUD abbreviation**: `R3vs`
- **Description**: The average price the player was offered when facing a river 3-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the river 3-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of river 3-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(r_3bet_facing_bp / r_3bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_3bet_facing_cnt = SUM(HudCache.cnt_r_3bet_facing); r_3bet_facing_bp = SUM(HudCache.val_r_3bet_facing_bp)
- **Tooltip**: avg river 3bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of River 4-Bet Faced — `r_4bet_facing`

- **HUD abbreviation**: `R4vs`
- **Description**: The average price the player was offered when facing a river 4-bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the river 4-bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of river 4-bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(r_4bet_facing_bp / r_4bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_4bet_facing_cnt = SUM(HudCache.cnt_r_4bet_facing); r_4bet_facing_bp = SUM(HudCache.val_r_4bet_facing_bp)
- **Tooltip**: avg river 4bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of River Bet Faced — `r_bet_facing`

- **HUD abbreviation**: `RBvs`
- **Description**: The average price the player was offered when facing a river bet: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot.
- **Formula**: Sum of prices of the river bets faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of river bets faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(r_bet_facing_bp / r_bet_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_bet_facing_cnt = SUM(HudCache.cnt_r_bet_facing); r_bet_facing_bp = SUM(HudCache.val_r_bet_facing_bp)
- **Tooltip**: avg river bet faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_turn_river_bet_facing.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average River Bet Size — `r_bet_made`

- **HUD abbreviation**: `RBet`
- **Description**: The average size of the player's first river bet, as a percentage of the pot before the bet.
- **Formula**: Sum of sizes of those bets: bet / pot before the bet, in basis points / Number of first bets made on the river / 10 000 × 100
- **Formula (code)**: `(r_bet_made_bp / r_bet_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_bet_made_cnt = SUM(HudCache.cnt_r_bet_made); r_bet_made_bp = SUM(HudCache.val_r_bet_made_bp)
- **Tooltip**: avg river bet made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_made.py`
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Price of River Raise Faced — `r_raise_facing`

- **HUD abbreviation**: `RRvs`
- **Description**: The average price the player was offered when facing a river raise: the amount to call divided by the pot at the moment of the decision (the pot already holds the bet), as a percentage. 50% means a call of half the pot. When several raises are faced on the street, the last one counts.
- **Formula**: Sum of prices of the river raises (most recent level) faced: amount to call / pot at the decision (the pot already holds the bet), in basis points / Number of river raises (most recent level) faced with a recorded price / 10 000 × 100
- **Formula (code)**: `(r_raise_facing_bp / r_raise_facing_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_raise_facing_cnt = SUM(HudCache.cnt_r_raise_facing); r_raise_facing_bp = SUM(HudCache.val_r_raise_facing_bp)
- **Tooltip**: avg river raise faced (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average River Raise Size — `r_raise_made`

- **HUD abbreviation**: `RRz`
- **Description**: The average size of the player's first river raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those raises: raise-to amount / pot before the raise, in basis points / Number of first raises made on the river / 10 000 × 100
- **Formula (code)**: `(r_raise_made_bp / r_raise_made_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_raise_made_cnt = SUM(HudCache.cnt_r_raise_made); r_raise_made_bp = SUM(HudCache.val_r_raise_made_bp)
- **Tooltip**: avg river raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### Average River Raise Size (2nd raise) — `r_raise_made_2`

- **HUD abbreviation**: `RRz2`
- **Description**: The average size of the player's second river raise: the raise-to amount as a percentage of the pot before the raise.
- **Formula**: Sum of sizes of those second raises: raise-to amount / pot before the raise, in basis points / Number of second raises made by the player on the river / 10 000 × 100
- **Formula (code)**: `(r_raise_made_2_bp / r_raise_made_2_cnt) / 10 000 × 100`
- **SQL database field / logic**: r_raise_made_2_cnt = SUM(HudCache.cnt_r_raise_made_2); r_raise_made_2_bp = SUM(HudCache.val_r_raise_made_2_bp)
- **Tooltip**: avg 2nd river raise made (% pot)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot.

### River Stack-to-Pot Ratio — `r_spr`

- **HUD abbreviation**: `rSPR`
- **Description**: The average stack-to-pot ratio entering the river: the effective stack (smallest of the player's and the deepest active opponent's) divided by the pot.
- **Formula**: Sum of stack-to-pot ratios entering the river (effective stack / pot), stored ×100 / Number of rivers with a recorded stack-to-pot ratio × 0.01
- **Formula (code)**: `0.01 × r_spr_val / r_spr_cnt`
- **SQL database field / logic**: r_spr_cnt = SUM(HudCache.cnt_r_spr); r_spr_val = SUM(HudCache.val_r_spr)
- **Tooltip**: avg river SPR
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs River Barrel after Float — `raise_float_river`

- **HUD abbreviation**: `RvRFl`
- **Description**: Percentage of the time that a player who called the turn bet in position raised when the aggressor bet the river again.
- **Formula**: Number of times the player raised a bet after having called the previous street's bet in position (a float spot) on the river / Number of times the player faced a bet after having called the previous street's bet in position (a float spot) on the river × 100
- **Formula (code)**: `cnt_r_raise_float / cnt_r_face_float × 100`
- **SQL database field / logic**: cnt_r_face_float = SUM(HudCache.cnt_r_face_float); cnt_r_raise_float = SUM(HudCache.cnt_r_raise_float)
- **Tooltip**: % raising facing the river barrel, having called the turn bet in position
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_action_enum_hud_stats.py`

### Raise vs River 3-Bet — `raise_vs_river_3bet`

- **HUD abbreviation**: `RvR3B`
- **Description**: Percentage of the time that a player raised when facing a 3-bet on the river.
- **Formula**: Number of times the player raised a 3-bet on the river / Number of times the player faced a 3-bet on the river × 100
- **Formula (code)**: `cnt_r_raise_3bet / cnt_r_face_3bet × 100`
- **SQL database field / logic**: cnt_r_face_3bet = SUM(HudCache.cnt_r_face_3bet); cnt_r_raise_3bet = SUM(HudCache.cnt_r_raise_3bet)
- **Tooltip**: % raising facing a river 3-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs River 4-Bet — `raise_vs_river_4bet`

- **HUD abbreviation**: `RvR4B`
- **Description**: Percentage of the time that a player raised when facing a 4-bet on the river.
- **Formula**: Number of times the player raised a 4-bet on the river / Number of times the player faced a 4-bet on the river × 100
- **Formula (code)**: `cnt_r_raise_4bet / cnt_r_face_4bet × 100`
- **SQL database field / logic**: cnt_r_face_4bet = SUM(HudCache.cnt_r_face_4bet); cnt_r_raise_4bet = SUM(HudCache.cnt_r_raise_4bet)
- **Tooltip**: % raising facing a river 4-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs River C-Bet — `raise_vs_river_cbet`

- **HUD abbreviation**: `RvRCB`
- **Description**: Percentage of the time that a player raised when facing a continuation bet on the river.
- **Formula**: Number of times the player raised a continuation bet on the river / Number of times the player faced a continuation bet on the river × 100
- **Formula (code)**: `cnt_r_raise_cbet / cnt_r_face_cbet × 100`
- **SQL database field / logic**: cnt_r_face_cbet = SUM(HudCache.cnt_r_face_cbet); cnt_r_raise_cbet = SUM(HudCache.cnt_r_raise_cbet)
- **Tooltip**: % raising facing a river c-bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Raise vs River Donk Bet — `raise_vs_river_donk`

- **HUD abbreviation**: `RvRDk`
- **Description**: Percentage of the time that a player raised when facing a donk bet (a bet into the preflop raiser) on the river.
- **Formula**: Number of times the player raised a donk bet (a bet into the preflop raiser) on the river / Number of times the player faced a donk bet (a bet into the preflop raiser) on the river × 100
- **Formula (code)**: `cnt_r_raise_donk / cnt_r_face_donk × 100`
- **SQL database field / logic**: cnt_r_face_donk = SUM(HudCache.cnt_r_face_donk); cnt_r_raise_donk = SUM(HudCache.cnt_r_raise_donk)
- **Tooltip**: % raising facing a river donk bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### River Call Efficiency — `river_call_efficiency`

- **HUD abbreviation**: `RCE`
- **Description**: Showdowns won per call made on the river. It compares two different counts (showdowns won, river calls), so it can exceed 100%.
- **Formula**: Number of showdowns where the player won money (any share of a pot) / Number of calls made on the river (every call counts) × 100
- **Formula (code)**: `wmsd / call_3 × 100`
- **SQL database field / logic**: call_3 = SUM(HudCache.street3Calls); wmsd = SUM(HudCache.wonAtSD)
- **Tooltip**: River Call Efficiency
- **Detailed HUD text**: `RiverCallEff`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the third draw (triple draw)

### River 3-Bet — `three_B_river`

- **HUD abbreviation**: `R3B`
- **Description**: Percentage of the time that a player re-raised when facing a bet and a raise on the river.
- **Formula**: Number of river 3-bets (re-raise of a bet and a raise) / Number of times the player faced a bet and a raise on the river × 100
- **Formula (code)**: `rv3b / rv3b_opp × 100`
- **SQL database field / logic**: rv3b_opp = SUM(HudCache.street3_3BChance); rv3b = SUM(HudCache.street3_3BDone)
- **Tooltip**: % 3 bet river
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: yes, on 6th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_3bet_postflop.py`

## 7th street

### 7Th Street Aggression Frequency — `a_freq4`

- **HUD abbreviation**: `a4`
- **Description**: Percentage of the time that a player bet or raised at least once on the 7th street, given that they saw it.
- **Formula**: Number of hands where the player bet or raised on the 7th street / Number of hands where the player saw the 7th street × 100
- **Formula (code)**: `aggr_4 / saw_4 × 100`
- **SQL database field / logic**: saw_4 = SUM(HudCache.street4Seen); aggr_4 = SUM(HudCache.street4Aggr)
- **Tooltip**: Aggression frequency 7th street
- **Detailed HUD text**: `a_fq_4`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: yes, on 7th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### 7Th Street Continuation Bet — `cb4`

- **HUD abbreviation**: `cb4`
- **Description**: Percentage of the time that the last preflop raiser bet (or raised) on the 7th street when they had the chance.
- **Formula**: Number of continuation bets on the 7th street (the last preflop raiser bet or raised on the street) / Number of 7th street continuation-bet opportunities (the last preflop raiser, not folded yet) × 100
- **Formula (code)**: `cb_4 / cb_opp_4 × 100`
- **SQL database field / logic**: cb_opp_4 = SUM(HudCache.street4CBChance); cb_4 = SUM(HudCache.street4CBDone)
- **Tooltip**: % continuation bet 7th street
- **Detailed HUD text**: `cb_4`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: yes, on 7th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### 7Th Street Check-Raise — `cr4`

- **HUD abbreviation**: `cr4`
- **Description**: Percentage of the time that a player check-raised the 7th street, given that they checked and acted again on it.
- **Formula**: Number of check-raises on the 7th street / Number of times the player checked on the 7th street and acted again on that street × 100
- **Formula (code)**: `cr_4 / ccr_opp_4 × 100`
- **SQL database field / logic**: ccr_opp_4 = SUM(HudCache.street4CheckCallRaiseChance); cr_4 = SUM(HudCache.street4CheckRaiseDone)
- **Tooltip**: % check-raise 7th street
- **Detailed HUD text**: `cr_4`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Fold to 7Th Street Continuation Bet — `f_cb4`

- **HUD abbreviation**: `f_cb4`
- **Description**: Percentage of the time that a player folded when facing a 7th street continuation bet.
- **Formula**: Number of folds to a 7th street continuation bet / Number of times the player acted after a 7th street continuation bet × 100
- **Formula (code)**: `f_cb_4 / f_cb_opp_4 × 100`
- **SQL database field / logic**: f_cb_opp_4 = SUM(HudCache.foldToStreet4CBChance); f_cb_4 = SUM(HudCache.foldToStreet4CBDone)
- **Tooltip**: % fold to continuation bet 7th street
- **Detailed HUD text**: `f_cb_4`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: yes, on 7th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### 7Th Street Fold to Bet or Raise — `ffreq4`

- **HUD abbreviation**: `ff4`
- **Description**: Percentage of the time that a player folded on the 7th street after someone else bet or raised there.
- **Formula**: Number of times the player folded on the 7th street after someone else bet or raised / Number of times the player acted on the 7th street after someone else bet or raised × 100
- **Formula (code)**: `f_freq_4 / was_raised_4 × 100`
- **SQL database field / logic**: was_raised_4 = SUM(HudCache.otherRaisedStreet4); f_freq_4 = SUM(HudCache.foldToOtherRaisedStreet4)
- **Tooltip**: % fold frequency 7th street
- **Detailed HUD text**: `ff_4`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: yes, on 7th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

## Postflop, all streets

### Postflop Aggression Frequency — `a_freq_123`

- **HUD abbreviation**: `afq`
- **Description**: Percentage of the flops, turns and rivers a player saw on which they bet or raised at least once.
- **Formula**: (Number of hands where the player bet or raised on the flop plus Number of hands where the player bet or raised on the turn plus Number of hands where the player bet or raised on the river) / (Number of hands where the player saw the flop plus Number of hands where the player saw the turn plus Number of hands where the player saw the river) × 100
- **Formula (code)**: `(aggr_1 + aggr_2 + aggr_3) / (saw_1 + saw_2 + saw_3) × 100`
- **SQL database field / logic**: aggr_1 = SUM(HudCache.street1Aggr); aggr_2 = SUM(HudCache.street2Aggr); aggr_3 = SUM(HudCache.street3Aggr); saw_1 = SUM(HudCache.street1Seen); saw_2 = SUM(HudCache.street2Seen); saw_3 = SUM(HudCache.street3Seen)
- **Tooltip**: Post-flop aggression frequency
- **Detailed HUD text**: `post_a_fq`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **PT4 equivalent**: Total AFq — `((street1Bets + street1Raises + street2Bets + street2Raises + street3Bets + street3Raises) / (street1Calls + flg_f_fold + street2Calls + flg_t_fold + street3Calls + flg_r_fold + street1Bets + street1Raises + street2Bets + street2Raises + street3Bets + street3Raises)) * 100` (different formula)
- **PT4 difference**: PT4: flop-to-river bets and raises / (calls + folds + bets + raises), over actions. FPDB: streets with a bet or raise / streets seen, over hands.
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `PoFAFq`

### Aggression Factor — `agg_fact`

- **HUD abbreviation**: `afa`
- **Description**: Bets and raises divided by calls, over the flop, turn, river and 7th street. Higher means more aggressive. Each street counts once per hand for aggression but every call counts.
- **Formula**: (Number of hands with a bet or raise on the flop + turn + river + 7th street) / (Number of calls on the flop + turn + river + 7th street)
- **Formula (code)**: `(Σ aggr_1..4) / (Σ call_1..4); the numerator alone when there is no call`
- **SQL database field / logic**: aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4 (flop to 7th street)
- **Tooltip**: Aggression factor
- **Detailed HUD text**: `agg_fa`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **PT4 equivalent**: Total AF — `(street1Bets + street1Raises + street2Bets + street2Raises + street3Bets + street3Raises) / (street1Calls + street2Calls + street3Calls)` (different formula)
- **PT4 difference**: PT4 divides every flop, turn and river bet and raise by the calls on those streets. FPDB counts hands with at least one bet or raise on each street (one per street, however many raises) and adds 7th street, over every call.
- **XML titles**: `AggFac`
- **Note**: Postflop aggression factor, raw ratio.

### Aggression Percentage — `agg_fact_pct`

- **HUD abbreviation**: `afap`
- **Description**: Aggressive streets as a share of aggressive streets plus calls, over the flop to 7th street. A fraction between 0 and 1, not multiplied by 100.
- **Formula**: (Number of hands with a bet or raise on the flop to 7th street) / (that number + Number of calls on the flop to 7th street)
- **Formula (code)**: `(Σ aggr_1..4) / (Σ call_1..4 + Σ aggr_1..4)`
- **SQL database field / logic**: aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4
- **Tooltip**: Aggression factor pct
- **Detailed HUD text**: `agg_fa_pct`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Despite its name the result is a 0..1 fraction (aggression / (aggression + calls)), not multiplied by 100.

### Continuation Bet (all streets) — `cbet`

- **HUD abbreviation**: `cbet`
- **Description**: Percentage of the time that the last preflop raiser bet on a later street when they had the chance, pooled over the flop, turn, river and 7th street.
- **Formula**: (Number of continuation bets, flop to 7th street) / (Number of continuation-bet opportunities, flop to 7th street) × 100
- **Formula (code)**: `(Σ cb_1..4) / (Σ cb_opp_1..4) × 100`
- **SQL database field / logic**: cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 4
- **Tooltip**: % continuation bet
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **XML titles**: `ContBet`
- **Note**: Continuation bet across all four streets pooled; `cb1`..`cb4` give one street each.

### Check-Raise (postflop) — `check_raise_frequency`

- **HUD abbreviation**: `CRF`
- **Description**: Percentage of the time that a player check-raised, given that they checked and acted again on the street, pooled over the flop, turn and river.
- **Formula**: (Number of check-raises on the flop plus Number of check-raises on the turn plus Number of check-raises on the river) / (Number of times the player checked on the flop and acted again on that street plus Number of times the player checked on the turn and acted again on that street plus Number of times the player checked on the river and acted again on that street) × 100
- **Formula (code)**: `(cr_1 + cr_2 + cr_3) / (ccr_opp_1 + ccr_opp_2 + ccr_opp_3) × 100`
- **SQL database field / logic**: cr_1 = SUM(HudCache.street1CheckRaiseDone); cr_2 = SUM(HudCache.street2CheckRaiseDone); cr_3 = SUM(HudCache.street3CheckRaiseDone); ccr_opp_1 = SUM(HudCache.street1CheckCallRaiseChance); ccr_opp_2 = SUM(HudCache.street2CheckCallRaiseChance); ccr_opp_3 = SUM(HudCache.street3CheckCallRaiseChance)
- **Tooltip**: Check-Raise Frequency
- **Detailed HUD text**: `CheckRaiseFreq`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Fold to All-In — `fold_to_allin`

- **HUD abbreviation**: `FvAI`
- **Description**: Percentage of the time that a player folded the first time they faced an all-in bet or raise in a hand.
- **Formula**: Number of times the player folded to that all-in / Number of hands where the player faced an all-in bet or raise with a decision to make (first such spot only) × 100
- **Formula (code)**: `fold_allin / faced_allin × 100`
- **SQL database field / logic**: faced_allin = SUM(HudCache.flg_faced_allin); fold_allin = SUM(HudCache.flg_fold_to_allin)
- **Tooltip**: % fold to all-in
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **PT4 derivation tests**: `test_calc_faced_allin.py`

### Overbet Frequency (fixed) — `overbet_frequency`

- **HUD abbreviation**: `overbet`
- **Description**: Not measured: the stat shows a fixed 15% as soon as any bet exists. Kept so old layouts load.
- **Formula**: 15% (a constant)
- **Formula (code)**: `constant 15 %, shown once any bet has been seen (Σ street1..3Bets > 0)`
- **SQL database field / logic**: street1Bets, street2Bets, street3Bets = SUM(HudCache.streetNBets) (exposed by the HUD queries as bet_1..3)
- **Tooltip**: % overbet frequency
- **Detailed HUD text**: `overbet_freq`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Status**: estimate
- **Note**: Not measured. The function returns a fixed 15 % estimate; it is kept for old layouts.

### Triple Barrel (estimate) — `triple_barrel`

- **HUD abbreviation**: `3barrel`
- **Description**: An estimate of how often the preflop raiser bets flop, turn and river: the product of the three street c-bet rates. It does not follow the same hands through the three streets.
- **Formula**: (flop c-bets / flop c-bet chances) × (turn c-bets / turn c-bet chances) × (river c-bets / river c-bet chances) × 100
- **Formula (code)**: `min(cb_opp_1..3) × Π (cb_N / cb_opp_N) / min(cb_opp_1..3) × 100 = Π (cb_N / cb_opp_N) × 100`
- **SQL database field / logic**: cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 3
- **Tooltip**: % triple barrel
- **Detailed HUD text**: `triple_barrel`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: An estimate: the product of the three street c-bet rates, assuming the streets are independent. It does not follow the same hands through the three streets.

## Results and showdown

### Average Flop Investment — `amt_bet_f`

- **HUD abbreviation**: `BetF`
- **Description**: The average amount the player put in on the flop per hand played (all hands, not only flops seen).
- **Formula**: Sum of chips put in on the flop, in cents / Number of hands played × 0.01
- **Formula (code)**: `0.01 × amt_bet_f / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_f = SUM(HudCache.amt_bet_f)
- **Tooltip**: avg flop invested
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`

### Average Preflop Investment — `amt_bet_p`

- **HUD abbreviation**: `BetP`
- **Description**: The average amount the player put in preflop per hand, blinds included, in the table's currency.
- **Formula**: Sum of chips put in preflop, blinds included, in cents / Number of hands played × 0.01
- **Formula (code)**: `0.01 × amt_bet_p / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_p = SUM(HudCache.amt_bet_p)
- **Tooltip**: avg preflop invested
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes, preflop
- **Stud / Razz**: yes, on 3rd street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, before the first draw
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`

### Average River Investment — `amt_bet_r`

- **HUD abbreviation**: `BetR`
- **Description**: The average amount the player put in on the river per hand played.
- **Formula**: Sum of chips put in on the river, in cents / Number of hands played × 0.01
- **Formula (code)**: `0.01 × amt_bet_r / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_r = SUM(HudCache.amt_bet_r)
- **Tooltip**: avg river invested
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes, on the river
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`

### Average Turn Investment — `amt_bet_t`

- **HUD abbreviation**: `BetT`
- **Description**: The average amount the player put in on the turn per hand played.
- **Formula**: Sum of chips put in on the turn, in cents / Number of hands played × 0.01
- **Formula (code)**: `0.01 × amt_bet_t / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_t = SUM(HudCache.amt_bet_t)
- **Tooltip**: avg turn invested
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes, on the turn
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`

### Average Total Investment — `amt_bet_ttl`

- **HUD abbreviation**: `BetTtl`
- **Description**: The average amount the player put in over the whole hand, per hand played.
- **Formula**: Sum of chips put in over the whole hand, in cents / Number of hands played × 0.01
- **Formula (code)**: `0.01 × amt_bet_ttl / n`
- **SQL database field / logic**: n = SUM(HudCache.n); amt_bet_ttl = SUM(HudCache.amt_bet_ttl)
- **Tooltip**: avg total invested
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **PT4 derivation tests**: `test_calc_bet_sizing_extra.py`

### Big Bets per 100 Hands — `BBper100`

- **HUD abbreviation**: `BB100`
- **Description**: Big bets won per 100 hands, where a big bet is two big blinds (the limit-poker unit).
- **Formula**: Sum of profit in cents × 50 / Sum of big blinds in play (big blind × hands); a big bet is two big blinds
- **Formula (code)**: `50 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)
- **Tooltip**: Big bets won per 100 hands
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Big *bets* per 100 hands: the 50 factor counts a big bet as two big blinds. `bbper100` is the big-blind version.

### Big Blinds per 100 Hands — `bbper100`

- **HUD abbreviation**: `bb100`
- **Description**: Big blinds won per 100 hands.
- **Formula**: Sum of profit in cents × 100 / Sum of big blinds in play (big blind × hands)
- **Formula (code)**: `100 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)
- **Tooltip**: Big blinds won per 100 hands
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Big blinds won per 100 hands.

### Won Without Showdown — `non_sd_winrate`

- **HUD abbreviation**: `nsd_wr`
- **Description**: Percentage of flops seen that did not reach showdown and that the player still won: won-when-saw-flop hands minus showdown wins, over flops seen minus showdowns.
- **Formula**: (Number of hands where the player saw the flop and won money (any share of a pot, with or without showdown) minus Number of showdowns where the player won money (any share of a pot)) / (Number of hands where the player saw the flop minus Number of hands where the player went to showdown) × 100
- **Formula (code)**: `(w_w_s_1 − wmsd) / (saw_f − sd) × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); sd = SUM(HudCache.sawShowdown); w_w_s_1 = SUM(HudCache.wonWhenSeenStreet1); wmsd = SUM(HudCache.wonAtSD)
- **Tooltip**: % non-showdown winrate
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`

### Profit per Hand — `profit100`

- **HUD abbreviation**: `p`
- **Description**: The average profit per hand, in cents. The label says per 100 hands but the formula is per hand.
- **Formula**: Sum of profit in cents / Number of hands played
- **Formula (code)**: `net / n  (net in cents, so cents per hand, shown as per 100 hands in the label)`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); n = SUM(HudCache.n)
- **Tooltip**: Profit per 100 hands
- **Detailed HUD text**: `p/100`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: The label says per 100 hands but the formula is the average profit per hand, in cents. The HUD abbreviation `p` is shared with: `pfr`, `playerprofile`.

### Saw Flop — `saw_f`

- **HUD abbreviation**: `sf`
- **Description**: Percentage of hands where the player saw the flop (4th street in stud).
- **Formula**: Number of hands where the player saw the flop / Number of hands played × 100
- **Formula (code)**: `saw_f / n × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); n = SUM(HudCache.n)
- **Tooltip**: Flop/4th street seen %
- **Detailed HUD text**: `saw_f`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `Saw_F`

### Showdown Win Rate — `sd_winrate`

- **HUD abbreviation**: `sd_wr`
- **Description**: Percentage of showdowns where the player won money. Same counters as W$SD (`wmsd`).
- **Formula**: Number of showdowns where the player won money (any share of a pot) / Number of hands where the player went to showdown × 100
- **Formula (code)**: `wmsd / sd × 100`
- **SQL database field / logic**: sd = SUM(HudCache.sawShowdown); wmsd = SUM(HudCache.wonAtSD)
- **Tooltip**: % showdown winrate
- **Detailed HUD text**: `showdown_winrate`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Gives the same value as `wmsd` (same counters, same formula).

### Total Profit — `totalprofit`

- **HUD abbreviation**: `tp`
- **Description**: The player's total profit over the aggregated hands. It is always formatted as US dollars: the HUD query does not select the game's currency. In tournaments the amount is chips.
- **Formula**: Sum of profit in cents / 100, formatted as USD
- **Formula (code)**: `net / 100, formatted with the game's currency`
- **SQL database field / logic**: net = SUM(HudCache.totalProfit); currency is not selected by the HUD queries, so the USD default is used
- **Tooltip**: Total Profit
- **Detailed HUD text**: `tot_prof`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); amounts are tournament chips there, not money
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### Won Money at Showdown (W$SD) — `wmsd`

- **HUD abbreviation**: `w`
- **Description**: Percentage of showdowns where the player won money (any share of a pot).
- **Formula**: Number of showdowns where the player won money (any share of a pot) / Number of hands where the player went to showdown × 100
- **Formula (code)**: `wmsd / sd × 100`
- **SQL database field / logic**: sd = SUM(HudCache.sawShowdown); wmsd = SUM(HudCache.wonAtSD)
- **Tooltip**: % won some money at showdown
- **Detailed HUD text**: `wmsd`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **PT4 equivalent**: WSD — `(wonAtSD / sawShowdown) * 100` (same formula)
- **XML titles**: `W$SD`
- **Note**: Gives the same value as `sd_winrate` (same counters, same formula). The HUD abbreviation `w` is shared with: `wtsd`.

### Won When Saw Flop (WWSF / W$wsF) — `WMsF`

- **HUD abbreviation**: `wf`
- **Description**: Percentage of the time that a player won some money, in any fashion, given that they saw the flop: with or without a showdown, a split pot counts.
- **Formula**: Number of hands where the player saw the flop and won money (any share of a pot, with or without showdown) / Number of hands where the player saw the flop × 100
- **Formula (code)**: `w_w_s_1 / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); w_w_s_1 = SUM(HudCache.wonWhenSeenStreet1)
- **Tooltip**: % won money when seen flop/4th street
- **Detailed HUD text**: `w_w_f`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `W$wsF`
- **Note**: Gives the same value as `wwsf` (same counters, same formula). The HUD abbreviation `wf` is shared with: `wwsf`.

### Won money at showdown. — `wsd`

- **HUD abbreviation**: `W$SD`
- **Description**: Won money at showdown.
- **Formula (code)**: `100 * wonAtSD / sawShowdown   (aggregate: ratio)`
- **SQL database field / logic**: inputs (HudCache columns): wonAtSD, sawShowdown
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Went to Showdown (WTSD) — `wtsd`

- **HUD abbreviation**: `w`
- **Description**: Percentage of the time that a player went to showdown, given that they saw the flop.
- **Formula**: Number of hands where the player went to showdown / Number of hands where the player saw the flop × 100
- **Formula (code)**: `sd / saw_f × 100`
- **SQL database field / logic**: saw_f = SUM(HudCache.street1Seen); sd = SUM(HudCache.sawShowdown)
- **Tooltip**: % went to showdown when seen flop/4th street
- **Detailed HUD text**: `wtsd`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 equivalent**: WTSD — `(sawShowdown / street1Seen) * 100` (same formula)
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **XML titles**: `WtSDwsF`
- **Note**: The HUD abbreviation `w` is shared with: `wmsd`.

### Won When Saw Flop (WWSF) — `wwsf`

- **HUD abbreviation**: `wf`
- **Description**: Alias of `WMsF` under the name other trackers use. Percentage of the time that a player won some money, in any fashion, given that they saw the flop.
- **Formula**: Number of hands where the player saw the flop and won money (any share of a pot, with or without showdown) / Number of hands where the player saw the flop × 100
- **Formula (code)**: `w_w_s_1 / saw_1 × 100`
- **SQL database field / logic**: saw_1 = SUM(HudCache.street1Seen); w_w_s_1 = SUM(HudCache.wonWhenSeenStreet1)
- **Tooltip**: % won money when seen flop/4th street
- **Detailed HUD text**: `w_w_f`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes, on the flop
- **Stud / Razz**: yes, on 4th street
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes, after the first draw
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Note**: Alias: this stat calls `WMsF` and returns its value unchanged. The HUD abbreviation `wf` is shared with: `WMsF`.

## Tournament and stack

### Stack in Big Blinds — `bbstack`

- **HUD abbreviation**: `v`
- **Description**: The player's stack after the current hand, in big blinds of that hand. Not aggregated over the history.
- **Formula**: Stack after the current hand / big blind of that hand
- **Formula (code)**: `end stack of the player at the current hand / big blind of that hand`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Tooltip**: bb stack
- **Detailed HUD text**: `vpip`
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); computed in cash games too, where it means less
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Last-hand value, not aggregated over the history. The HUD abbreviation `v` is shared with: `vpip`.

### Bounty — `bounty`

- **HUD abbreviation**: `bounty`
- **Description**: The player's current bounty in a knockout tournament, after the last hand.
- **Formula (code)**: `the player's current bounty after the last hand`
- **SQL database field / logic**: not a HudCache aggregate: read from the hand being displayed (Hand object)
- **Tooltip**: bounty (last hand)
- **Games**: Knockout (bounty) tournaments
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Knockout tournaments only.

### Chips the player was expected to win at all-in, 3-handed in the big blind. — `chipev_3h_bb`

- **HUD abbreviation**: `ChipEV 3-handed BB`
- **Description**: Chips the player was expected to win at all-in, 3-handed in the big blind.
- **Formula (code)**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Chips the player was expected to win at all-in, 3-handed on the button. — `chipev_3h_btn`

- **HUD abbreviation**: `ChipEV 3-handed BTN`
- **Description**: Chips the player was expected to win at all-in, 3-handed on the button.
- **Formula (code)**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Chips the player was expected to win at all-in, 3-handed in the small blind. — `chipev_3h_sb`

- **HUD abbreviation**: `ChipEV 3-handed SB`
- **Description**: Chips the player was expected to win at all-in, 3-handed in the small blind.
- **Formula (code)**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Chips the player was expected to win at all-in, heads-up in the big blind. — `chipev_hu_bb`

- **HUD abbreviation**: `ChipEV heads-up BB`
- **Description**: Chips the player was expected to win at all-in, heads-up in the big blind.
- **Formula (code)**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Chips the player was expected to win at all-in, heads-up in the small blind (button). — `chipev_hu_sb`

- **HUD abbreviation**: `ChipEV heads-up SB`
- **Description**: Chips the player was expected to win at all-in, heads-up in the small blind (button).
- **Formula (code)**: `allInEV / 100.0   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Average all-in chip EV per tournament. — `chipev_tourney`

- **HUD abbreviation**: `ChipEV / tournament`
- **Description**: Average all-in chip EV per tournament.
- **Formula (code)**: `allInEV / 100.0 / cnt_tourneys   (aggregate: sum)`
- **SQL database field / logic**: inputs (HudCache columns): allInEV, cnt_tourneys
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.

### Covers — `covers`

- **HUD abbreviation**: `covers`
- **Description**: Who has the bigger stack after the last hand: you cover the player, the player covers you, or even.
- **Formula (code)**: `compares the player's end stack with the hero's: +1 you cover, −1 covers you, 0 even`
- **SQL database field / logic**: not a HudCache aggregate: read from the hand being displayed (Hand object)
- **Tooltip**: who covers whom (last hand)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes

### M Ratio — `m_ratio`

- **HUD abbreviation**: `M`
- **Description**: The player's stack after the current hand divided by the cost of one orbit (blinds and antes). Not aggregated over the history.
- **Formula**: Stack after the current hand / (antes + blinds of one orbit)
- **Formula (code)**: `end stack / (antes + blinds posted in the hand + small blind + big blind)`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Tooltip**: M ratio
- **Games**: Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both); computed in cash games too, where it means less
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Last-hand value, not aggregated over the history.

### Stack — `stack_amount`

- **HUD abbreviation**: `stack`
- **Description**: The player's stack after the last hand, in the table's currency.
- **Formula (code)**: `reconstructed stack of the player, in the table's currency`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Tooltip**: stack (last hand)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Last-hand value. The HUD abbreviation `stack` is shared with: `stack_native_bb`.

### Stack (bb) — `stack_bb`

- **HUD abbreviation**: `stack_bb`
- **Description**: The player's stack after the last hand, in big blinds.
- **Formula**: Stack after the last hand / big blind
- **Formula (code)**: `reconstructed stack / big blind`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Tooltip**: stack in bb (last hand)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Last-hand value.

### Stack and Stack (bb) — `stack_native_bb`

- **HUD abbreviation**: `stack`
- **Description**: The player's stack after the last hand, followed by the same stack in big blinds.
- **Formula**: Stack after the last hand, then stack / big blind
- **Formula (code)**: `reconstructed stack, followed by the stack / big blind`
- **SQL database field / logic**: not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)
- **Tooltip**: stack and bb stack (last hand)
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Last-hand value. The HUD abbreviation `stack` is shared with: `stack_amount`.

## All-in or Fold

### All-in (AoF) — `aof_allin`

- **HUD abbreviation**: `AI`
- **Description**: In All-in or Fold games, percentage of the time that a player went all-in on their single decision.
- **Formula**: Number of hands where the player voluntarily put money in the pot preflop (call, raise or complete; posting a blind does not count) / Number of hands where the player had the chance to put money in voluntarily (excludes walks and blinds folded or all-in without a decision) × 100
- **Formula (code)**: `vpip / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI)
- **Tooltip**: % all-in on the single All-in or Fold decision
- **Detailed HUD text**: `all-in`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_pt4_adapter.py`
- **Note**: Gives the same value as `vpip` (same counters, same formula).

### All-ins with at least thirteen straight outs — `aof_big_wrap13`

- **HUD abbreviation**: `W13+`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held at least thirteen straight outs on the flop.
- **Formula**: Number of observable all-ins with at least thirteen straight outs / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_big_wrap13 / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_big_wrap13 = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.straightOuts>=13 then 1 else 0 end)
- **Tooltip**: % of observable all-ins with at least thirteen straight outs
- **Detailed HUD text**: `big wrap 13+ 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Decision EV (bb) — `aof_decision_ev`

- **HUD abbreviation**: `EV`
- **Description**: The average modelled EV, in big blinds, of the player's all-in decisions, including the fold and call branches. Before rake until the room's rake schedule is verified.
- **Formula**: Sum of modelled decision EV in millionths of a big blind / Number of all-in decisions with a modelled EV (weak, strong or uncertain) × 1e-06
- **Formula (code)**: `1e-06 × aof_decision_ev_bb_ppm / aof_decision_ev`
- **SQL database field / logic**: aof_decision_ev = SUM(case when e.status in ('weak', 'strong', 'uncertain') then 1 else 0 end); aof_decision_ev_bb_ppm = SUM(case when e.status in ('weak', 'strong', 'uncertain') then e.evBbPpm else 0 end)
- **Tooltip**: average modeled decision EV in big blinds, including fold/call branches; pre-rake until the room supplies a verified rake schedule
- **Detailed HUD text**: `Decision EV`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with a flush — `aof_flush`

- **HUD abbreviation**: `Flush`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held a flush on the flop.
- **Formula**: Number of observable all-ins with a flush / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_flush / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_flush = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a flush' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as flush
- **Detailed HUD text**: `flush 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Fold (AoF) — `aof_fold`

- **HUD abbreviation**: `F`
- **Description**: In All-in or Fold games, percentage of the time that a player folded on their single decision.
- **Formula**: (Number of hands where the player had the chance to put money in voluntarily (excludes walks and blinds folded or all-in without a decision) minus Number of hands where the player voluntarily put money in the pot preflop (call, raise or complete; posting a blind does not count)) / Number of hands where the player had the chance to put money in voluntarily (excludes walks and blinds folded or all-in without a decision) × 100
- **Formula (code)**: `(vpip_opp − vpip) / vpip_opp × 100`
- **SQL database field / logic**: vpip_opp = SUM(HudCache.street0VPIChance); vpip = SUM(HudCache.street0VPI)
- **Tooltip**: % folded on the single All-in or Fold decision
- **Detailed HUD text**: `fold`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **PT4 derivation tests**: `test_pt4_adapter.py`

### All-ins with a full house — `aof_full_house`

- **HUD abbreviation**: `Full`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held a full house on the flop.
- **Formula**: Number of observable all-ins with a full house / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_full_house / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_full_house = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a full house' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as full house
- **Detailed HUD text**: `full house 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Equity vs Callers — `aof_known_equity`

- **HUD abbreviation**: `EqK`
- **Description**: The average flop equity of the player's all-ins against the actual callers, using only all-ins where every caller's cards were captured.
- **Formula**: Sum of flop equity against the actual callers in parts per million / Number of all-ins whose callers' cards were all captured × 1e-06
- **Formula (code)**: `1e-06 × aof_known_equity_ppm / aof_known`
- **SQL database field / logic**: aof_known = SUM(case when a.status='complete' then 1 else 0 end); aof_known_equity_ppm = SUM(case when a.status='complete' then a.equityPpm else 0 end)
- **Tooltip**: average flop equity against actual callers whose complete cards were captured
- **Detailed HUD text**: `known-card equity`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### EV vs Callers (bb) — `aof_known_ev`

- **HUD abbreviation**: `EVact`
- **Description**: The average EV, in big blinds, of the player's all-ins against the actual callers, using only fully known hands.
- **Formula**: Sum of EV against the actual callers in millionths of a big blind / Number of all-ins whose callers' cards were all captured × 1e-06
- **Formula (code)**: `1e-06 × aof_known_ev_bb_ppm / aof_known`
- **SQL database field / logic**: aof_known = SUM(case when a.status='complete' then 1 else 0 end); aof_known_ev_bb_ppm = SUM(case when a.status='complete' then a.evBbPpm else 0 end)
- **Tooltip**: average EV in BB conditional on the actual callers, using only fully known pockets
- **Detailed HUD text**: `EV vs actual callers`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with a made hand — `aof_made`

- **HUD abbreviation**: `Made`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held a made hand on the flop.
- **Formula**: Number of observable all-ins with a made hand / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_made / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_made = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand<>'no made hand' then 1 else 0 end)
- **Tooltip**: % of observable all-ins with a made hand
- **Detailed HUD text**: `made hand 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with the nut flush draw — `aof_nfd`

- **HUD abbreviation**: `NFD`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held the nut flush draw on the flop.
- **Formula**: Number of observable all-ins with the nut flush draw / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_nfd / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_nfd = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.flushDraw='nut flush draw' then 1 else 0 end)
- **Tooltip**: % of observable all-ins with the nut flush draw
- **Detailed HUD text**: `nut flush draw 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with no made hand — `aof_no_made`

- **HUD abbreviation**: `NoMade`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held no made hand on the flop.
- **Formula**: Number of observable all-ins with no made hand / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_no_made / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_no_made = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='no made hand' then 1 else 0 end)
- **Tooltip**: % of observable all-ins with no made hand
- **Detailed HUD text**: `no made hand 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with a non-nut flush draw — `aof_non_nfd`

- **HUD abbreviation**: `nonNFD`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held a non-nut flush draw on the flop.
- **Formula**: Number of observable all-ins with a non-nut flush draw / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_non_nfd / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_non_nfd = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.flushDraw='non-nut flush draw' then 1 else 0 end)
- **Tooltip**: % of observable all-ins with a non-nut flush draw
- **Detailed HUD text**: `non-nut flush draw 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Observed All-ins — `aof_observed`

- **HUD abbreviation**: `Obs`
- **Description**: The number of the player's all-ins whose hole cards and flop were captured, the sample the hand-class stats use.
- **Formula**: Number of observable all-ins (decision all-in, hole cards and flop captured)
- **Formula (code)**: `aof_obs (a count)`
- **SQL database field / logic**: aof_obs = count of all-or-fold decisions with decision = 'allin' and cardsObservable (sql_queries_aof.py)
- **Tooltip**: all-ins with complete hole cards and flop captured
- **Detailed HUD text**: `observed all-ins`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with one pair — `aof_pair`

- **HUD abbreviation**: `Pair`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held one pair on the flop.
- **Formula**: Number of observable all-ins with one pair / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_pair / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_pair = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a pair' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as pair
- **Detailed HUD text**: `pair 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with quads — `aof_quads`

- **HUD abbreviation**: `Quads`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held quads on the flop.
- **Formula**: Number of observable all-ins with quads / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_quads / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_quads = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='quads' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as quads
- **Detailed HUD text**: `quads 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Equity vs Range — `aof_range_equity`

- **HUD abbreviation**: `EqR`
- **Description**: The average flop equity of the player's all-ins against the population range for the room, game and role. Biased toward showdown hands and trained only on earlier hands.
- **Formula**: Sum of flop equity against the population range in parts per million / Number of all-ins with a population-range equity × 1e-06
- **Formula (code)**: `1e-06 × aof_range_equity_ppm / aof_range`
- **SQL database field / logic**: aof_range = SUM(case when r.status='complete' then 1 else 0 end); aof_range_equity_ppm = SUM(case when r.status='complete' then r.equityPpm else 0 end)
- **Tooltip**: average flop equity against the room/game/role population range; showdown-biased and trained only on earlier hands
- **Detailed HUD text**: `population-range equity`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Showdowns (AoF) — `aof_showdowns`

- **HUD abbreviation**: `SD`
- **Description**: The number of the player's hands that reached showdown. Reaching showdown does not mean the cards were captured.
- **Formula**: Number of hands where the player went to showdown
- **Formula (code)**: `sd (a count, with n as the sample)`
- **SQL database field / logic**: sd = SUM(HudCache.sawShowdown); n = SUM(HudCache.n)
- **Tooltip**: hands of this player that reached showdown
- **Detailed HUD text**: `showdowns`
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: yes
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
- **Note**: Hands that reached showdown, not hands whose cards were captured.

### Splash Share — `aof_splash_freq`

- **HUD abbreviation**: `Spl%`
- **Description**: Percentage of splash-pot hands where the player took a share of the splash.
- **Formula**: Number of splash-pot hands where the player took a share of the splash / Number of splash-pot hands played × 100
- **Formula (code)**: `aof_splash_hit / aof_splash_seen × 100`
- **SQL database field / logic**: aof_splash_seen = SUM(case when h.splashPot>0 then 1 else 0 end); aof_splash_hit = SUM(case when hp.splashWinnings>0 then 1 else 0 end)
- **Tooltip**: % of splash hands where the player took a share
- **Detailed HUD text**: `splash taken`
- **Games**: Cash tables of rooms that add splash pots
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Splash Collected — `aof_splash_won`

- **HUD abbreviation**: `Spl`
- **Description**: The money the player collected from splash pots (money the room adds from outside the pot), in the table's currency. Add it to profit to read the player's real take.
- **Formula**: Sum of splash money collected, in cents / 100
- **Formula (code)**: `aof_splash_cents / 100`
- **SQL database field / logic**: aof_splash_cents, aof_splash_seen and aof_splash_hit from sql_queries_aof.py (splash pot winnings)
- **Tooltip**: amount collected from splash pots
- **Detailed HUD text**: `splash collected`
- **Games**: Cash tables of rooms that add splash pots
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: Money the room adds to the pot from outside; read it together with profit.

### All-ins with a straight — `aof_straight`

- **HUD abbreviation**: `Str`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held a straight on the flop.
- **Formula**: Number of observable all-ins with a straight / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_straight / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_straight = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a straight' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as straight
- **Detailed HUD text**: `straight 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)
- **Note**: The HUD abbreviation `Str` is shared with: `straddle`.

### All-ins with a straight flush — `aof_straight_flush`

- **HUD abbreviation**: `SF`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held a straight flush on the flop.
- **Formula**: Number of observable all-ins with a straight flush / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_straight_flush / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_straight_flush = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='a straight flush' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as straight flush
- **Detailed HUD text**: `straight flush 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-in Profile — `aof_summary`

- **HUD abbreviation**: `Shows NFD×1 W13×1 W9×1 fd×1`
- **Description**: What the player shows up with over their observed all-ins, for example NFD×10 W9×8 air×4, most telling first, with the sample size.
- **Formula (code)**: `the markers seen over the observed all-ins, for example NFD×10 W9×8 air×4`
- **SQL database field / logic**: aof_obs and one counter per marker (aof_nfd, aof_wrap9, aof_pair…) from sql_queries_aof.py
- **Tooltip**: what this player shows up with, over observed all-ins
- **Detailed HUD text**: `NFD×1 W13×1 W9×1 fd×1 3k×1 2p×1 1p×1 air×1 over 1 observed all-ins`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with trips — `aof_trips`

- **HUD abbreviation**: `Trips`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held trips on the flop.
- **Formula**: Number of observable all-ins with trips / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_trips / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_trips = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='trips' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as trips
- **Detailed HUD text**: `trips 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with two pair — `aof_two_pair`

- **HUD abbreviation**: `2P`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held two pair on the flop.
- **Formula**: Number of observable all-ins with two pair / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_two_pair / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_two_pair = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.madeHand='two pair' then 1 else 0 end)
- **Tooltip**: % of observable all-ins classified as two pair
- **Detailed HUD text**: `two pair 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### Weak All-ins — `aof_weak`

- **HUD abbreviation**: `W`
- **Description**: Percentage of modelled all-in decisions whose EV is negative even at the upper 95% confidence bound. Uncertain and unmodelled decisions are not counted as weak.
- **Formula**: Number of all-ins whose modelled EV is negative even at the upper 95% bound / Number of all-in decisions with a modelled EV (weak, strong or uncertain) × 100
- **Formula (code)**: `aof_weak / aof_decision_ev × 100`
- **SQL database field / logic**: aof_decision_ev = SUM(case when e.status in ('weak', 'strong', 'uncertain') then 1 else 0 end); aof_weak = SUM(case when e.status='weak' then 1 else 0 end)
- **Tooltip**: all-ins whose modeled pre-rake EV is negative even at the upper 95% confidence bound; uncertain and unmodeled decisions are not counted as weak
- **Detailed HUD text**: `Weak AI`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

### All-ins with at least nine straight outs — `aof_wrap9`

- **HUD abbreviation**: `W9+`
- **Description**: Percentage of the player's observable all-ins (hole cards and flop captured) where they held at least nine straight outs on the flop.
- **Formula**: Number of observable all-ins with at least nine straight outs / Number of observable all-ins (decision all-in, hole cards and flop captured) × 100
- **Formula (code)**: `aof_wrap9 / aof_obs × 100`
- **SQL database field / logic**: aof_obs = SUM(case when d.decision='allin' and d.cardsObservable=TRUE then 1 else 0 end); aof_wrap9 = SUM(case when d.decision='allin' and d.cardsObservable=TRUE and d.straightOuts>=9 then 1 else 0 end)
- **Tooltip**: % of observable all-ins with at least nine straight outs
- **Detailed HUD text**: `wrap 9+ 1/1 100.0%`
- **Games**: All-in or Fold cash tables (AoF Hold'em and AoF Omaha)
- **Hold'em / Omaha (flop games)**: yes
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: no data (its columns stay empty on all 179 Draw test hands)

## Other

### Counts explicit stand-pat and discard decisions for every draw round present in the hand history. Zero means stand pat; unknown discard counts remain in an unknown group. — `draw_decision_distribution`

- **HUD abbreviation**: `Draw decisions by round and cards drawn`
- **Description**: Counts explicit stand-pat and discard decisions for every draw round present in the hand history. Zero means stand pat; unknown discard counts remain in an unknown group.
- **Formula (code)**: `metric opportunities over the decisions matching the filters`
- **SQL database field / logic**: analytics engine over the action events (analytics_query): filters {'game_base': ['draw'], 'action_taken': ['discards', 'stands pat']}; grouped by draw_number, cards_drawn
- **Games**: Cash games; Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)
- **Hold'em / Omaha (flop games)**: no data (its columns stay empty on all 3081 Hold'em / Omaha test hands)
- **Stud / Razz**: no data (its columns stay empty on all 166 Stud / Razz test hands)
- **Draw (2-7, A-5, Badugi, 5-card draw...)**: yes
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
