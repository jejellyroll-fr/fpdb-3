# Registre de dette technique

Ce fichier est généré par `python tools/todo_inventory.py`. Chaque marqueur
`TODO`, `FIXME` ou `HACK` du code possède ainsi un identifiant stable et une
catégorie. Modifier le code source, puis régénérer ce registre.

**Total : 33 tâches ouvertes.**

| Catégorie | Nombre |
|---|---:|
| parser | 30 |
| poker-domain | 3 |

## Tâches

| ID | Catégorie | Type | Emplacement | Description |
|---|---|---|---|---|
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
