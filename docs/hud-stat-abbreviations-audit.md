# Audit des statistiques et abréviations HUD

Relevé produit depuis le code de `fpdb_3_legacy/Stats.py` en appelant chaque nom avec un dictionnaire vide. La colonne « Abréviation HUD » est le préfixe exact de la troisième valeur renvoyée par `Stats.do_stat` (avant `=NA`, `=0`, etc.). La colonne « Texte détaillé HUD » est la quatrième valeur renvoyée (nom affiché avec sa valeur); la description fournie au tooltip est la sixième valeur. Le texte peut être remplacé par le titre d’une colonne dans les anciens layouts XML.

- **274 stats natives** dont la fonction renvoie un tuple HUD complet.
- **110 entrées** dans le choix de la fenêtre « Add/Edit Statistic », **108 noms uniques**.
- Entrées répétées dans ce choix : wmsd, wtsd.
- Le sélecteur n’est pas construit depuis le registre : il contient des identifiants absents de `Stats.STATLIST` et du registre descriptif, et omet beaucoup de fonctions natives.

## Stats natives exécutables par le HUD

| Nom accepté par le code | Abréviation HUD renvoyée | Texte détaillé HUD | Description / tooltip |
| --- | --- | --- | --- |
| `BBper100` | `BB100` | BB100=NA | Big bets won per 100 hands |
| `WMsF` | `wf` | w_w_f=NA | % won money when seen flop/4th street |
| `a_freq1` | `a1` | a_fq_1=NA | Aggression frequency flop/4th street |
| `a_freq2` | `a2` | a_fq_2=NA | Aggression frequency turn/5th street |
| `a_freq3` | `a3` | a_fq_3=NA | Aggression frequency river/6th street |
| `a_freq4` | `a4` | a_fq_4=NA | Aggression frequency 7th street |
| `a_freq_123` | `afq` | post_a_fq=NA | Post-flop aggression frequency |
| `agg_fact` | `afa` | agg_fa=NA | Aggression factor |
| `agg_fact_pct` | `afap` | agg_fa_pct=NA | Aggression factor pct |
| `amt_bet_f` | `BetF` | BetF=- | avg flop invested |
| `amt_bet_p` | `BetP` | BetP=- | avg preflop invested |
| `amt_bet_r` | `BetR` | BetR=- | avg river invested |
| `amt_bet_t` | `BetT` | BetT=- | avg turn invested |
| `amt_bet_ttl` | `BetTtl` | BetTtl=- | avg total invested |
| `amt_blind` | `Blind` | Blind=- | avg blinds posted |
| `aof_allin` | `AI` | AI=- | % all-in on the single All-in or Fold decision |
| `aof_big_wrap13` | `W13+` | W13+=- | % of observable all-ins with at least thirteen straight outs |
| `aof_decision_ev` | `EV` | EV=- | average modeled decision EV in big blinds, including fold/call branches; pre-rake until the room supplies a verified rake schedule |
| `aof_flush` | `Flush` | Flush=- | % of observable all-ins classified as flush |
| `aof_fold` | `F` | F=- | % folded on the single All-in or Fold decision |
| `aof_full_house` | `Full` | Full=- | % of observable all-ins classified as full house |
| `aof_known_equity` | `EqK` | EqK=- | average flop equity against actual callers whose complete cards were captured |
| `aof_known_ev` | `EVact` | EVact=- | average EV in BB conditional on the actual callers, using only fully known pockets |
| `aof_made` | `Made` | Made=- | % of observable all-ins with a made hand |
| `aof_nfd` | `NFD` | NFD=- | % of observable all-ins with the nut flush draw |
| `aof_no_made` | `NoMade` | NoMade=- | % of observable all-ins with no made hand |
| `aof_non_nfd` | `nonNFD` | nonNFD=- | % of observable all-ins with a non-nut flush draw |
| `aof_observed` | `Obs` | Obs=- | all-ins with complete hole cards and flop captured |
| `aof_pair` | `Pair` | Pair=- | % of observable all-ins classified as pair |
| `aof_quads` | `Quads` | Quads=- | % of observable all-ins classified as quads |
| `aof_range_equity` | `EqR` | EqR=- | average flop equity against the room/game/role population range; showdown-biased and trained only on earlier hands |
| `aof_showdowns` | `SD` | SD=- | hands of this player that reached showdown |
| `aof_splash_freq` | `Spl%` | Spl%=- | % of splash hands where the player took a share |
| `aof_splash_won` | `Spl` | Spl=- | amount collected from splash pots |
| `aof_straight` | `Str` | Str=- | % of observable all-ins classified as straight |
| `aof_straight_flush` | `SF` | SF=- | % of observable all-ins classified as straight flush |
| `aof_summary` | `Shows` | Shows=- | what this player shows up with, over observed all-ins |
| `aof_trips` | `Trips` | Trips=- | % of observable all-ins classified as trips |
| `aof_two_pair` | `2P` | 2P=- | % of observable all-ins classified as two pair |
| `aof_weak` | `W` | W=- | all-ins whose modeled pre-rake EV is negative even at the upper 95% confidence bound; uncertain and unmodeled decisions are not counted as weak |
| `aof_wrap9` | `W9+` | W9+=- | % of observable all-ins with at least nine straight outs |
| `avg_bet_size_flop` | `avg_bet_f` | avg_bet_f=- | avg bet size flop (deprecated) |
| `avg_bet_size_river` | `avg_bet_r` | avg_bet_r=- | avg bet size river (deprecated) |
| `avg_bet_size_turn` | `avg_bet_t` | avg_bet_t=- | avg bet size turn (deprecated) |
| `bbper100` | `bb100` | bb100=NA | Big blinds won per 100 hands |
| `bbstack` | `v` | vpip=NA | bb stack |
| `bet_frequency_flop` | `bet_f` | bet_f=- | % bet frequency flop |
| `bet_frequency_turn` | `bet_t` | bet_t=- | % bet frequency turn |
| `bounty` | `bounty` | bounty=- | bounty (last hand) |
| `call_float_river` | `CvRFl` | CvRFl=NA | % calling facing the river barrel, having called the turn bet in position |
| `call_float_turn` | `CvTFl` | CvTFl=NA | % calling facing the turn barrel, having called the flop c-bet in position |
| `call_vs_flop_3bet` | `CvF3B` | CvF3B=NA | % calling facing a flop 3-bet |
| `call_vs_flop_4bet` | `CvF4B` | CvF4B=NA | % calling facing a flop 4-bet |
| `call_vs_flop_cbet` | `CvFCB` | CvFCB=NA | % calling facing a flop c-bet |
| `call_vs_flop_donk` | `CvFDk` | CvFDk=NA | % calling facing a flop donk bet |
| `call_vs_preflop_3bet` | `Cv3B` | Cv3B=NA | % calling facing a preflop 3-bet |
| `call_vs_preflop_4bet` | `Cv4B` | Cv4B=NA | % calling facing a preflop 4-bet |
| `call_vs_preflop_squeeze` | `CvSQ` | CvSQ=NA | % calling facing a preflop squeeze |
| `call_vs_river_3bet` | `CvR3B` | CvR3B=NA | % calling facing a river 3-bet |
| `call_vs_river_4bet` | `CvR4B` | CvR4B=NA | % calling facing a river 4-bet |
| `call_vs_river_cbet` | `CvRCB` | CvRCB=NA | % calling facing a river c-bet |
| `call_vs_river_donk` | `CvRDk` | CvRDk=NA | % calling facing a river donk bet |
| `call_vs_steal` | `cvs` | cvs=- | % call vs steal (deprecated) |
| `call_vs_turn_3bet` | `CvT3B` | CvT3B=NA | % calling facing a turn 3-bet |
| `call_vs_turn_4bet` | `CvT4B` | CvT4B=NA | % calling facing a turn 4-bet |
| `call_vs_turn_cbet` | `CvTCB` | CvTCB=NA | % calling facing a turn c-bet |
| `call_vs_turn_donk` | `CvTDk` | CvTDk=NA | % calling facing a turn donk bet |
| `car0` | `CAR0` | CAR_pf=NA | % called a raise preflop |
| `cb1` | `cb1` | cb1=- | % continuation bet flop/4th street |
| `cb2` | `cb2` | cb2=- | % continuation bet turn/5th street |
| `cb3` | `cb3` | cb3=- | % continuation bet river/6th street |
| `cb4` | `cb4` | cb4=- | % continuation bet 7th street |
| `cb_ip` | `cb_ip` | cb_ip=- | % c-bet in position |
| `cb_oop` | `cb_oop` | cb_oop=- | % c-bet out of position |
| `cbet` | `cbet` | cbet=NA | % continuation bet |
| `cfour_B` | `C4B` | C4B_pf=NA | % cold 4 bet preflop/3rd street |
| `check_raise_frequency` | `CRF` | CheckRaiseFreq=NA | Check-Raise Frequency |
| `cold_call` | `cc` | cc=- | % cold call preflop |
| `covers` | `covers` | covers=- | who covers whom (last hand) |
| `cr1` | `cr1` | cr_1=NA | % check-raise flop/4th street |
| `cr2` | `cr2` | cr_2=NA | % check-raise turn/5th street |
| `cr3` | `cr3` | cr_3=NA | % check-raise river/6th street |
| `cr4` | `cr4` | cr_4=NA | % check-raise 7th street |
| `ctb` | `ctb` | ctb=NA | % call 3 bet |
| `dbr1` | `dbr1` | dbr1=- | % DonkBetAndRaise flop/4th street |
| `dbr2` | `dbr2` | dbr2=- | % DonkBetAndRaise turn/5th street |
| `dbr3` | `dbr3` | dbr3=NA | % DonkBetAndRaise river/6th street |
| `f_2bet_facing` | `F2vs` | F2vs=- | avg flop 2bet faced (% pot) |
| `f_3bet` | `F3B` | F3B_pf=NA | % fold to 3 bet preflop/3rd street |
| `f_3bet_facing` | `F3vs` | F3vs=- | avg flop 3bet faced (% pot) |
| `f_4bet` | `F4B` | F4B_pf=NA | % fold to 4 bet preflop/3rd street |
| `f_4bet_facing` | `F4vs` | F4vs=- | avg flop 4bet faced (% pot) |
| `f_BB_steal` | `fBB` | fBB_s=NA | % folded BB to steal |
| `f_SB_steal` | `fSB` | fSB_s=NA | % folded SB to steal |
| `f_bet_facing` | `FBvs` | FBvs=- | avg flop bet faced (% pot) |
| `f_bet_made` | `FBet` | FBet=- | avg flop bet made (% pot) |
| `f_cb1` | `f_cb1` | f_cb_1=NA | % fold to continuation bet flop/4th street |
| `f_cb2` | `f_cb2` | f_cb_2=NA | % fold to continuation bet turn/5th street |
| `f_cb3` | `f_cb3` | f_cb_3=NA | % fold to continuation bet river/6th street |
| `f_cb4` | `f_cb4` | f_cb_4=NA | % fold to continuation bet 7th street |
| `f_dbr1` | `f_dbr1` | f_dbr1=NA | % Fold DonkBetAndRaise flop/4th street |
| `f_dbr2` | `f_dbr2` | f_dbr2=NA | % Fold DonkBetAndRaise turn |
| `f_dbr3` | `f_dbr3` | f_dbr3=NA | % Fold DonkBetAndRaise river |
| `f_raise_facing` | `FRvs` | FRvs=- | avg flop raise faced (% pot) |
| `f_raise_made` | `FRz` | FRz=- | avg flop raise made (% pot) |
| `f_raise_made_2` | `FRz` | FRz=- | avg flop raise made (% pot) |
| `f_spr` | `fSPR` | fSPR=- | avg flop SPR |
| `f_steal` | `fB` | fB_s=NA | % folded blind to steal |
| `face_limpers` | `FLmp` | FLmp=- | avg limpers faced preflop |
| `face_raise_flop` | `FvRf` | FvRf=NA | % face raise flop |
| `face_raise_preflop` | `FvRp` | FvRp=NA | % face raise preflop |
| `face_raise_river` | `FvRr` | FvRr=NA | % face raise river |
| `face_raise_turn` | `FvRt` | FvRt=NA | % face raise turn |
| `fbr` | `fbr` | fbr=NA | 4 bet range |
| `ffreq1` | `ff1` | ff_1=NA | % fold frequency flop/4th street |
| `ffreq2` | `ff2` | ff_2=NA | % fold frequency turn/5th street |
| `ffreq3` | `ff3` | ff_3=NA | % fold frequency river/6th street |
| `ffreq4` | `ff4` | ff_4=NA | % fold frequency 7th street |
| `first_raise_flop` | `1Rf` | 1Rf=NA | % first raise flop |
| `first_raise_river` | `1Rr` | 1Rr=NA | % first raise river |
| `first_raise_turn` | `1Rt` | 1Rt=NA | % first raise turn |
| `float_bet` | `float` | float=- | % float bet turn |
| `float_river` | `FltR` | FltR=NA | % float river |
| `float_turn` | `FltT` | FltT=NA | % float turn |
| `fold_float_river` | `FvRFl` | FvRFl=NA | % folding facing the river barrel, having called the turn bet in position |
| `fold_float_turn` | `FvTFl` | FvTFl=NA | % folding facing the turn barrel, having called the flop c-bet in position |
| `fold_flop` | `Fldf` | Fldf=NA | % fold flop |
| `fold_river` | `Fldr` | Fldr=NA | % fold river |
| `fold_to_allin` | `FvAI` | FvAI=NA | % fold to all-in |
| `fold_to_cbet_flop` | `f_cb1` | f_cb_1=NA | % fold to continuation bet flop/4th street |
| `fold_to_cbet_river` | `f_cb3` | f_cb_3=NA | % fold to continuation bet river/6th street |
| `fold_to_cbet_turn` | `f_cb2` | f_cb_2=NA | % fold to continuation bet turn/5th street |
| `fold_to_squeeze` | `FvSq` | FvSq=NA | % fold to squeeze |
| `fold_to_three_B_flop` | `FF3B` | FF3B=NA | % fold to flop 3bet |
| `fold_to_three_B_river` | `FR3B` | FR3B=NA | % fold to river 3bet |
| `fold_to_three_B_turn` | `FT3B` | FT3B=NA | % fold to turn 3bet |
| `fold_turn` | `Fldt` | Fldt=NA | % fold turn |
| `fold_vs_4bet` | `f4b` | f4b=- | % fold vs 4bet |
| `fold_vs_flop_3bet` | `FvF3B` | FvF3B=NA | % folding facing a flop 3-bet |
| `fold_vs_flop_4bet` | `FvF4B` | FvF4B=NA | % folding facing a flop 4-bet |
| `fold_vs_flop_cbet` | `FvFCB` | FvFCB=NA | % folding facing a flop c-bet |
| `fold_vs_flop_donk` | `FvFDk` | FvFDk=NA | % folding facing a flop donk bet |
| `fold_vs_preflop_3bet` | `Fv3B` | Fv3B=NA | % folding facing a preflop 3-bet |
| `fold_vs_preflop_4bet` | `Fv4B` | Fv4B=NA | % folding facing a preflop 4-bet |
| `fold_vs_preflop_squeeze` | `FvSQ` | FvSQ=NA | % folding facing a preflop squeeze |
| `fold_vs_river_3bet` | `FvR3B` | FvR3B=NA | % folding facing a river 3-bet |
| `fold_vs_river_4bet` | `FvR4B` | FvR4B=NA | % folding facing a river 4-bet |
| `fold_vs_river_cbet` | `FvRCB` | FvRCB=NA | % folding facing a river c-bet |
| `fold_vs_river_donk` | `FvRDk` | FvRDk=NA | % folding facing a river donk bet |
| `fold_vs_turn_3bet` | `FvT3B` | FvT3B=NA | % folding facing a turn 3-bet |
| `fold_vs_turn_4bet` | `FvT4B` | FvT4B=NA | % folding facing a turn 4-bet |
| `fold_vs_turn_cbet` | `FvTCB` | FvTCB=NA | % folding facing a turn c-bet |
| `fold_vs_turn_donk` | `FvTDk` | FvTDk=NA | % folding facing a turn donk bet |
| `four_B` | `4B` | 4B=NA | % 4 bet preflop/3rd street |
| `four_B_flop` | `F4B` | F4B=NA | % 4 bet flop |
| `four_B_river` | `R4B` | R4B=NA | % 4 bet river |
| `four_B_turn` | `T4B` | T4B=NA | % 4 bet turn |
| `four_bet_bb` | `4B BB` | 4B BB=NA | % 4B BB preflop |
| `four_bet_btn` | `4B BTN` | 4B BTN=NA | % 4B BTN preflop |
| `four_bet_co` | `4B CO` | 4B CO=NA | % 4B CO preflop |
| `four_bet_ep` | `4B EP` | 4B EP=NA | % 4B EP preflop |
| `four_bet_mp` | `4B MP` | 4B MP=NA | % 4B MP preflop |
| `four_bet_range` | `4BR` | 4BR=NA | 4-bet range |
| `four_bet_sb` | `4B SB` | 4B SB=NA | % 4B SB preflop |
| `game_abbr` | `game` | game_abbr=NA | Game abbreviation |
| `gp_2x` | `2X` | 2X=NA | % open-raise (<40% stack) |
| `gp_limp` | `Limp` | Limp=NA | % open-limp |
| `gp_os` | `OS` | OS=NA | % open-shove (>=40% stack) |
| `iso` | `iso` | iso=- | % isolation raise (deprecated) |
| `limp` | `limp` | limp=- | % limp preflop |
| `m_ratio` | `M` | M=0 | M ratio |
| `n` | `n` | n=0 | Number of hands seen |
| `non_sd_winrate` | `nsd_wr` | nsd_wr=- | % non-showdown winrate |
| `open_flop` | `OPf` | OPf=NA | % open flop |
| `open_limp` | `open_limp` | open_limp=- | % open limp preflop |
| `open_river` | `OPr` | OPr=NA | % open river |
| `open_turn` | `OPt` | OPt=NA | % open turn |
| `overbet_frequency` | `overbet` | overbet=- | % overbet frequency |
| `p_2bet_facing` | `2Bvs` | 2Bvs=- | avg 2bet faced (% pot) |
| `p_3bet_facing` | `3Bvs` | 3Bvs=- | avg 3bet faced (% pot) |
| `p_4bet_facing` | `4Bvs` | 4Bvs=- | avg 4bet faced (% pot) |
| `p_5bet_facing` | `5Bvs` | 5Bvs=- | avg 5bet faced (% pot) |
| `p_raise_facing` | `PRvs` | PRvs=- | avg preflop raise faced (% pot) |
| `p_raise_made` | `PRz` | PRz=- | avg preflop raise made (% pot) |
| `p_raise_made_2` | `PRz` | PRz=- | avg preflop raise made (% pot) |
| `pfr` | `p` | pfr=NA | Preflop/3rd street raise % |
| `player_note` | `📝` | 📝 | Player note icon |
| `playername` | `` |  | Player name |
| `playerprofile` | `p` | playerprofile=unknown | Player Profile |
| `playershort` | `` |  | Player Name 1-5 |
| `probe_bet` | `probe` | probe=- | % probe bet flop |
| `probe_bet_river` | `probe_r` | probe_r=- | % probe bet river |
| `probe_bet_turn` | `probe_t` | probe_t=- | % probe bet turn |
| `profit100` | `p` | p/100=NA | Profit per 100 hands |
| `r_2bet_facing` | `R2vs` | R2vs=- | avg river 2bet faced (% pot) |
| `r_3bet_facing` | `R3vs` | R3vs=- | avg river 3bet faced (% pot) |
| `r_4bet_facing` | `R4vs` | R4vs=- | avg river 4bet faced (% pot) |
| `r_bet_facing` | `RBvs` | RBvs=- | avg river bet faced (% pot) |
| `r_bet_made` | `RBet` | RBet=- | avg river bet made (% pot) |
| `r_raise_facing` | `RRvs` | RRvs=- | avg river raise faced (% pot) |
| `r_raise_made` | `RRz` | RRz=- | avg river raise made (% pot) |
| `r_raise_made_2` | `RRz` | RRz=- | avg river raise made (% pot) |
| `r_spr` | `rSPR` | rSPR=- | avg river SPR |
| `raiseToSteal` | `RST` | RST_pf=NA | % raise to steal |
| `raise_float_river` | `RvRFl` | RvRFl=NA | % raising facing the river barrel, having called the turn bet in position |
| `raise_float_turn` | `RvTFl` | RvTFl=NA | % raising facing the turn barrel, having called the flop c-bet in position |
| `raise_frequency_flop` | `raise_f` | raise_f=- | % raise frequency flop |
| `raise_frequency_turn` | `raise_t` | raise_t=- | % raise frequency turn |
| `raise_vs_flop_3bet` | `RvF3B` | RvF3B=NA | % raising facing a flop 3-bet |
| `raise_vs_flop_4bet` | `RvF4B` | RvF4B=NA | % raising facing a flop 4-bet |
| `raise_vs_flop_cbet` | `RvFCB` | RvFCB=NA | % raising facing a flop c-bet |
| `raise_vs_flop_donk` | `RvFDk` | RvFDk=NA | % raising facing a flop donk bet |
| `raise_vs_preflop_3bet` | `Rv3B` | Rv3B=NA | % raising facing a preflop 3-bet |
| `raise_vs_preflop_4bet` | `Rv4B` | Rv4B=NA | % raising facing a preflop 4-bet |
| `raise_vs_preflop_squeeze` | `RvSQ` | RvSQ=NA | % raising facing a preflop squeeze |
| `raise_vs_river_3bet` | `RvR3B` | RvR3B=NA | % raising facing a river 3-bet |
| `raise_vs_river_4bet` | `RvR4B` | RvR4B=NA | % raising facing a river 4-bet |
| `raise_vs_river_cbet` | `RvRCB` | RvRCB=NA | % raising facing a river c-bet |
| `raise_vs_river_donk` | `RvRDk` | RvRDk=NA | % raising facing a river donk bet |
| `raise_vs_turn_3bet` | `RvT3B` | RvT3B=NA | % raising facing a turn 3-bet |
| `raise_vs_turn_4bet` | `RvT4B` | RvT4B=NA | % raising facing a turn 4-bet |
| `raise_vs_turn_cbet` | `RvTCB` | RvTCB=NA | % raising facing a turn c-bet |
| `raise_vs_turn_donk` | `RvTDk` | RvTDk=NA | % raising facing a turn donk bet |
| `resteal` | `resteal` | resteal=- | % resteal |
| `rfi_early_position` | `rfi_ep` | rfi_ep=- | % RFI early position |
| `rfi_late_position` | `rfi_lp` | rfi_lp=- | % RFI late position |
| `rfi_middle_position` | `rfi_mp` | rfi_mp=- | % RFI middle position |
| `rfi_total` | `rfi` | rfi=- | % raise first in |
| `river_call_efficiency` | `RCE` | RiverCallEff=NA | River Call Efficiency |
| `s_steal` | `s_st` | s_steal=NA | % steal success |
| `saw_f` | `sf` | saw_f=NA | Flop/4th street seen % |
| `sd_winrate` | `sd_wr` | sd_wr=- | % showdown winrate |
| `squeeze` | `SQZ` | SQZ_pf=NA | % squeeze preflop |
| `squeeze_bb` | `SQZ BB` | SQZ BB=NA | % SQZ BB preflop |
| `squeeze_btn` | `SQZ BTN` | SQZ BTN=NA | % SQZ BTN preflop |
| `squeeze_co` | `SQZ CO` | SQZ CO=NA | % SQZ CO preflop |
| `squeeze_ep` | `SQZ EP` | SQZ EP=NA | % SQZ EP preflop |
| `squeeze_mp` | `SQZ MP` | SQZ MP=NA | % SQZ MP preflop |
| `squeeze_range` | `SQZR` | SQZR=NA | squeeze range |
| `squeeze_sb` | `SQZ SB` | SQZ SB=NA | % SQZ SB preflop |
| `stack_amount` | `stack` | stack=- | stack (last hand) |
| `stack_bb` | `stack_bb` | stack_bb=- | stack in bb (last hand) |
| `stack_native_bb` | `stack` | stack=- | stack and bb stack (last hand) |
| `starthands` | `` |  | Hands seen at this table |
| `steal` | `st` | steal=NA | % steal attempted |
| `straddle` | `Str` | Str=NA | % straddle |
| `t_2bet_facing` | `T2vs` | T2vs=- | avg turn 2bet faced (% pot) |
| `t_3bet_facing` | `T3vs` | T3vs=- | avg turn 3bet faced (% pot) |
| `t_4bet_facing` | `T4vs` | T4vs=- | avg turn 4bet faced (% pot) |
| `t_bet_facing` | `TBvs` | TBvs=- | avg turn bet faced (% pot) |
| `t_bet_made` | `TBet` | TBet=- | avg turn bet made (% pot) |
| `t_raise_facing` | `TRvs` | TRvs=- | avg turn raise faced (% pot) |
| `t_raise_made` | `TRz` | TRz=- | avg turn raise made (% pot) |
| `t_raise_made_2` | `TRz` | TRz=- | avg turn raise made (% pot) |
| `t_spr` | `tSPR` | tSPR=- | avg turn SPR |
| `three_B` | `3B` | 3B_pf=NA | % 3 bet preflop/3rd street |
| `three_B_flop` | `F3B` | F3B=NA | % 3 bet flop |
| `three_B_river` | `R3B` | R3B=NA | % 3 bet river |
| `three_B_turn` | `T3B` | T3B=NA | % 3 bet turn |
| `three_bet_bb` | `3B BB` | 3B BB=NA | % 3B BB preflop |
| `three_bet_btn` | `3B BTN` | 3B BTN=NA | % 3B BTN preflop |
| `three_bet_co` | `3B CO` | 3B CO=NA | % 3B CO preflop |
| `three_bet_ep` | `3B EP` | 3B EP=NA | % 3B EP preflop |
| `three_bet_mp` | `3B MP` | 3B MP=NA | % 3B MP preflop |
| `three_bet_range` | `3BR` | 3BR=NA | 3-bet range |
| `three_bet_sb` | `3B SB` | 3B SB=NA | % 3B SB preflop |
| `three_bet_vs_steal` | `3bvs` | 3bvs=- | % 3bet vs steal (deprecated) |
| `totalprofit` | `tp` | totalprofit=0 | Total Profit |
| `triple_barrel` | `3barrel` | 3barrel=- | % triple barrel |
| `vpip` | `v` | vpip=NA | Voluntarily put in preflop/3rd street % |
| `vpip_pfr_ratio` | `v/p` | vpip/pfr=NA | VPIP/PFR ratio |
| `wmsd` | `w` | wmsd=NA | % won some money at showdown |
| `wtsd` | `w` | wtsd=NA | % went to showdown when seen flop/4th street |
| `wwsf` | `wf` | w_w_f=NA | % won money when seen flop/4th street |

