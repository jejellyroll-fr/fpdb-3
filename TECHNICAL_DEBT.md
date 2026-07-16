# Registre de dette technique

Ce fichier est généré par `python tools/todo_inventory.py`. Chaque marqueur
`TODO`, `FIXME` ou `HACK` du code possède ainsi un identifiant stable et une
catégorie. Modifier le code source, puis régénérer ce registre.

**Total : 46 tâches ouvertes.**

| Catégorie | Nombre |
|---|---:|
| database | 3 |
| parser | 40 |
| poker-domain | 3 |

## Tâches

| ID | Catégorie | Type | Emplacement | Description |
|---|---|---|---|---|
| `TD-F140803E` | database | FIXME | [fpdb_3_legacy/sql_queries_player_detailed.py:570](fpdb_3_legacy/sql_queries_player_detailed.py#L570) | 3/4bet and foldTo don't added four tournaments yet |
| `TD-C253D5A8` | database | FIXME | [fpdb_3_legacy/sql_queries_tournament_graph.py:34](fpdb_3_legacy/sql_queries_tournament_graph.py#L34) | this is a horrible hack to prevent nonsense data |
| `TD-F04EE9E8` | database | FIXME | [fpdb_3_legacy/sql_queries_tournament_graph.py:58](fpdb_3_legacy/sql_queries_tournament_graph.py#L58) | this is a horrible hack to prevent nonsense data |
| `TD-D14B2924` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:27](fpdb_3_legacy/AbsoluteToFpdb.py#L27) | I have no idea if AP has multi-currency options, i just copied the regex out of Everleaf converter for the currency symbols.. weeeeee - Eric |
| `TD-8999E04A` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:129](fpdb_3_legacy/AbsoluteToFpdb.py#L129) | that's not the right way to match for "dead" dealer is it? |
| `TD-C4001A69` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:152](fpdb_3_legacy/AbsoluteToFpdb.py#L152) | Absolute posting when coming in new: %s - Posts $0.02 .. should that be a new Post line? where do we need to add support for that? *confused* |
| `TD-E7B1E72B` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:261](fpdb_3_legacy/AbsoluteToFpdb.py#L261) | AP does provide Small BET for Limit .. I think? at least 1-on-1 limit they do.. sigh |
| `TD-CAD4A4C1` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:307](fpdb_3_legacy/AbsoluteToFpdb.py#L307) | 1-on-1) does have that info in the game type line |
| `TD-6DEBDDEA` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:321](fpdb_3_legacy/AbsoluteToFpdb.py#L321) | implement lookup list by table-name to determine maxes, |
| `TD-EB5B8ECA` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:338](fpdb_3_legacy/AbsoluteToFpdb.py#L338) | Not implemented yet |
| `TD-9EF696E5` | parser | TODO | [fpdb_3_legacy/AbsoluteToFpdb.py:484](fpdb_3_legacy/AbsoluteToFpdb.py#L484) | not supported yet ? |
| `TD-FA54F1A1` | parser | TODO | [fpdb_3_legacy/BetOnlineToFpdb.py:457](fpdb_3_legacy/BetOnlineToFpdb.py#L457) | fpdb): handle other currencies, play money |
| `TD-C53C12F4` | parser | TODO | [fpdb_3_legacy/BetOnlineToFpdb.py:770](fpdb_3_legacy/BetOnlineToFpdb.py#L770) | fpdb): The following should only trigger when a small blind is missing |
| `TD-187C8208` | parser | FIXME | [fpdb_3_legacy/EnetToFpdb.py:318](fpdb_3_legacy/EnetToFpdb.py#L318) | handle other currencies, play money |
| `TD-3FB18AD8` | parser | FIXME | [fpdb_3_legacy/EntractionToFpdb.py:265](fpdb_3_legacy/EntractionToFpdb.py#L265) | handle other currencies, play money |
| `TD-30783EBC` | parser | HACK | [fpdb_3_legacy/EverestToFpdb.py:174](fpdb_3_legacy/EverestToFpdb.py#L174) | tablename not in every hand. |
| `TD-9F6C9348` | parser | FIXME | [fpdb_3_legacy/EverestToFpdb.py:214](fpdb_3_legacy/EverestToFpdb.py#L214) | u'DATETIME': u'1291155932' |
| `TD-BFA05051` | parser | TODO | [fpdb_3_legacy/EverleafToFpdb.py:44](fpdb_3_legacy/EverleafToFpdb.py#L44) | change \x80 to \x20\x80, update all regexes accordingly |
| `TD-D6DF417F` | parser | TODO | [fpdb_3_legacy/EverleafToFpdb.py:259](fpdb_3_legacy/EverleafToFpdb.py#L259) | we should fetch info including buyincurrency, buyin and fee from URL |
| `TD-C3B2EB7C` | parser | FIXME | [fpdb_3_legacy/MergeSummary.py:361](fpdb_3_legacy/MergeSummary.py#L361) | Searching every line for all regexes is pretty horrible |
| `TD-6EB9E7A5` | parser | FIXME | [fpdb_3_legacy/MergeSummary.py:362](fpdb_3_legacy/MergeSummary.py#L362) | Need to search for 'Status:  Finished' |
| `TD-2D58B08E` | parser | TODO | [fpdb_3_legacy/MergeToFpdb.py:32](fpdb_3_legacy/MergeToFpdb.py#L32) | Description à préciser |
| `TD-853C86CD` | parser | FIXME | [fpdb_3_legacy/MergeToFpdb.py:647](fpdb_3_legacy/MergeToFpdb.py#L647) | Description à préciser |
| `TD-AF7CB899` | parser | TODO | [fpdb_3_legacy/OnGameToFpdb.py:112](fpdb_3_legacy/OnGameToFpdb.py#L112) | detect play money |
| `TD-83283D95` | parser | TODO | [fpdb_3_legacy/OnGameToFpdb.py:160](fpdb_3_legacy/OnGameToFpdb.py#L160) | should probably rename re_HeroCards and corresponding method, |
| `TD-5B027A09` | parser | TODO | [fpdb_3_legacy/OnGameToFpdb.py:327](fpdb_3_legacy/OnGameToFpdb.py#L327) | Manually adjust time against OFFSET |
| `TD-2AEF5D7C` | parser | TODO | [fpdb_3_legacy/PacificPokerToFpdb.py:195](fpdb_3_legacy/PacificPokerToFpdb.py#L195) | unknown in available hand histories for pacificpoker |
| `TD-6E45CFBA` | parser | FIXME | [fpdb_3_legacy/PacificPokerToFpdb.py:409](fpdb_3_legacy/PacificPokerToFpdb.py#L409) | handle other currencies, FPP, play money |
| `TD-6C7C042C` | parser | FIXME | [fpdb_3_legacy/PartyPokerToFpdb.py:205](fpdb_3_legacy/PartyPokerToFpdb.py#L205) | check if play money is correct |
| `TD-E2BB62B2` | parser | FIXME | [fpdb_3_legacy/PkrToFpdb.py:148](fpdb_3_legacy/PkrToFpdb.py#L148) | Sionel posts $0.04 is a second big blind in a different format. |
| `TD-BC41779F` | parser | TODO | [fpdb_3_legacy/PkrToFpdb.py:236](fpdb_3_legacy/PkrToFpdb.py#L236) | I rather like the idea of just having this dict as hand.info |
| `TD-7B9F56EC` | parser | FIXME | [fpdb_3_legacy/PkrToFpdb.py:270](fpdb_3_legacy/PkrToFpdb.py#L270) | The key looks like: '€0.82+€0.18 EUR' |
| `TD-7217B4BD` | parser | TODO | [fpdb_3_legacy/PkrToFpdb.py:403](fpdb_3_legacy/PkrToFpdb.py#L403) | Going to have to write an addCallStoopid |
| `TD-D43264BE` | parser | FIXME | [fpdb_3_legacy/PokerTrackerToFpdb.py:689](fpdb_3_legacy/PokerTrackerToFpdb.py#L689) | handle other currencies, play money |
| `TD-31EFD5A8` | parser | FIXME | [fpdb_3_legacy/PokerTrackerToFpdb.py:916](fpdb_3_legacy/PokerTrackerToFpdb.py#L916) | Description à préciser |
| `TD-40764682` | parser | TODO | [fpdb_3_legacy/SummaryEverleaf.py:120](fpdb_3_legacy/SummaryEverleaf.py#L120) | Can we get attrs in the END tag too? Would be useful to make SURE we're closing the right div .. |
| `TD-7B179274` | parser | TODO | [fpdb_3_legacy/SummaryEverleaf.py:122](fpdb_3_legacy/SummaryEverleaf.py#L122) | Should probably just make sure everything is false at this point |
| `TD-08077AA4` | parser | TODO | [fpdb_3_legacy/SummaryEverleaf.py:158](fpdb_3_legacy/SummaryEverleaf.py#L158) | Further parse the fee from this |
| `TD-C38D627C` | parser | FIXME | [fpdb_3_legacy/UnibetToFpdb.py:708](fpdb_3_legacy/UnibetToFpdb.py#L708) | handle other currencies, play money |
| `TD-BF4B4B2B` | parser | TODO | [fpdb_3_legacy/WinamaxSummary.py:516](fpdb_3_legacy/WinamaxSummary.py#L516) | dev): obv not a great metric |
| `TD-AF613862` | parser | TODO | [fpdb_3_legacy/WinamaxToFpdb.py:197](fpdb_3_legacy/WinamaxToFpdb.py#L197) | fpdb): should probably rename re_hero_cards and corresponding method, |
| `TD-1C729FFE` | parser | TODO | [fpdb_3_legacy/WinamaxToFpdb.py:521](fpdb_3_legacy/WinamaxToFpdb.py#L521) | maintainer): long-term solution for table naming on Winamax. |
| `TD-AADEA234` | parser | TODO | [fpdb_3_legacy/WinamaxToFpdb.py:608](fpdb_3_legacy/WinamaxToFpdb.py#L608) | maintainer): Is this correct? Old code tried to |
| `TD-8B5FAEB2` | poker-domain | TODO | [fpdb_3_legacy/DerivedStats.py:93](fpdb_3_legacy/DerivedStats.py#L93) | future: REFACTOR - This function is too long (79 statements > 50 |
| `TD-405847C6` | poker-domain | TODO | [fpdb_3_legacy/DerivedStats.py:482](fpdb_3_legacy/DerivedStats.py#L482) | future: REFACTOR - This method is too complex (C901: 25 > 10, PLR0912: 30 > 12, PLR0915: 144 > 50 |
| `TD-27406CEB` | poker-domain | TODO | [fpdb_3_legacy/DerivedStats.py:728](fpdb_3_legacy/DerivedStats.py#L728) | future: REFACTOR - This method is too complex (C901: 25 > 10, PLR0912: 28 > 12 |
