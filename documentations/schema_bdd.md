# Schéma de la base **fpdb.db3**

_Généré le 2025-07-18 22:00:06_

## Actions

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| name | TEXT | Oui |  |  |
| code | TEXT | Oui |  |  |

## Autorates

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| playerId | INT | Non |  |  |
| gametypeId | INT | Non |  |  |
| description | TEXT | Non |  |  |
| shortDesc | TEXT | Non |  |  |
| ratingTime | timestamp | Non |  |  |
| handCount | INT | Non |  |  |

## Backings

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| tourneysPlayersId | INT | Oui |  |  |
| playerId | INT | Oui |  |  |
| buyInPercentage | REAL UNSIGNED | Oui |  |  |
| payOffPercentage | REAL UNSIGNED | Oui |  |  |

### Index

* `Backings_playerId_idx` : playerId
* `Backings_tourneysPlayersId_idx` : tourneysPlayersId

## Boards

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| handId | INT | Oui |  |  |
| boardId | INT | Non |  |  |
| boardcard1 | INT | Non |  |  |
| boardcard2 | INT | Non |  |  |
| boardcard3 | INT | Non |  |  |
| boardcard4 | INT | Non |  |  |
| boardcard5 | INT | Non |  |  |

### Index

* `Boards_handId_idx` : handId

## CardsCache

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| weekId | INT | Non |  |  |
| monthId | INT | Non |  |  |
| gametypeId | INT | Non |  |  |
| tourneyTypeId | INT | Non |  |  |
| playerId | INT | Non |  |  |
| startCards | INT | Non |  |  |
| n | INT | Non |  |  |
| street0VPIChance | INT | Non |  |  |
| street0VPI | INT | Non |  |  |
| street0AggrChance | INT | Non |  |  |
| street0Aggr | INT | Non |  |  |
| street0CalledRaiseChance | INT | Non |  |  |
| street0CalledRaiseDone | INT | Non |  |  |
| street0_2BChance | INT | Non |  |  |
| street0_2BDone | INT | Non |  |  |
| street0_3BChance | INT | Non |  |  |
| street0_3BDone | INT | Non |  |  |
| street0_4BChance | INT | Non |  |  |
| street0_4BDone | INT | Non |  |  |
| street0_C4BChance | INT | Non |  |  |
| street0_C4BDone | INT | Non |  |  |
| street0_FoldTo2BChance | INT | Non |  |  |
| street0_FoldTo2BDone | INT | Non |  |  |
| street0_FoldTo3BChance | INT | Non |  |  |
| street0_FoldTo3BDone | INT | Non |  |  |
| street0_FoldTo4BChance | INT | Non |  |  |
| street0_FoldTo4BDone | INT | Non |  |  |
| street0_SqueezeChance | INT | Non |  |  |
| street0_SqueezeDone | INT | Non |  |  |
| raiseToStealChance | INT | Non |  |  |
| raiseToStealDone | INT | Non |  |  |
| stealChance | INT | Non |  |  |
| stealDone | INT | Non |  |  |
| success_Steal | INT | Non |  |  |
| street1Seen | INT | Non |  |  |
| street2Seen | INT | Non |  |  |
| street3Seen | INT | Non |  |  |
| street4Seen | INT | Non |  |  |
| sawShowdown | INT | Non |  |  |
| street1Aggr | INT | Non |  |  |
| street2Aggr | INT | Non |  |  |
| street3Aggr | INT | Non |  |  |
| street4Aggr | INT | Non |  |  |
| otherRaisedStreet0 | INT | Non |  |  |
| otherRaisedStreet1 | INT | Non |  |  |
| otherRaisedStreet2 | INT | Non |  |  |
| otherRaisedStreet3 | INT | Non |  |  |
| otherRaisedStreet4 | INT | Non |  |  |
| foldToOtherRaisedStreet0 | INT | Non |  |  |
| foldToOtherRaisedStreet1 | INT | Non |  |  |
| foldToOtherRaisedStreet2 | INT | Non |  |  |
| foldToOtherRaisedStreet3 | INT | Non |  |  |
| foldToOtherRaisedStreet4 | INT | Non |  |  |
| wonWhenSeenStreet1 | INT | Non |  |  |
| wonWhenSeenStreet2 | INT | Non |  |  |
| wonWhenSeenStreet3 | INT | Non |  |  |
| wonWhenSeenStreet4 | INT | Non |  |  |
| wonAtSD | INT | Non |  |  |
| raiseFirstInChance | INT | Non |  |  |
| raisedFirstIn | INT | Non |  |  |
| foldBbToStealChance | INT | Non |  |  |
| foldedBbToSteal | INT | Non |  |  |
| foldSbToStealChance | INT | Non |  |  |
| foldedSbToSteal | INT | Non |  |  |
| street1CBChance | INT | Non |  |  |
| street1CBDone | INT | Non |  |  |
| street2CBChance | INT | Non |  |  |
| street2CBDone | INT | Non |  |  |
| street3CBChance | INT | Non |  |  |
| street3CBDone | INT | Non |  |  |
| street4CBChance | INT | Non |  |  |
| street4CBDone | INT | Non |  |  |
| foldToStreet1CBChance | INT | Non |  |  |
| foldToStreet1CBDone | INT | Non |  |  |
| foldToStreet2CBChance | INT | Non |  |  |
| foldToStreet2CBDone | INT | Non |  |  |
| foldToStreet3CBChance | INT | Non |  |  |
| foldToStreet3CBDone | INT | Non |  |  |
| foldToStreet4CBChance | INT | Non |  |  |
| foldToStreet4CBDone | INT | Non |  |  |
| common | INT | Non |  |  |
| committed | INT | Non |  |  |
| winnings | INT | Non |  |  |
| rake | INT | Non |  |  |
| rakeDealt | decimal | Non |  |  |
| rakeContributed | decimal | Non |  |  |
| rakeWeighted | decimal | Non |  |  |
| totalProfit | INT | Non |  |  |
| allInEV | decimal | Non |  |  |
| showdownWinnings | INT | Non |  |  |
| nonShowdownWinnings | INT | Non |  |  |
| street1CheckCallRaiseChance | INT | Non |  |  |
| street1CheckCallDone | INT | Non |  |  |
| street1CheckRaiseDone | INT | Non |  |  |
| street2CheckCallRaiseChance | INT | Non |  |  |
| street2CheckCallDone | INT | Non |  |  |
| street2CheckRaiseDone | INT | Non |  |  |
| street3CheckCallRaiseChance | INT | Non |  |  |
| street3CheckCallDone | INT | Non |  |  |
| street3CheckRaiseDone | INT | Non |  |  |
| street4CheckCallRaiseChance | INT | Non |  |  |
| street4CheckCallDone | INT | Non |  |  |
| street4CheckRaiseDone | INT | Non |  |  |
| street0Calls | INT | Non |  |  |
| street1Calls | INT | Non |  |  |
| street2Calls | INT | Non |  |  |
| street3Calls | INT | Non |  |  |
| street4Calls | INT | Non |  |  |
| street0Bets | INT | Non |  |  |
| street1Bets | INT | Non |  |  |
| street2Bets | INT | Non |  |  |
| street3Bets | INT | Non |  |  |
| street4Bets | INT | Non |  |  |
| street0Raises | INT | Non |  |  |
| street1Raises | INT | Non |  |  |
| street2Raises | INT | Non |  |  |
| street3Raises | INT | Non |  |  |
| street4Raises | INT | Non |  |  |
| street1Discards | INT | Non |  |  |
| street2Discards | INT | Non |  |  |
| street3Discards | INT | Non |  |  |