## Définitions déclaratives (`stats.d`)

Ces définitions partagent le chemin HUD, mais ne déclarent pas de forme courte séparée : `HudAdapter.stat_tuple` utilise le nom technique comme texte de cellule (`nom=valeur`) et le `label` pour le libellé long.

| Nom | Label déclaré | Catégorie |
| --- | --- | --- |
| `cbet_flop` | C-bet Flop | Standard / Postflop |
| `cbet_turn` | C-bet Turn | Standard / Postflop |
| `chipev_3h_bb` | ChipEV 3-handed BB | Tournament / ChipEV |
| `chipev_3h_btn` | ChipEV 3-handed BTN | Tournament / ChipEV |
| `chipev_3h_sb` | ChipEV 3-handed SB | Tournament / ChipEV |
| `chipev_hu_bb` | ChipEV heads-up BB | Tournament / ChipEV |
| `chipev_hu_sb` | ChipEV heads-up SB | Tournament / ChipEV |
| `chipev_tourney` | ChipEV / tournament | Tournament / ChipEV |
| `delayed_cbet_turn` | Delayed C-bet Turn | Standard / Postflop |
| `float_river` | Float River | Standard / Postflop |
| `float_turn` | Float Turn | Standard / Postflop |
| `fold_bb_to_steal` | Fold BB to Steal | Standard / Preflop |
| `fold_to_cbet_flop` | Fold to C-bet Flop | Standard / Postflop |
| `fold_to_squeeze` | Fold to Squeeze | Standard / Preflop |
| `four_bet` | 4Bet | Standard / Preflop |
| `pfr` | PFR | Standard / Preflop |
| `probe_turn` | Probe Turn | Standard / Postflop |
| `rfi` | RFI | Standard / Preflop |
| `steal` | Steal | Standard / Preflop |
| `three_bet` | 3Bet | Standard / Preflop |
| `vpip` | VPIP | Standard / Preflop |
| `wsd` | W$SD | Standard / Showdown |
| `wtsd` | WTSD | Standard / Showdown |

## Lecture des deux captures

- `three_B_river` est un identifiant reconnu et renvoie `R3B`; `three_B_turn` et `three_B` suivent le même schéma de nommage par street. Le choix `3bet` visible dans la capture n’est pas un identifiant reconnu par `Stats.do_stat` (la définition déclarative disponible s’appelle `three_bet`).
- `turn_afq` n’est pas un identifiant reconnu; l’AFQ turn native est `a_freq2`, abrégée `a2` (et l’AFQ postflop combinée est `a_freq_123`, abrégée `afq`). `wmsd` et `WMsF` sont deux stats différentes : `wmsd` = argent gagné au showdown (abréviation native `w`); `WMsF` = argent gagné après avoir vu le flop (abréviation native `wf`). L’ancien exemple XML configure le titre `W$wsF` pour sa colonne `wmsf`; ce nom de colonne historique ne passe pas le dispatcher actuel `Stats.do_stat`, et ne doit pas être confondu avec `wmsd`.
- Les noms de stats et les abréviations ne sont pas centralisés. Les abréviations proviennent des tuples retournés par les fonctions, tandis que les titres du HUD historique peuvent aussi venir de `col_title` dans le layout XML.
- Les stat packs installés par un utilisateur peuvent ajouter des noms propres; ils ne sont pas énumérables depuis le catalogue livré dans le dépôt. Le registre livré compte les définitions listées ci-dessus.