### Index

* `CardsCache_Compound_idx` UNIQUE : weekId, monthId, gametypeId, tourneyTypeId, playerId, startCards

## Files

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| file | TEXT | Oui |  |  |
| site | VARCHAR(32) | Non |  |  |
| type | VARCHAR(7) | Non |  |  |
| startTime | timestamp | Oui |  |  |
| lastUpdate | timestamp | Oui |  |  |
| endTime | timestamp | Non |  |  |
| hands | INT | Non |  |  |
| storedHands | INT | Non |  |  |
| dups | INT | Non |  |  |
| partial | INT | Non |  |  |
| skipped | INT | Non |  |  |
| errs | INT | Non |  |  |
| ttime100 | INT | Non |  |  |
| finished | BOOLEAN | Non |  |  |

### Index

* `index_file` UNIQUE : file

## Gametypes

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Oui | 1 |  |
| siteId | INTEGER | Oui |  |  |
| currency | TEXT | Oui |  |  |
| type | TEXT | Oui |  |  |
| base | TEXT | Oui |  |  |
| category | TEXT | Oui |  |  |
| limitType | TEXT | Oui |  |  |
| hiLo | TEXT | Oui |  |  |
| mix | TEXT | Oui |  |  |
| smallBlind | INTEGER | Non |  |  |
| bigBlind | INTEGER | Non |  |  |
| smallBet | INTEGER | Oui |  |  |
| bigBet | INTEGER | Oui |  |  |
| maxSeats | INT | Oui |  |  |
| ante | INT | Oui |  |  |
| buyinType | TEXT | Oui |  |  |
| fast | INT | Non |  |  |
| newToGame | INT | Non |  |  |
| homeGame | INT | Non |  |  |
| split | INT | Non |  |  |

### Clés étrangères

| Colonne | Référence | ON UPDATE | ON DELETE |
|---------|-----------|-----------|-----------|
| siteId | Sites(id) | NO ACTION | CASCADE |

### Index

* `Gametypes_siteId_idx` : siteId

## Hands

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| tableName | TEXT(50) | Oui |  |  |
| siteHandNo | INT | Oui |  |  |
| tourneyId | INT | Non |  |  |
| gametypeId | INT | Oui |  |  |
| sessionId | INT | Non |  |  |
| fileId | INT | Oui |  |  |
| startTime | timestamp | Oui |  |  |
| importTime | timestamp | Oui |  |  |
| seats | INT | Oui |  |  |
| heroSeat | INT | Oui |  |  |
| maxPosition | INT | Oui |  |  |
| boardcard1 | INT | Non |  |  |
| boardcard2 | INT | Non |  |  |
| boardcard3 | INT | Non |  |  |
| boardcard4 | INT | Non |  |  |
| boardcard5 | INT | Non |  |  |
| texture | INT | Non |  |  |
| runItTwice | BOOLEAN | Non |  |  |
| playersVpi | INT | Oui |  |  |
| playersAtStreet1 | INT | Oui |  |  |
| playersAtStreet2 | INT | Oui |  |  |
| playersAtStreet3 | INT | Oui |  |  |
| playersAtStreet4 | INT | Oui |  |  |
| playersAtShowdown | INT | Oui |  |  |
| street0Raises | INT | Oui |  |  |
| street1Raises | INT | Oui |  |  |
| street2Raises | INT | Oui |  |  |
| street3Raises | INT | Oui |  |  |
| street4Raises | INT | Oui |  |  |
| street0Pot | INT | Non |  |  |
| street1Pot | INT | Non |  |  |
| street2Pot | INT | Non |  |  |
| street3Pot | INT | Non |  |  |
| street4Pot | INT | Non |  |  |
| finalPot | INT | Non |  |  |
| comment | TEXT | Non |  |  |
| commentTs | timestamp | Non |  |  |

### Index

* `Hands_fileId_idx` : fileId
* `Hands_sessionId_idx` : sessionId
* `Hands_gametypeId_idx` : gametypeId
* `Hands_tourneyId_idx` : tourneyId
* `pot_idx` : finalPot
* `index_tableName` : tableName
* `seats_idx` : seats
* `heroSeat_idx` UNIQUE : id, heroSeat
* `siteHandNo` UNIQUE : siteHandNo, gametypeId

## HandsActions

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| handId | INT | Oui |  |  |
| playerId | INT | Oui |  |  |
| street | SMALLINT | Non |  |  |
| actionNo | SMALLINT | Non |  |  |
| streetActionNo | SMALLINT | Non |  |  |
| actionId | SMALLINT | Non |  |  |
| amount | INT | Non |  |  |
| raiseTo | INT | Non |  |  |
| amountCalled | INT | Non |  |  |
| numDiscarded | SMALLINT | Non |  |  |
| cardsDiscarded | TEXT | Non |  |  |
| allIn | BOOLEAN | Non |  |  |

### Index

* `HandsActions_actionId_idx` : actionId
* `HandsActions_playerId_idx` : playerId
* `HandsActions_handId_idx` : handId

## HandsPlayers

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| handId | INT | Oui |  |  |
| playerId | INT | Oui |  |  |
| startCash | INT | Oui |  |  |
| effStack | INT | Oui |  |  |
| startBounty | INT | Non |  |  |
| endBounty | INT | Non |  |  |
| position | TEXT | Non |  |  |
| seatNo | INT | Oui |  |  |
| sitout | BOOLEAN | Oui |  |  |
| card1 | INT | Oui |  |  |
| card2 | INT | Oui |  |  |
| card3 | INT | Non |  |  |
| card4 | INT | Non |  |  |
| card5 | INT | Non |  |  |
| card6 | INT | Non |  |  |
| card7 | INT | Non |  |  |
| card8 | INT | Non |  |  |
| card9 | INT | Non |  |  |
| card10 | INT | Non |  |  |
| card11 | INT | Non |  |  |
| card12 | INT | Non |  |  |
| card13 | INT | Non |  |  |
| card14 | INT | Non |  |  |
| card15 | INT | Non |  |  |
| card16 | INT | Non |  |  |
| card17 | INT | Non |  |  |
| card18 | INT | Non |  |  |
| card19 | INT | Non |  |  |
| card20 | INT | Non |  |  |
| startCards | INT | Non |  |  |
| common | INT | Oui |  |  |
| committed | INT | Oui |  |  |
| winnings | INT | Oui |  |  |
| rake | INT | Oui |  |  |
| rakeDealt | decimal | Oui |  |  |
| rakeContributed | decimal | Oui |  |  |
| rakeWeighted | decimal | Oui |  |  |
| totalProfit | INT | Non |  |  |
| allInEV | decimal | Non |  |  |
| comment | TEXT | Non |  |  |
| commentTs | timestamp | Non |  |  |
| tourneysPlayersId | INT | Non |  |  |
| wonWhenSeenStreet1 | INT | Non |  |  |
| wonWhenSeenStreet2 | INT | Non |  |  |
| wonWhenSeenStreet3 | INT | Non |  |  |
| wonWhenSeenStreet4 | INT | Non |  |  |
| wonAtSD | INT | Non |  |  |
| street0VPIChance | INT | Non |  |  |
| street0VPI | INT | Non |  |  |
| street0AggrChance | INT | Non |  |  |
| street0Aggr | INT | Non |  |  |
| street0CalledRaiseChance | INT | Non |  |  |
| street0CalledRaiseDone | INT | Non |  |  |
| street0_2BChance | INT | Non |  |  |
| street0_2BDone | INT | Non |  |  |
| street0_3BChance | INT | Non |  |  |
| street0_3BDone | INT | Non |  |  |
| street0_4BChance | INT | Non |  |  |
| street0_4BDone | INT | Non |  |  |
| street0_C4BChance | INT | Non |  |  |
| street0_C4BDone | INT | Non |  |  |
| street0_FoldTo2BChance | INT | Non |  |  |
| street0_FoldTo2BDone | INT | Non |  |  |
| street0_FoldTo3BChance | INT | Non |  |  |
| street0_FoldTo3BDone | INT | Non |  |  |
| street0_FoldTo4BChance | INT | Non |  |  |
| street0_FoldTo4BDone | INT | Non |  |  |
| street0_SqueezeChance | INT | Non |  |  |
| street0_SqueezeDone | INT | Non |  |  |
| raiseToStealChance | INT | Non |  |  |
| raiseToStealDone | INT | Non |  |  |
| stealChance | INT | Non |  |  |
| stealDone | INT | Non |  |  |
| success_Steal | INT | Non |  |  |
| street1Seen | INT | Non |  |  |
| street2Seen | INT | Non |  |  |
| street3Seen | INT | Non |  |  |
| street4Seen | INT | Non |  |  |
| sawShowdown | INT | Non |  |  |
| showed | INT | Non |  |  |
| street0AllIn | INT | Non |  |  |
| street1AllIn | INT | Non |  |  |
| street2AllIn | INT | Non |  |  |
| street3AllIn | INT | Non |  |  |
| street4AllIn | INT | Non |  |  |
| wentAllIn | INT | Non |  |  |
| street0InPosition | INT | Non |  |  |
| street1InPosition | INT | Non |  |  |
| street2InPosition | INT | Non |  |  |
| street3InPosition | INT | Non |  |  |
| street4InPosition | INT | Non |  |  |
| street0FirstToAct | INT | Non |  |  |
| street1FirstToAct | INT | Non |  |  |
| street2FirstToAct | INT | Non |  |  |
| street3FirstToAct | INT | Non |  |  |
| street4FirstToAct | INT | Non |  |  |
| street1Aggr | INT | Non |  |  |
| street2Aggr | INT | Non |  |  |
| street3Aggr | INT | Non |  |  |
| street4Aggr | INT | Non |  |  |
| otherRaisedStreet0 | INT | Non |  |  |
| otherRaisedStreet1 | INT | Non |  |  |
| otherRaisedStreet2 | INT | Non |  |  |
| otherRaisedStreet3 | INT | Non |  |  |
| otherRaisedStreet4 | INT | Non |  |  |
| foldToOtherRaisedStreet0 | INT | Non |  |  |
| foldToOtherRaisedStreet1 | INT | Non |  |  |
| foldToOtherRaisedStreet2 | INT | Non |  |  |
| foldToOtherRaisedStreet3 | INT | Non |  |  |
| foldToOtherRaisedStreet4 | INT | Non |  |  |
| raiseFirstInChance | INT | Non |  |  |
| raisedFirstIn | INT | Non |  |  |
| foldBbToStealChance | INT | Non |  |  |
| foldedBbToSteal | INT | Non |  |  |
| foldSbToStealChance | INT | Non |  |  |
| foldedSbToSteal | INT | Non |  |  |
| street1CBChance | INT | Non |  |  |
| street1CBDone | INT | Non |  |  |
| street2CBChance | INT | Non |  |  |
| street2CBDone | INT | Non |  |  |
| street3CBChance | INT | Non |  |  |
| street3CBDone | INT | Non |  |  |
| street4CBChance | INT | Non |  |  |
| street4CBDone | INT | Non |  |  |
| foldToStreet1CBChance | INT | Non |  |  |
| foldToStreet1CBDone | INT | Non |  |  |
| foldToStreet2CBChance | INT | Non |  |  |
| foldToStreet2CBDone | INT | Non |  |  |
| foldToStreet3CBChance | INT | Non |  |  |
| foldToStreet3CBDone | INT | Non |  |  |
| foldToStreet4CBChance | INT | Non |  |  |
| foldToStreet4CBDone | INT | Non |  |  |
| street1CheckCallRaiseChance | INT | Non |  |  |
| street1CheckCallDone | INT | Non |  |  |
| street1CheckRaiseDone | INT | Non |  |  |
| street2CheckCallRaiseChance | INT | Non |  |  |
| street2CheckCallDone | INT | Non |  |  |
| street2CheckRaiseDone | INT | Non |  |  |
| street3CheckCallRaiseChance | INT | Non |  |  |
| street3CheckCallDone | INT | Non |  |  |
| street3CheckRaiseDone | INT | Non |  |  |
| street4CheckCallRaiseChance | INT | Non |  |  |
| street4CheckCallDone | INT | Non |  |  |
| street4CheckRaiseDone | INT | Non |  |  |
| street0Calls | INT | Non |  |  |
| street1Calls | INT | Non |  |  |
| street2Calls | INT | Non |  |  |
| street3Calls | INT | Non |  |  |
| street4Calls | INT | Non |  |  |
| street0Bets | INT | Non |  |  |
| street1Bets | INT | Non |  |  |
| street2Bets | INT | Non |  |  |
| street3Bets | INT | Non |  |  |
| street4Bets | INT | Non |  |  |
| street0Raises | INT | Non |  |  |
| street1Raises | INT | Non |  |  |
| street2Raises | INT | Non |  |  |
| street3Raises | INT | Non |  |  |
| street4Raises | INT | Non |  |  |
| street1Discards | INT | Non |  |  |
| street2Discards | INT | Non |  |  |
| street3Discards | INT | Non |  |  |
| handString | TEXT | Non |  |  |
| actionString | VARCHAR(15) | Non |  |  |

### Index

* `HandsPlayers_tourneysPlayersId_idx` : tourneysPlayersId
* `HandsPlayers_playerId_idx` : playerId
* `HandsPlayers_handId_idx` : handId
* `winnings_idx` : winnings
* `profit_idx` : totalProfit
* `eff_stack_idx` : effStack
* `cash_idx` : startCash
* `position_idx` : position
* `playerSeat_idx` UNIQUE : handId, seatNo

## HandsPots

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| handId | INT | Oui |  |  |
| potId | INT | Non |  |  |
| boardId | INT | Non |  |  |
| hiLo | TEXT | Oui |  |  |
| playerId | INT | Oui |  |  |
| pot | INT | Non |  |  |
| collected | INT | Non |  |  |
| rake | INT | Non |  |  |

### Index

* `HandsPots_playerId_idx` : playerId
* `HandsPots_handId_idx` : handId

## HandsStove

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| handId | INT | Oui |  |  |
| playerId | INT | Oui |  |  |
| streetId | INT | Non |  |  |
| boardId | INT | Non |  |  |
| hiLo | TEXT | Oui |  |  |
| rankId | INT | Non |  |  |
| value | INT | Non |  |  |
| cards | TEXT | Non |  |  |
| ev | decimal | Non |  |  |

### Index

* `HandsStove_playerId_idx` : playerId
* `HandsStove_handId_idx` : handId
* `street_idx` : streetId, boardId

## HudCache

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| gametypeId | INT | Non |  |  |
| playerId | INT | Non |  |  |
| seats | INT | Non |  |  |
| position | TEXT | Non |  |  |
| tourneyTypeId | INT | Non |  |  |
| styleKey | TEXT | Oui |  |  |
| n | INT | Non |  |  |
| street0VPIChance | INT | Non |  |  |
| street0VPI | INT | Non |  |  |
| street0AggrChance | INT | Non |  |  |
| street0Aggr | INT | Non |  |  |
| street0CalledRaiseChance | INT | Non |  |  |
| street0CalledRaiseDone | INT | Non |  |  |
| street0_2BChance | INT | Non |  |  |
| street0_2BDone | INT | Non |  |  |
| street0_3BChance | INT | Non |  |  |
| street0_3BDone | INT | Non |  |  |
| street0_4BChance | INT | Non |  |  |
| street0_4BDone | INT | Non |  |  |
| street0_C4BChance | INT | Non |  |  |
| street0_C4BDone | INT | Non |  |  |
| street0_FoldTo2BChance | INT | Non |  |  |
| street0_FoldTo2BDone | INT | Non |  |  |
| street0_FoldTo3BChance | INT | Non |  |  |
| street0_FoldTo3BDone | INT | Non |  |  |
| street0_FoldTo4BChance | INT | Non |  |  |
| street0_FoldTo4BDone | INT | Non |  |  |
| street0_SqueezeChance | INT | Non |  |  |
| street0_SqueezeDone | INT | Non |  |  |
| raiseToStealChance | INT | Non |  |  |
| raiseToStealDone | INT | Non |  |  |
| stealChance | INT | Non |  |  |
| stealDone | INT | Non |  |  |
| success_Steal | INT | Non |  |  |
| street1Seen | INT | Non |  |  |
| street2Seen | INT | Non |  |  |
| street3Seen | INT | Non |  |  |
| street4Seen | INT | Non |  |  |
| sawShowdown | INT | Non |  |  |
| street1Aggr | INT | Non |  |  |
| street2Aggr | INT | Non |  |  |
| street3Aggr | INT | Non |  |  |
| street4Aggr | INT | Non |  |  |
| otherRaisedStreet0 | INT | Non |  |  |
| otherRaisedStreet1 | INT | Non |  |  |
| otherRaisedStreet2 | INT | Non |  |  |
| otherRaisedStreet3 | INT | Non |  |  |
| otherRaisedStreet4 | INT | Non |  |  |
| foldToOtherRaisedStreet0 | INT | Non |  |  |
| foldToOtherRaisedStreet1 | INT | Non |  |  |
| foldToOtherRaisedStreet2 | INT | Non |  |  |
| foldToOtherRaisedStreet3 | INT | Non |  |  |
| foldToOtherRaisedStreet4 | INT | Non |  |  |
| wonWhenSeenStreet1 | INT | Non |  |  |
| wonWhenSeenStreet2 | INT | Non |  |  |
| wonWhenSeenStreet3 | INT | Non |  |  |
| wonWhenSeenStreet4 | INT | Non |  |  |
| wonAtSD | INT | Non |  |  |
| raiseFirstInChance | INT | Non |  |  |
| raisedFirstIn | INT | Non |  |  |
| foldBbToStealChance | INT | Non |  |  |
| foldedBbToSteal | INT | Non |  |  |
| foldSbToStealChance | INT | Non |  |  |
| foldedSbToSteal | INT | Non |  |  |
| street1CBChance | INT | Non |  |  |
| street1CBDone | INT | Non |  |  |
| street2CBChance | INT | Non |  |  |
| street2CBDone | INT | Non |  |  |
| street3CBChance | INT | Non |  |  |
| street3CBDone | INT | Non |  |  |
| street4CBChance | INT | Non |  |  |
| street4CBDone | INT | Non |  |  |
| foldToStreet1CBChance | INT | Non |  |  |
| foldToStreet1CBDone | INT | Non |  |  |
| foldToStreet2CBChance | INT | Non |  |  |
| foldToStreet2CBDone | INT | Non |  |  |
| foldToStreet3CBChance | INT | Non |  |  |
| foldToStreet3CBDone | INT | Non |  |  |
| foldToStreet4CBChance | INT | Non |  |  |
| foldToStreet4CBDone | INT | Non |  |  |
| common | INT | Non |  |  |
| committed | INT | Non |  |  |
| winnings | INT | Non |  |  |
| rake | INT | Non |  |  |
| rakeDealt | decimal | Non |  |  |
| rakeContributed | decimal | Non |  |  |
| rakeWeighted | decimal | Non |  |  |
| totalProfit | INT | Non |  |  |
| allInEV | decimal | Non |  |  |
| showdownWinnings | INT | Non |  |  |
| nonShowdownWinnings | INT | Non |  |  |
| street1CheckCallRaiseChance | INT | Non |  |  |
| street1CheckCallDone | INT | Non |  |  |
| street1CheckRaiseDone | INT | Non |  |  |
| street2CheckCallRaiseChance | INT | Non |  |  |
| street2CheckCallDone | INT | Non |  |  |
| street2CheckRaiseDone | INT | Non |  |  |
| street3CheckCallRaiseChance | INT | Non |  |  |
| street3CheckCallDone | INT | Non |  |  |
| street3CheckRaiseDone | INT | Non |  |  |
| street4CheckCallRaiseChance | INT | Non |  |  |
| street4CheckCallDone | INT | Non |  |  |
| street4CheckRaiseDone | INT | Non |  |  |
| street0Calls | INT | Non |  |  |
| street1Calls | INT | Non |  |  |
| street2Calls | INT | Non |  |  |
| street3Calls | INT | Non |  |  |
| street4Calls | INT | Non |  |  |
| street0Bets | INT | Non |  |  |
| street1Bets | INT | Non |  |  |
| street2Bets | INT | Non |  |  |
| street3Bets | INT | Non |  |  |
| street4Bets | INT | Non |  |  |
| street0Raises | INT | Non |  |  |
| street1Raises | INT | Non |  |  |
| street2Raises | INT | Non |  |  |
| street3Raises | INT | Non |  |  |
| street4Raises | INT | Non |  |  |
| street1Discards | INT | Non |  |  |
| street2Discards | INT | Non |  |  |
| street3Discards | INT | Non |  |  |

### Index

* `HudCache_tourneyTypeId_idx` : tourneyTypeId
* `HudCache_playerId_idx` : playerId
* `HudCache_gametypeId_idx` : gametypeId
* `HudCache_Compound_idx` UNIQUE : gametypeId, playerId, seats, position, tourneyTypeId, styleKey

## Months

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| monthStart | timestamp | Oui |  |  |

## Players

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| name | TEXT | Non |  |  |
| siteId | INTEGER | Non |  |  |
| hero | BOOLEAN | Non |  |  |
| chars | TEXT | Non |  |  |
| comment | TEXT | Non |  |  |
| commentTs | timestamp | Non |  |  |
| profil | TEXT | Non |  |  |
| color_code | TEXT | Non |  | '#FFFFFF' |
| symbol | TEXT | Non |  | '★' |

### Clés étrangères

| Colonne | Référence | ON UPDATE | ON DELETE |
|---------|-----------|-----------|-----------|
| siteId | Sites(id) | NO ACTION | CASCADE |

### Index

* `Players_siteId_idx` : siteId
* `player_heroes` : hero
* `index_playerName` : name
* `name` UNIQUE : name, siteId

## PositionsCache

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| weekId | INT | Non |  |  |
| monthId | INT | Non |  |  |
| gametypeId | INT | Non |  |  |
| tourneyTypeId | INT | Non |  |  |
| playerId | INT | Non |  |  |
| seats | INT | Non |  |  |
| maxPosition | INT | Oui |  |  |
| position | TEXT | Non |  |  |
| n | INT | Non |  |  |
| street0VPIChance | INT | Non |  |  |
| street0VPI | INT | Non |  |  |
| street0AggrChance | INT | Non |  |  |
| street0Aggr | INT | Non |  |  |
| street0CalledRaiseChance | INT | Non |  |  |
| street0CalledRaiseDone | INT | Non |  |  |
| street0_2BChance | INT | Non |  |  |
| street0_2BDone | INT | Non |  |  |
| street0_3BChance | INT | Non |  |  |
| street0_3BDone | INT | Non |  |  |
| street0_4BChance | INT | Non |  |  |
| street0_4BDone | INT | Non |  |  |
| street0_C4BChance | INT | Non |  |  |
| street0_C4BDone | INT | Non |  |  |
| street0_FoldTo2BChance | INT | Non |  |  |
| street0_FoldTo2BDone | INT | Non |  |  |
| street0_FoldTo3BChance | INT | Non |  |  |
| street0_FoldTo3BDone | INT | Non |  |  |
| street0_FoldTo4BChance | INT | Non |  |  |
| street0_FoldTo4BDone | INT | Non |  |  |
| street0_SqueezeChance | INT | Non |  |  |
| street0_SqueezeDone | INT | Non |  |  |
| raiseToStealChance | INT | Non |  |  |
| raiseToStealDone | INT | Non |  |  |
| stealChance | INT | Non |  |  |
| stealDone | INT | Non |  |  |
| success_Steal | INT | Non |  |  |
| street1Seen | INT | Non |  |  |
| street2Seen | INT | Non |  |  |
| street3Seen | INT | Non |  |  |
| street4Seen | INT | Non |  |  |
| sawShowdown | INT | Non |  |  |
| street1Aggr | INT | Non |  |  |
| street2Aggr | INT | Non |  |  |
| street3Aggr | INT | Non |  |  |
| street4Aggr | INT | Non |  |  |
| otherRaisedStreet0 | INT | Non |  |  |
| otherRaisedStreet1 | INT | Non |  |  |
| otherRaisedStreet2 | INT | Non |  |  |
| otherRaisedStreet3 | INT | Non |  |  |
| otherRaisedStreet4 | INT | Non |  |  |
| foldToOtherRaisedStreet0 | INT | Non |  |  |
| foldToOtherRaisedStreet1 | INT | Non |  |  |
| foldToOtherRaisedStreet2 | INT | Non |  |  |
| foldToOtherRaisedStreet3 | INT | Non |  |  |
| foldToOtherRaisedStreet4 | INT | Non |  |  |
| wonWhenSeenStreet1 | INT | Non |  |  |
| wonWhenSeenStreet2 | INT | Non |  |  |
| wonWhenSeenStreet3 | INT | Non |  |  |
| wonWhenSeenStreet4 | INT | Non |  |  |
| wonAtSD | INT | Non |  |  |
| raiseFirstInChance | INT | Non |  |  |
| raisedFirstIn | INT | Non |  |  |
| foldBbToStealChance | INT | Non |  |  |
| foldedBbToSteal | INT | Non |  |  |
| foldSbToStealChance | INT | Non |  |  |
| foldedSbToSteal | INT | Non |  |  |
| street1CBChance | INT | Non |  |  |
| street1CBDone | INT | Non |  |  |
| street2CBChance | INT | Non |  |  |
| street2CBDone | INT | Non |  |  |
| street3CBChance | INT | Non |  |  |
| street3CBDone | INT | Non |  |  |
| street4CBChance | INT | Non |  |  |
| street4CBDone | INT | Non |  |  |
| foldToStreet1CBChance | INT | Non |  |  |
| foldToStreet1CBDone | INT | Non |  |  |
| foldToStreet2CBChance | INT | Non |  |  |
| foldToStreet2CBDone | INT | Non |  |  |
| foldToStreet3CBChance | INT | Non |  |  |
| foldToStreet3CBDone | INT | Non |  |  |
| foldToStreet4CBChance | INT | Non |  |  |
| foldToStreet4CBDone | INT | Non |  |  |
| common | INT | Non |  |  |
| committed | INT | Non |  |  |
| winnings | INT | Non |  |  |
| rake | INT | Non |  |  |
| rakeDealt | decimal | Non |  |  |
| rakeContributed | decimal | Non |  |  |
| rakeWeighted | decimal | Non |  |  |
| totalProfit | INT | Non |  |  |
| allInEV | decimal | Non |  |  |
| showdownWinnings | INT | Non |  |  |
| nonShowdownWinnings | INT | Non |  |  |
| street1CheckCallRaiseChance | INT | Non |  |  |
| street1CheckCallDone | INT | Non |  |  |
| street1CheckRaiseDone | INT | Non |  |  |
| street2CheckCallRaiseChance | INT | Non |  |  |
| street2CheckCallDone | INT | Non |  |  |
| street2CheckRaiseDone | INT | Non |  |  |
| street3CheckCallRaiseChance | INT | Non |  |  |
| street3CheckCallDone | INT | Non |  |  |
| street3CheckRaiseDone | INT | Non |  |  |
| street4CheckCallRaiseChance | INT | Non |  |  |
| street4CheckCallDone | INT | Non |  |  |
| street4CheckRaiseDone | INT | Non |  |  |
| street0Calls | INT | Non |  |  |
| street1Calls | INT | Non |  |  |
| street2Calls | INT | Non |  |  |
| street3Calls | INT | Non |  |  |
| street4Calls | INT | Non |  |  |
| street0Bets | INT | Non |  |  |
| street1Bets | INT | Non |  |  |
| street2Bets | INT | Non |  |  |
| street3Bets | INT | Non |  |  |
| street4Bets | INT | Non |  |  |
| street0Raises | INT | Non |  |  |
| street1Raises | INT | Non |  |  |
| street2Raises | INT | Non |  |  |
| street3Raises | INT | Non |  |  |
| street4Raises | INT | Non |  |  |
| street1Discards | INT | Non |  |  |
| street2Discards | INT | Non |  |  |
| street3Discards | INT | Non |  |  |

### Index

* `PositionsCache_Compound_idx` UNIQUE : weekId, monthId, gametypeId, tourneyTypeId, playerId, seats, maxPosition, position

## Rank

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| name | TEXT | Oui |  |  |

## RawHands

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| handId | BIGINT | Oui |  |  |
| rawHand | TEXT | Oui |  |  |
| complain | BOOLEAN | Oui |  | FALSE |

### Index

* `RawHands_id_idx` : id

## RawTourneys

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| tourneyId | BIGINT | Oui |  |  |
| rawTourney | TEXT | Oui |  |  |
| complain | BOOLEAN | Oui |  | FALSE |

### Index

* `RawTourneys_id_idx` : id

## Sessions

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| weekId | INT | Non |  |  |
| monthId | INT | Non |  |  |
| sessionStart | timestamp | Oui |  |  |
| sessionEnd | timestamp | Oui |  |  |

### Index

* `Sessions_monthId_idx` : monthId
* `Sessions_weekId_idx` : weekId

## SessionsCache

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| sessionId | INT | Non |  |  |
| startTime | timestamp | Oui |  |  |
| endTime | timestamp | Oui |  |  |
| gametypeId | INT | Non |  |  |
| playerId | INT | Non |  |  |
| n | INT | Non |  |  |
| street0VPIChance | INT | Non |  |  |
| street0VPI | INT | Non |  |  |
| street0AggrChance | INT | Non |  |  |
| street0Aggr | INT | Non |  |  |
| street0CalledRaiseChance | INT | Non |  |  |
| street0CalledRaiseDone | INT | Non |  |  |
| street0_2BChance | INT | Non |  |  |
| street0_2BDone | INT | Non |  |  |
| street0_3BChance | INT | Non |  |  |
| street0_3BDone | INT | Non |  |  |
| street0_4BChance | INT | Non |  |  |
| street0_4BDone | INT | Non |  |  |
| street0_C4BChance | INT | Non |  |  |
| street0_C4BDone | INT | Non |  |  |
| street0_FoldTo2BChance | INT | Non |  |  |
| street0_FoldTo2BDone | INT | Non |  |  |
| street0_FoldTo3BChance | INT | Non |  |  |
| street0_FoldTo3BDone | INT | Non |  |  |
| street0_FoldTo4BChance | INT | Non |  |  |
| street0_FoldTo4BDone | INT | Non |  |  |
| street0_SqueezeChance | INT | Non |  |  |
| street0_SqueezeDone | INT | Non |  |  |
| raiseToStealChance | INT | Non |  |  |
| raiseToStealDone | INT | Non |  |  |
| stealChance | INT | Non |  |  |
| stealDone | INT | Non |  |  |
| success_Steal | INT | Non |  |  |
| street1Seen | INT | Non |  |  |
| street2Seen | INT | Non |  |  |
| street3Seen | INT | Non |  |  |
| street4Seen | INT | Non |  |  |
| sawShowdown | INT | Non |  |  |
| street1Aggr | INT | Non |  |  |
| street2Aggr | INT | Non |  |  |
| street3Aggr | INT | Non |  |  |
| street4Aggr | INT | Non |  |  |
| otherRaisedStreet0 | INT | Non |  |  |
| otherRaisedStreet1 | INT | Non |  |  |
| otherRaisedStreet2 | INT | Non |  |  |
| otherRaisedStreet3 | INT | Non |  |  |
| otherRaisedStreet4 | INT | Non |  |  |
| foldToOtherRaisedStreet0 | INT | Non |  |  |
| foldToOtherRaisedStreet1 | INT | Non |  |  |
| foldToOtherRaisedStreet2 | INT | Non |  |  |
| foldToOtherRaisedStreet3 | INT | Non |  |  |
| foldToOtherRaisedStreet4 | INT | Non |  |  |
| wonWhenSeenStreet1 | INT | Non |  |  |
| wonWhenSeenStreet2 | INT | Non |  |  |
| wonWhenSeenStreet3 | INT | Non |  |  |
| wonWhenSeenStreet4 | INT | Non |  |  |
| wonAtSD | INT | Non |  |  |
| raiseFirstInChance | INT | Non |  |  |
| raisedFirstIn | INT | Non |  |  |
| foldBbToStealChance | INT | Non |  |  |
| foldedBbToSteal | INT | Non |  |  |
| foldSbToStealChance | INT | Non |  |  |
| foldedSbToSteal | INT | Non |  |  |
| street1CBChance | INT | Non |  |  |
| street1CBDone | INT | Non |  |  |
| street2CBChance | INT | Non |  |  |
| street2CBDone | INT | Non |  |  |
| street3CBChance | INT | Non |  |  |
| street3CBDone | INT | Non |  |  |
| street4CBChance | INT | Non |  |  |
| street4CBDone | INT | Non |  |  |
| foldToStreet1CBChance | INT | Non |  |  |
| foldToStreet1CBDone | INT | Non |  |  |
| foldToStreet2CBChance | INT | Non |  |  |
| foldToStreet2CBDone | INT | Non |  |  |
| foldToStreet3CBChance | INT | Non |  |  |
| foldToStreet3CBDone | INT | Non |  |  |
| foldToStreet4CBChance | INT | Non |  |  |
| foldToStreet4CBDone | INT | Non |  |  |
| common | INT | Non |  |  |
| committed | INT | Non |  |  |
| winnings | INT | Non |  |  |
| rake | INT | Non |  |  |
| rakeDealt | decimal | Non |  |  |
| rakeContributed | decimal | Non |  |  |
| rakeWeighted | decimal | Non |  |  |
| totalProfit | INT | Non |  |  |
| allInEV | decimal | Non |  |  |
| showdownWinnings | INT | Non |  |  |
| nonShowdownWinnings | INT | Non |  |  |
| street1CheckCallRaiseChance | INT | Non |  |  |
| street1CheckCallDone | INT | Non |  |  |
| street1CheckRaiseDone | INT | Non |  |  |
| street2CheckCallRaiseChance | INT | Non |  |  |
| street2CheckCallDone | INT | Non |  |  |
| street2CheckRaiseDone | INT | Non |  |  |
| street3CheckCallRaiseChance | INT | Non |  |  |
| street3CheckCallDone | INT | Non |  |  |
| street3CheckRaiseDone | INT | Non |  |  |
| street4CheckCallRaiseChance | INT | Non |  |  |
| street4CheckCallDone | INT | Non |  |  |
| street4CheckRaiseDone | INT | Non |  |  |
| street0Calls | INT | Non |  |  |
| street1Calls | INT | Non |  |  |
| street2Calls | INT | Non |  |  |
| street3Calls | INT | Non |  |  |
| street4Calls | INT | Non |  |  |
| street0Bets | INT | Non |  |  |
| street1Bets | INT | Non |  |  |
| street2Bets | INT | Non |  |  |
| street3Bets | INT | Non |  |  |
| street4Bets | INT | Non |  |  |
| street0Raises | INT | Non |  |  |
| street1Raises | INT | Non |  |  |
| street2Raises | INT | Non |  |  |
| street3Raises | INT | Non |  |  |
| street4Raises | INT | Non |  |  |
| street1Discards | INT | Non |  |  |
| street2Discards | INT | Non |  |  |
| street3Discards | INT | Non |  |  |

### Index

* `SessionsCache_playerId_idx` : playerId
* `SessionsCache_gametypeId_idx` : gametypeId
* `SessionsCache_sessionId_idx` : sessionId
* `SessionsCache_Compound_idx` : gametypeId, playerId

## Settings

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| version | INTEGER | Oui |  |  |

## Sites

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| name | TEXT | Oui |  |  |
| code | TEXT | Oui |  |  |

## StartCards

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| category | TEXT | Oui |  |  |
| name | TEXT | Oui |  |  |
| rank | SMALLINT | Oui |  |  |
| combinations | SMALLINT | Oui |  |  |

### Index

* `cards_idx` UNIQUE : category, rank

## TourneyTypes

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| siteId | INT | Oui |  |  |
| currency | VARCHAR(4) | Non |  |  |
| buyin | INT | Non |  |  |
| fee | INT | Non |  |  |
| category | TEXT | Non |  |  |
| limitType | TEXT | Non |  |  |
| buyInChips | INT | Non |  |  |
| stack | VARCHAR(8) | Non |  |  |
| maxSeats | INT | Non |  |  |
| rebuy | BOOLEAN | Non |  |  |
| rebuyCost | INT | Non |  |  |
| rebuyFee | INT | Non |  |  |
| rebuyChips | INT | Non |  |  |
| addOn | BOOLEAN | Non |  |  |
| addOnCost | INT | Non |  |  |
| addOnFee | INT | Non |  |  |
| addOnChips | INT | Non |  |  |
| knockout | BOOLEAN | Non |  |  |
| koBounty | INT | Non |  |  |
| progressive | BOOLEAN | Non |  |  |
| step | BOOLEAN | Non |  |  |
| stepNo | INT | Non |  |  |
| chance | BOOLEAN | Non |  |  |
| chanceCount | INT | Non |  |  |
| speed | TEXT | Non |  |  |
| shootout | BOOLEAN | Non |  |  |
| matrix | BOOLEAN | Non |  |  |
| multiEntry | BOOLEAN | Non |  |  |
| reEntry | BOOLEAN | Non |  |  |
| fast | BOOLEAN | Non |  |  |
| newToGame | BOOLEAN | Non |  |  |
| homeGame | BOOLEAN | Non |  |  |
| split | BOOLEAN | Non |  |  |
| sng | BOOLEAN | Non |  |  |
| fifty50 | BOOLEAN | Non |  |  |
| time | BOOLEAN | Non |  |  |
| timeAmt | INT | Non |  |  |
| satellite | BOOLEAN | Non |  |  |
| doubleOrNothing | BOOLEAN | Non |  |  |
| cashOut | BOOLEAN | Non |  |  |
| onDemand | BOOLEAN | Non |  |  |
| flighted | BOOLEAN | Non |  |  |
| guarantee | BOOLEAN | Non |  |  |
| guaranteeAmt | INT | Non |  |  |
| lottery | BOOLEAN | Non |  | FALSE |
| multiplier | INT | Non |  | 1 |

### Index

* `TourneyTypes_siteId_idx` : siteId

## Tourneys

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| tourneyTypeId | INT | Non |  |  |
| sessionId | INT | Non |  |  |
| siteTourneyNo | INT | Non |  |  |
| entries | INT | Non |  |  |
| prizepool | INT | Non |  |  |
| startTime | timestamp | Non |  |  |
| endTime | timestamp | Non |  |  |
| tourneyName | TEXT | Non |  |  |
| totalRebuyCount | INT | Non |  |  |
| totalAddOnCount | INT | Non |  |  |
| added | INT | Non |  |  |
| addedCurrency | VARCHAR(4) | Non |  |  |
| comment | TEXT | Non |  |  |
| commentTs | timestamp | Non |  |  |

### Index

* `Tourneys_sessionId_idx` : sessionId
* `Tourneys_tourneyTypeId_idx` : tourneyTypeId
* `siteTourneyNo` UNIQUE : siteTourneyNo, tourneyTypeId

## TourneysCache

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| sessionId | INT | Non |  |  |
| startTime | timestamp | Oui |  |  |
| endTime | timestamp | Oui |  |  |
| tourneyId | INT | Non |  |  |
| playerId | INT | Non |  |  |
| n | INT | Non |  |  |
| street0VPIChance | INT | Non |  |  |
| street0VPI | INT | Non |  |  |
| street0AggrChance | INT | Non |  |  |
| street0Aggr | INT | Non |  |  |
| street0CalledRaiseChance | INT | Non |  |  |
| street0CalledRaiseDone | INT | Non |  |  |
| street0_2BChance | INT | Non |  |  |
| street0_2BDone | INT | Non |  |  |
| street0_3BChance | INT | Non |  |  |
| street0_3BDone | INT | Non |  |  |
| street0_4BChance | INT | Non |  |  |
| street0_4BDone | INT | Non |  |  |
| street0_C4BChance | INT | Non |  |  |
| street0_C4BDone | INT | Non |  |  |
| street0_FoldTo2BChance | INT | Non |  |  |
| street0_FoldTo2BDone | INT | Non |  |  |
| street0_FoldTo3BChance | INT | Non |  |  |
| street0_FoldTo3BDone | INT | Non |  |  |
| street0_FoldTo4BChance | INT | Non |  |  |
| street0_FoldTo4BDone | INT | Non |  |  |
| street0_SqueezeChance | INT | Non |  |  |
| street0_SqueezeDone | INT | Non |  |  |
| raiseToStealChance | INT | Non |  |  |
| raiseToStealDone | INT | Non |  |  |
| stealChance | INT | Non |  |  |
| stealDone | INT | Non |  |  |
| success_Steal | INT | Non |  |  |
| street1Seen | INT | Non |  |  |
| street2Seen | INT | Non |  |  |
| street3Seen | INT | Non |  |  |
| street4Seen | INT | Non |  |  |
| sawShowdown | INT | Non |  |  |
| street1Aggr | INT | Non |  |  |
| street2Aggr | INT | Non |  |  |
| street3Aggr | INT | Non |  |  |
| street4Aggr | INT | Non |  |  |
| otherRaisedStreet0 | INT | Non |  |  |
| otherRaisedStreet1 | INT | Non |  |  |
| otherRaisedStreet2 | INT | Non |  |  |
| otherRaisedStreet3 | INT | Non |  |  |
| otherRaisedStreet4 | INT | Non |  |  |
| foldToOtherRaisedStreet0 | INT | Non |  |  |
| foldToOtherRaisedStreet1 | INT | Non |  |  |
| foldToOtherRaisedStreet2 | INT | Non |  |  |
| foldToOtherRaisedStreet3 | INT | Non |  |  |
| foldToOtherRaisedStreet4 | INT | Non |  |  |
| wonWhenSeenStreet1 | INT | Non |  |  |
| wonWhenSeenStreet2 | INT | Non |  |  |
| wonWhenSeenStreet3 | INT | Non |  |  |
| wonWhenSeenStreet4 | INT | Non |  |  |
| wonAtSD | INT | Non |  |  |
| raiseFirstInChance | INT | Non |  |  |
| raisedFirstIn | INT | Non |  |  |
| foldBbToStealChance | INT | Non |  |  |
| foldedBbToSteal | INT | Non |  |  |
| foldSbToStealChance | INT | Non |  |  |
| foldedSbToSteal | INT | Non |  |  |
| street1CBChance | INT | Non |  |  |
| street1CBDone | INT | Non |  |  |
| street2CBChance | INT | Non |  |  |
| street2CBDone | INT | Non |  |  |
| street3CBChance | INT | Non |  |  |
| street3CBDone | INT | Non |  |  |
| street4CBChance | INT | Non |  |  |
| street4CBDone | INT | Non |  |  |
| foldToStreet1CBChance | INT | Non |  |  |
| foldToStreet1CBDone | INT | Non |  |  |
| foldToStreet2CBChance | INT | Non |  |  |
| foldToStreet2CBDone | INT | Non |  |  |
| foldToStreet3CBChance | INT | Non |  |  |
| foldToStreet3CBDone | INT | Non |  |  |
| foldToStreet4CBChance | INT | Non |  |  |
| foldToStreet4CBDone | INT | Non |  |  |
| common | INT | Non |  |  |
| committed | INT | Non |  |  |
| winnings | INT | Non |  |  |
| rake | INT | Non |  |  |
| rakeDealt | decimal | Non |  |  |
| rakeContributed | decimal | Non |  |  |
| rakeWeighted | decimal | Non |  |  |
| totalProfit | INT | Non |  |  |
| allInEV | decimal | Non |  |  |
| showdownWinnings | INT | Non |  |  |
| nonShowdownWinnings | INT | Non |  |  |
| street1CheckCallRaiseChance | INT | Non |  |  |
| street1CheckCallDone | INT | Non |  |  |
| street1CheckRaiseDone | INT | Non |  |  |
| street2CheckCallRaiseChance | INT | Non |  |  |
| street2CheckCallDone | INT | Non |  |  |
| street2CheckRaiseDone | INT | Non |  |  |
| street3CheckCallRaiseChance | INT | Non |  |  |
| street3CheckCallDone | INT | Non |  |  |
| street3CheckRaiseDone | INT | Non |  |  |
| street4CheckCallRaiseChance | INT | Non |  |  |
| street4CheckCallDone | INT | Non |  |  |
| street4CheckRaiseDone | INT | Non |  |  |
| street0Calls | INT | Non |  |  |
| street1Calls | INT | Non |  |  |
| street2Calls | INT | Non |  |  |
| street3Calls | INT | Non |  |  |
| street4Calls | INT | Non |  |  |
| street0Bets | INT | Non |  |  |
| street1Bets | INT | Non |  |  |
| street2Bets | INT | Non |  |  |
| street3Bets | INT | Non |  |  |
| street4Bets | INT | Non |  |  |
| street0Raises | INT | Non |  |  |
| street1Raises | INT | Non |  |  |
| street2Raises | INT | Non |  |  |
| street3Raises | INT | Non |  |  |
| street4Raises | INT | Non |  |  |
| street1Discards | INT | Non |  |  |
| street2Discards | INT | Non |  |  |
| street3Discards | INT | Non |  |  |

### Index

* `TourneysCache_playerId_idx` : playerId
* `TourneysCache_tourneyId_idx` : tourneyId
* `TourneysCache_sessionId_idx` : sessionId
* `TourneysCache_Compound_idx` UNIQUE : tourneyId, playerId

## TourneysPlayers

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| tourneyId | INT | Non |  |  |
| playerId | INT | Non |  |  |
| entryId | INT | Non |  |  |
| rank | INT | Non |  |  |
| winnings | INT | Non |  |  |
| winningsCurrency | VARCHAR(4) | Non |  |  |
| rebuyCount | INT | Non |  |  |
| addOnCount | INT | Non |  |  |
| koCount | decimal | Non |  |  |
| comment | TEXT | Non |  |  |
| commentTs | timestamp | Non |  |  |

### Clés étrangères

| Colonne | Référence | ON UPDATE | ON DELETE |
|---------|-----------|-----------|-----------|
| playerId | Players(id) | NO ACTION | NO ACTION |
| tourneyId | Tourneys(id) | NO ACTION | NO ACTION |

### Index

* `TourneysPlayers_playerId_idx` : playerId
* `tourneyId` UNIQUE : tourneyId, playerId, entryId

## Weeks

### Colonnes

| Nom | Type | NOT NULL | PK | Défaut |
|-----|------|----------|----|--------|
| id | INTEGER | Non | 1 |  |
| weekStart | timestamp | Oui |  |  |

