free poker database 
[('Actions',), ('Autorates',), ('Backings',), ('Boards',), ('CardsCache',), ('Files',), ('Gametypes',), ('Hands',), ('HandsActions',), ('HandsPlayers',), ('HandsPots',), ('HandsStove',), ('HudCache',), ('Months',), ('Players',), ('PositionsCache',), ('Rank',), ('RawHands',), ('RawTourneys',), ('Sessions',), ('SessionsCache',), ('Settings',), ('Sites',), ('StartCards',), ('TourneyTypes',), ('Tourneys',), ('TourneysCache',), ('TourneysPlayers',), ('Weeks',), ('sqlite_stat1',)]

Actions:
|   cid | name   | type    |   notnull | dflt_value   |   pk |
|------:|:-------|:--------|----------:|:-------------|-----:|
|     0 | id     | INTEGER |         0 |              |    1 |
|     1 | name   | TEXT    |         1 |              |    0 |
|     2 | code   | TEXT    |         1 |              |    0 |


Autorates:
|   cid | name        | type      |   notnull | dflt_value   |   pk |
|------:|:------------|:----------|----------:|:-------------|-----:|
|     0 | id          | INTEGER   |         0 |              |    1 |
|     1 | playerId    | INT       |         0 |              |    0 |
|     2 | gametypeId  | INT       |         0 |              |    0 |
|     3 | description | TEXT      |         0 |              |    0 |
|     4 | shortDesc   | TEXT      |         0 |              |    0 |
|     5 | ratingTime  | timestamp |         0 |              |    0 |
|     6 | handCount   | INT       |         0 |              |    0 |


Backings:
|   cid | name              | type          |   notnull | dflt_value   |   pk |
|------:|:------------------|:--------------|----------:|:-------------|-----:|
|     0 | id                | INTEGER       |         0 |              |    1 |
|     1 | tourneysPlayersId | INT           |         1 |              |    0 |
|     2 | playerId          | INT           |         1 |              |    0 |
|     3 | buyInPercentage   | REAL UNSIGNED |         1 |              |    0 |
|     4 | payOffPercentage  | REAL UNSIGNED |         1 |              |    0 |

Boards:
|   cid | name       | type    |   notnull | dflt_value   |   pk |
|------:|:-----------|:--------|----------:|:-------------|-----:|
|     0 | id         | INTEGER |         0 |              |    1 |
|     1 | handId     | INT     |         1 |              |    0 |
|     2 | boardId    | INT     |         0 |              |    0 |
|     3 | boardcard1 | INT     |         0 |              |    0 |
|     4 | boardcard2 | INT     |         0 |              |    0 |
|     5 | boardcard3 | INT     |         0 |              |    0 |
|     6 | boardcard4 | INT     |         0 |              |    0 |
|     7 | boardcard5 | INT     |         0 |              |    0 |

CardsCache:
|   cid | name                        | type    |   notnull | dflt_value   |   pk |
|------:|:----------------------------|:--------|----------:|:-------------|-----:|
|     0 | id                          | INTEGER |         0 |              |    1 |
|     1 | weekId                      | INT     |         0 |              |    0 |
|     2 | monthId                     | INT     |         0 |              |    0 |
|     3 | gametypeId                  | INT     |         0 |              |    0 |
|     4 | tourneyTypeId               | INT     |         0 |              |    0 |
|     5 | playerId                    | INT     |         0 |              |    0 |
|     6 | startCards                  | INT     |         0 |              |    0 |
|     7 | n                           | INT     |         0 |              |    0 |
|     8 | street0VPIChance            | INT     |         0 |              |    0 |
|     9 | street0VPI                  | INT     |         0 |              |    0 |
|    10 | street0AggrChance           | INT     |         0 |              |    0 |
|    11 | street0Aggr                 | INT     |         0 |              |    0 |
|    12 | street0CalledRaiseChance    | INT     |         0 |              |    0 |
|    13 | street0CalledRaiseDone      | INT     |         0 |              |    0 |
|    14 | street0_2BChance            | INT     |         0 |              |    0 |
|    15 | street0_2BDone              | INT     |         0 |              |    0 |
|    16 | street0_3BChance            | INT     |         0 |              |    0 |
|    17 | street0_3BDone              | INT     |         0 |              |    0 |
|    18 | street0_4BChance            | INT     |         0 |              |    0 |
|    19 | street0_4BDone              | INT     |         0 |              |    0 |
|    20 | street0_C4BChance           | INT     |         0 |              |    0 |
|    21 | street0_C4BDone             | INT     |         0 |              |    0 |
|    22 | street0_FoldTo2BChance      | INT     |         0 |              |    0 |
|    23 | street0_FoldTo2BDone        | INT     |         0 |              |    0 |
|    24 | street0_FoldTo3BChance      | INT     |         0 |              |    0 |
|    25 | street0_FoldTo3BDone        | INT     |         0 |              |    0 |
|    26 | street0_FoldTo4BChance      | INT     |         0 |              |    0 |
|    27 | street0_FoldTo4BDone        | INT     |         0 |              |    0 |
|    28 | street0_SqueezeChance       | INT     |         0 |              |    0 |
|    29 | street0_SqueezeDone         | INT     |         0 |              |    0 |
|    30 | raiseToStealChance          | INT     |         0 |              |    0 |
|    31 | raiseToStealDone            | INT     |         0 |              |    0 |
|    32 | stealChance                 | INT     |         0 |              |    0 |
|    33 | stealDone                   | INT     |         0 |              |    0 |
|    34 | success_Steal               | INT     |         0 |              |    0 |
|    35 | street1Seen                 | INT     |         0 |              |    0 |
|    36 | street2Seen                 | INT     |         0 |              |    0 |
|    37 | street3Seen                 | INT     |         0 |              |    0 |
|    38 | street4Seen                 | INT     |         0 |              |    0 |
|    39 | sawShowdown                 | INT     |         0 |              |    0 |
|    40 | street1Aggr                 | INT     |         0 |              |    0 |
|    41 | street2Aggr                 | INT     |         0 |              |    0 |
|    42 | street3Aggr                 | INT     |         0 |              |    0 |
|    43 | street4Aggr                 | INT     |         0 |              |    0 |
|    44 | otherRaisedStreet0          | INT     |         0 |              |    0 |
|    45 | otherRaisedStreet1          | INT     |         0 |              |    0 |
|    46 | otherRaisedStreet2          | INT     |         0 |              |    0 |
|    47 | otherRaisedStreet3          | INT     |         0 |              |    0 |
|    48 | otherRaisedStreet4          | INT     |         0 |              |    0 |
|    49 | foldToOtherRaisedStreet0    | INT     |         0 |              |    0 |
|    50 | foldToOtherRaisedStreet1    | INT     |         0 |              |    0 |
|    51 | foldToOtherRaisedStreet2    | INT     |         0 |              |    0 |
|    52 | foldToOtherRaisedStreet3    | INT     |         0 |              |    0 |
|    53 | foldToOtherRaisedStreet4    | INT     |         0 |              |    0 |
|    54 | wonWhenSeenStreet1          | INT     |         0 |              |    0 |
|    55 | wonWhenSeenStreet2          | INT     |         0 |              |    0 |
|    56 | wonWhenSeenStreet3          | INT     |         0 |              |    0 |
|    57 | wonWhenSeenStreet4          | INT     |         0 |              |    0 |
|    58 | wonAtSD                     | INT     |         0 |              |    0 |
|    59 | raiseFirstInChance          | INT     |         0 |              |    0 |
|    60 | raisedFirstIn               | INT     |         0 |              |    0 |
|    61 | foldBbToStealChance         | INT     |         0 |              |    0 |
|    62 | foldedBbToSteal             | INT     |         0 |              |    0 |
|    63 | foldSbToStealChance         | INT     |         0 |              |    0 |
|    64 | foldedSbToSteal             | INT     |         0 |              |    0 |
|    65 | street1CBChance             | INT     |         0 |              |    0 |
|    66 | street1CBDone               | INT     |         0 |              |    0 |
|    67 | street2CBChance             | INT     |         0 |              |    0 |
|    68 | street2CBDone               | INT     |         0 |              |    0 |
|    69 | street3CBChance             | INT     |         0 |              |    0 |
|    70 | street3CBDone               | INT     |         0 |              |    0 |
|    71 | street4CBChance             | INT     |         0 |              |    0 |
|    72 | street4CBDone               | INT     |         0 |              |    0 |
|    73 | foldToStreet1CBChance       | INT     |         0 |              |    0 |
|    74 | foldToStreet1CBDone         | INT     |         0 |              |    0 |
|    75 | foldToStreet2CBChance       | INT     |         0 |              |    0 |
|    76 | foldToStreet2CBDone         | INT     |         0 |              |    0 |
|    77 | foldToStreet3CBChance       | INT     |         0 |              |    0 |
|    78 | foldToStreet3CBDone         | INT     |         0 |              |    0 |
|    79 | foldToStreet4CBChance       | INT     |         0 |              |    0 |
|    80 | foldToStreet4CBDone         | INT     |         0 |              |    0 |
|    81 | common                      | INT     |         0 |              |    0 |
|    82 | committed                   | INT     |         0 |              |    0 |
|    83 | winnings                    | INT     |         0 |              |    0 |
|    84 | rake                        | INT     |         0 |              |    0 |
|    85 | rakeDealt                   | decimal |         0 |              |    0 |
|    86 | rakeContributed             | decimal |         0 |              |    0 |
|    87 | rakeWeighted                | decimal |         0 |              |    0 |
|    88 | totalProfit                 | INT     |         0 |              |    0 |
|    89 | allInEV                     | decimal |         0 |              |    0 |
|    90 | showdownWinnings            | INT     |         0 |              |    0 |
|    91 | nonShowdownWinnings         | INT     |         0 |              |    0 |
|    92 | street1CheckCallRaiseChance | INT     |         0 |              |    0 |
|    93 | street1CheckCallDone        | INT     |         0 |              |    0 |
|    94 | street1CheckRaiseDone       | INT     |         0 |              |    0 |
|    95 | street2CheckCallRaiseChance | INT     |         0 |              |    0 |
|    96 | street2CheckCallDone        | INT     |         0 |              |    0 |
|    97 | street2CheckRaiseDone       | INT     |         0 |              |    0 |
|    98 | street3CheckCallRaiseChance | INT     |         0 |              |    0 |
|    99 | street3CheckCallDone        | INT     |         0 |              |    0 |
|   100 | street3CheckRaiseDone       | INT     |         0 |              |    0 |
|   101 | street4CheckCallRaiseChance | INT     |         0 |              |    0 |
|   102 | street4CheckCallDone        | INT     |         0 |              |    0 |
|   103 | street4CheckRaiseDone       | INT     |         0 |              |    0 |
|   104 | street0Calls                | INT     |         0 |              |    0 |
|   105 | street1Calls                | INT     |         0 |              |    0 |
|   106 | street2Calls                | INT     |         0 |              |    0 |
|   107 | street3Calls                | INT     |         0 |              |    0 |
|   108 | street4Calls                | INT     |         0 |              |    0 |
|   109 | street0Bets                 | INT     |         0 |              |    0 |
|   110 | street1Bets                 | INT     |         0 |              |    0 |
|   111 | street2Bets                 | INT     |         0 |              |    0 |
|   112 | street3Bets                 | INT     |         0 |              |    0 |
|   113 | street4Bets                 | INT     |         0 |              |    0 |
|   114 | street0Raises               | INT     |         0 |              |    0 |
|   115 | street1Raises               | INT     |         0 |              |    0 |
|   116 | street2Raises               | INT     |         0 |              |    0 |
|   117 | street3Raises               | INT     |         0 |              |    0 |
|   118 | street4Raises               | INT     |         0 |              |    0 |
|   119 | street1Discards             | INT     |         0 |              |    0 |
|   120 | street2Discards             | INT     |         0 |              |    0 |
|   121 | street3Discards             | INT     |         0 |              |    0 |

Files:
|   cid | name        | type        |   notnull | dflt_value   |   pk |
|------:|:------------|:------------|----------:|:-------------|-----:|
|     0 | id          | INTEGER     |         0 |              |    1 |
|     1 | file        | TEXT        |         1 |              |    0 |
|     2 | site        | VARCHAR(32) |         0 |              |    0 |
|     3 | type        | VARCHAR(7)  |         0 |              |    0 |
|     4 | startTime   | timestamp   |         1 |              |    0 |
|     5 | lastUpdate  | timestamp   |         1 |              |    0 |
|     6 | endTime     | timestamp   |         0 |              |    0 |
|     7 | hands       | INT         |         0 |              |    0 |
|     8 | storedHands | INT         |         0 |              |    0 |
|     9 | dups        | INT         |         0 |              |    0 |
|    10 | partial     | INT         |         0 |              |    0 |
|    11 | skipped     | INT         |         0 |              |    0 |
|    12 | errs        | INT         |         0 |              |    0 |
|    13 | ttime100    | INT         |         0 |              |    0 |
|    14 | finished    | BOOLEAN     |         0 |              |    0 |

Gametypes:
|   cid | name       | type    |   notnull | dflt_value   |   pk |
|------:|:-----------|:--------|----------:|:-------------|-----:|
|     0 | id         | INTEGER |         1 |              |    1 |
|     1 | siteId     | INTEGER |         1 |              |    0 |
|     2 | currency   | TEXT    |         1 |              |    0 |
|     3 | type       | TEXT    |         1 |              |    0 |
|     4 | base       | TEXT    |         1 |              |    0 |
|     5 | category   | TEXT    |         1 |              |    0 |
|     6 | limitType  | TEXT    |         1 |              |    0 |
|     7 | hiLo       | TEXT    |         1 |              |    0 |
|     8 | mix        | TEXT    |         1 |              |    0 |
|     9 | smallBlind | INTEGER |         0 |              |    0 |
|    10 | bigBlind   | INTEGER |         0 |              |    0 |
|    11 | smallBet   | INTEGER |         1 |              |    0 |
|    12 | bigBet     | INTEGER |         1 |              |    0 |
|    13 | maxSeats   | INT     |         1 |              |    0 |
|    14 | ante       | INT     |         1 |              |    0 |
|    15 | buyinType  | TEXT    |         1 |              |    0 |
|    16 | fast       | INT     |         0 |              |    0 |
|    17 | newToGame  | INT     |         0 |              |    0 |
|    18 | homeGame   | INT     |         0 |              |    0 |
|    19 | split      | INT     |         0 |              |    0 |

Hands:
|   cid | name              | type      |   notnull | dflt_value   |   pk |
|------:|:------------------|:----------|----------:|:-------------|-----:|
|     0 | id                | INTEGER   |         0 |              |    1 |
|     1 | tableName         | TEXT(50)  |         1 |              |    0 |
|     2 | siteHandNo        | INT       |         1 |              |    0 |
|     3 | tourneyId         | INT       |         0 |              |    0 |
|     4 | gametypeId        | INT       |         1 |              |    0 |
|     5 | sessionId         | INT       |         0 |              |    0 |
|     6 | fileId            | INT       |         1 |              |    0 |
|     7 | startTime         | timestamp |         1 |              |    0 |
|     8 | importTime        | timestamp |         1 |              |    0 |
|     9 | seats             | INT       |         1 |              |    0 |
|    10 | heroSeat          | INT       |         1 |              |    0 |
|    11 | maxPosition       | INT       |         1 |              |    0 |
|    12 | boardcard1        | INT       |         0 |              |    0 |
|    13 | boardcard2        | INT       |         0 |              |    0 |
|    14 | boardcard3        | INT       |         0 |              |    0 |
|    15 | boardcard4        | INT       |         0 |              |    0 |
|    16 | boardcard5        | INT       |         0 |              |    0 |
|    17 | texture           | INT       |         0 |              |    0 |
|    18 | runItTwice        | BOOLEAN   |         0 |              |    0 |
|    19 | playersVpi        | INT       |         1 |              |    0 |
|    20 | playersAtStreet1  | INT       |         1 |              |    0 |
|    21 | playersAtStreet2  | INT       |         1 |              |    0 |
|    22 | playersAtStreet3  | INT       |         1 |              |    0 |
|    23 | playersAtStreet4  | INT       |         1 |              |    0 |
|    24 | playersAtShowdown | INT       |         1 |              |    0 |
|    25 | street0Raises     | INT       |         1 |              |    0 |
|    26 | street1Raises     | INT       |         1 |              |    0 |
|    27 | street2Raises     | INT       |         1 |              |    0 |
|    28 | street3Raises     | INT       |         1 |              |    0 |
|    29 | street4Raises     | INT       |         1 |              |    0 |
|    30 | street0Pot        | INT       |         0 |              |    0 |
|    31 | street1Pot        | INT       |         0 |              |    0 |
|    32 | street2Pot        | INT       |         0 |              |    0 |
|    33 | street3Pot        | INT       |         0 |              |    0 |
|    34 | street4Pot        | INT       |         0 |              |    0 |
|    35 | finalPot          | INT       |         0 |              |    0 |
|    36 | comment           | TEXT      |         0 |              |    0 |
|    37 | commentTs         | timestamp |         0 |              |    0 |

HandsActions:
|   cid | name           | type     |   notnull | dflt_value   |   pk |
|------:|:---------------|:---------|----------:|:-------------|-----:|
|     0 | id             | INTEGER  |         0 |              |    1 |
|     1 | handId         | INT      |         1 |              |    0 |
|     2 | playerId       | INT      |         1 |              |    0 |
|     3 | street         | SMALLINT |         0 |              |    0 |
|     4 | actionNo       | SMALLINT |         0 |              |    0 |
|     5 | streetActionNo | SMALLINT |         0 |              |    0 |
|     6 | actionId       | SMALLINT |         0 |              |    0 |
|     7 | amount         | INT      |         0 |              |    0 |
|     8 | raiseTo        | INT      |         0 |              |    0 |
|     9 | amountCalled   | INT      |         0 |              |    0 |
|    10 | numDiscarded   | SMALLINT |         0 |              |    0 |
|    11 | cardsDiscarded | TEXT     |         0 |              |    0 |
|    12 | allIn          | BOOLEAN  |         0 |              |    0 |

HandsPlayers:
|   cid | name                        | type        |   notnull | dflt_value   |   pk |
|------:|:----------------------------|:------------|----------:|:-------------|-----:|
|     0 | id                          | INTEGER     |         0 |              |    1 |
|     1 | handId                      | INT         |         1 |              |    0 |
|     2 | playerId                    | INT         |         1 |              |    0 |
|     3 | startCash                   | INT         |         1 |              |    0 |
|     4 | effStack                    | INT         |         1 |              |    0 |
|     5 | startBounty                 | INT         |         0 |              |    0 |
|     6 | endBounty                   | INT         |         0 |              |    0 |
|     7 | position                    | TEXT        |         0 |              |    0 |
|     8 | seatNo                      | INT         |         1 |              |    0 |
|     9 | sitout                      | BOOLEAN     |         1 |              |    0 |
|    10 | card1                       | INT         |         1 |              |    0 |
|    11 | card2                       | INT         |         1 |              |    0 |
|    12 | card3                       | INT         |         0 |              |    0 |
|    13 | card4                       | INT         |         0 |              |    0 |
|    14 | card5                       | INT         |         0 |              |    0 |
|    15 | card6                       | INT         |         0 |              |    0 |
|    16 | card7                       | INT         |         0 |              |    0 |
|    17 | card8                       | INT         |         0 |              |    0 |
|    18 | card9                       | INT         |         0 |              |    0 |
|    19 | card10                      | INT         |         0 |              |    0 |
|    20 | card11                      | INT         |         0 |              |    0 |
|    21 | card12                      | INT         |         0 |              |    0 |
|    22 | card13                      | INT         |         0 |              |    0 |
|    23 | card14                      | INT         |         0 |              |    0 |
|    24 | card15                      | INT         |         0 |              |    0 |
|    25 | card16                      | INT         |         0 |              |    0 |
|    26 | card17                      | INT         |         0 |              |    0 |
|    27 | card18                      | INT         |         0 |              |    0 |
|    28 | card19                      | INT         |         0 |              |    0 |
|    29 | card20                      | INT         |         0 |              |    0 |
|    30 | startCards                  | INT         |         0 |              |    0 |
|    31 | common                      | INT         |         1 |              |    0 |
|    32 | committed                   | INT         |         1 |              |    0 |
|    33 | winnings                    | INT         |         1 |              |    0 |
|    34 | rake                        | INT         |         1 |              |    0 |
|    35 | rakeDealt                   | decimal     |         1 |              |    0 |
|    36 | rakeContributed             | decimal     |         1 |              |    0 |
|    37 | rakeWeighted                | decimal     |         1 |              |    0 |
|    38 | totalProfit                 | INT         |         0 |              |    0 |
|    39 | allInEV                     | decimal     |         0 |              |    0 |
|    40 | comment                     | TEXT        |         0 |              |    0 |
|    41 | commentTs                   | timestamp   |         0 |              |    0 |
|    42 | tourneysPlayersId           | INT         |         0 |              |    0 |
|    43 | wonWhenSeenStreet1          | INT         |         0 |              |    0 |
|    44 | wonWhenSeenStreet2          | INT         |         0 |              |    0 |
|    45 | wonWhenSeenStreet3          | INT         |         0 |              |    0 |
|    46 | wonWhenSeenStreet4          | INT         |         0 |              |    0 |
|    47 | wonAtSD                     | INT         |         0 |              |    0 |
|    48 | street0VPIChance            | INT         |         0 |              |    0 |
|    49 | street0VPI                  | INT         |         0 |              |    0 |
|    50 | street0AggrChance           | INT         |         0 |              |    0 |
|    51 | street0Aggr                 | INT         |         0 |              |    0 |
|    52 | street0CalledRaiseChance    | INT         |         0 |              |    0 |
|    53 | street0CalledRaiseDone      | INT         |         0 |              |    0 |
|    54 | street0_2BChance            | INT         |         0 |              |    0 |
|    55 | street0_2BDone              | INT         |         0 |              |    0 |
|    56 | street0_3BChance            | INT         |         0 |              |    0 |
|    57 | street0_3BDone              | INT         |         0 |              |    0 |
|    58 | street0_4BChance            | INT         |         0 |              |    0 |
|    59 | street0_4BDone              | INT         |         0 |              |    0 |
|    60 | street0_C4BChance           | INT         |         0 |              |    0 |
|    61 | street0_C4BDone             | INT         |         0 |              |    0 |
|    62 | street0_FoldTo2BChance      | INT         |         0 |              |    0 |
|    63 | street0_FoldTo2BDone        | INT         |         0 |              |    0 |
|    64 | street0_FoldTo3BChance      | INT         |         0 |              |    0 |
|    65 | street0_FoldTo3BDone        | INT         |         0 |              |    0 |
|    66 | street0_FoldTo4BChance      | INT         |         0 |              |    0 |
|    67 | street0_FoldTo4BDone        | INT         |         0 |              |    0 |
|    68 | street0_SqueezeChance       | INT         |         0 |              |    0 |
|    69 | street0_SqueezeDone         | INT         |         0 |              |    0 |
|    70 | raiseToStealChance          | INT         |         0 |              |    0 |
|    71 | raiseToStealDone            | INT         |         0 |              |    0 |
|    72 | stealChance                 | INT         |         0 |              |    0 |
|    73 | stealDone                   | INT         |         0 |              |    0 |
|    74 | success_Steal               | INT         |         0 |              |    0 |
|    75 | street1Seen                 | INT         |         0 |              |    0 |
|    76 | street2Seen                 | INT         |         0 |              |    0 |
|    77 | street3Seen                 | INT         |         0 |              |    0 |
|    78 | street4Seen                 | INT         |         0 |              |    0 |
|    79 | sawShowdown                 | INT         |         0 |              |    0 |
|    80 | showed                      | INT         |         0 |              |    0 |
|    81 | street0AllIn                | INT         |         0 |              |    0 |
|    82 | street1AllIn                | INT         |         0 |              |    0 |
|    83 | street2AllIn                | INT         |         0 |              |    0 |
|    84 | street3AllIn                | INT         |         0 |              |    0 |
|    85 | street4AllIn                | INT         |         0 |              |    0 |
|    86 | wentAllIn                   | INT         |         0 |              |    0 |
|    87 | street0InPosition           | INT         |         0 |              |    0 |
|    88 | street1InPosition           | INT         |         0 |              |    0 |
|    89 | street2InPosition           | INT         |         0 |              |    0 |
|    90 | street3InPosition           | INT         |         0 |              |    0 |
|    91 | street4InPosition           | INT         |         0 |              |    0 |
|    92 | street0FirstToAct           | INT         |         0 |              |    0 |
|    93 | street1FirstToAct           | INT         |         0 |              |    0 |
|    94 | street2FirstToAct           | INT         |         0 |              |    0 |
|    95 | street3FirstToAct           | INT         |         0 |              |    0 |
|    96 | street4FirstToAct           | INT         |         0 |              |    0 |
|    97 | street1Aggr                 | INT         |         0 |              |    0 |
|    98 | street2Aggr                 | INT         |         0 |              |    0 |
|    99 | street3Aggr                 | INT         |         0 |              |    0 |
|   100 | street4Aggr                 | INT         |         0 |              |    0 |
|   101 | otherRaisedStreet0          | INT         |         0 |              |    0 |
|   102 | otherRaisedStreet1          | INT         |         0 |              |    0 |
|   103 | otherRaisedStreet2          | INT         |         0 |              |    0 |
|   104 | otherRaisedStreet3          | INT         |         0 |              |    0 |
|   105 | otherRaisedStreet4          | INT         |         0 |              |    0 |
|   106 | foldToOtherRaisedStreet0    | INT         |         0 |              |    0 |
|   107 | foldToOtherRaisedStreet1    | INT         |         0 |              |    0 |
|   108 | foldToOtherRaisedStreet2    | INT         |         0 |              |    0 |
|   109 | foldToOtherRaisedStreet3    | INT         |         0 |              |    0 |
|   110 | foldToOtherRaisedStreet4    | INT         |         0 |              |    0 |
|   111 | raiseFirstInChance          | INT         |         0 |              |    0 |
|   112 | raisedFirstIn               | INT         |         0 |              |    0 |
|   113 | foldBbToStealChance         | INT         |         0 |              |    0 |
|   114 | foldedBbToSteal             | INT         |         0 |              |    0 |
|   115 | foldSbToStealChance         | INT         |         0 |              |    0 |
|   116 | foldedSbToSteal             | INT         |         0 |              |    0 |
|   117 | street1CBChance             | INT         |         0 |              |    0 |
|   118 | street1CBDone               | INT         |         0 |              |    0 |
|   119 | street2CBChance             | INT         |         0 |              |    0 |
|   120 | street2CBDone               | INT         |         0 |              |    0 |
|   121 | street3CBChance             | INT         |         0 |              |    0 |
|   122 | street3CBDone               | INT         |         0 |              |    0 |
|   123 | street4CBChance             | INT         |         0 |              |    0 |
|   124 | street4CBDone               | INT         |         0 |              |    0 |
|   125 | foldToStreet1CBChance       | INT         |         0 |              |    0 |
|   126 | foldToStreet1CBDone         | INT         |         0 |              |    0 |
|   127 | foldToStreet2CBChance       | INT         |         0 |              |    0 |
|   128 | foldToStreet2CBDone         | INT         |         0 |              |    0 |
|   129 | foldToStreet3CBChance       | INT         |         0 |              |    0 |
|   130 | foldToStreet3CBDone         | INT         |         0 |              |    0 |
|   131 | foldToStreet4CBChance       | INT         |         0 |              |    0 |
|   132 | foldToStreet4CBDone         | INT         |         0 |              |    0 |
|   133 | street1CheckCallRaiseChance | INT         |         0 |              |    0 |
|   134 | street1CheckCallDone        | INT         |         0 |              |    0 |
|   135 | street1CheckRaiseDone       | INT         |         0 |              |    0 |
|   136 | street2CheckCallRaiseChance | INT         |         0 |              |    0 |
|   137 | street2CheckCallDone        | INT         |         0 |              |    0 |
|   138 | street2CheckRaiseDone       | INT         |         0 |              |    0 |
|   139 | street3CheckCallRaiseChance | INT         |         0 |              |    0 |
|   140 | street3CheckCallDone        | INT         |         0 |              |    0 |
|   141 | street3CheckRaiseDone       | INT         |         0 |              |    0 |
|   142 | street4CheckCallRaiseChance | INT         |         0 |              |    0 |
|   143 | street4CheckCallDone        | INT         |         0 |              |    0 |
|   144 | street4CheckRaiseDone       | INT         |         0 |              |    0 |
|   145 | street0Calls                | INT         |         0 |              |    0 |
|   146 | street1Calls                | INT         |         0 |              |    0 |
|   147 | street2Calls                | INT         |         0 |              |    0 |
|   148 | street3Calls                | INT         |         0 |              |    0 |
|   149 | street4Calls                | INT         |         0 |              |    0 |
|   150 | street0Bets                 | INT         |         0 |              |    0 |
|   151 | street1Bets                 | INT         |         0 |              |    0 |
|   152 | street2Bets                 | INT         |         0 |              |    0 |
|   153 | street3Bets                 | INT         |         0 |              |    0 |
|   154 | street4Bets                 | INT         |         0 |              |    0 |
|   155 | street0Raises               | INT         |         0 |              |    0 |
|   156 | street1Raises               | INT         |         0 |              |    0 |
|   157 | street2Raises               | INT         |         0 |              |    0 |
|   158 | street3Raises               | INT         |         0 |              |    0 |
|   159 | street4Raises               | INT         |         0 |              |    0 |
|   160 | street1Discards             | INT         |         0 |              |    0 |
|   161 | street2Discards             | INT         |         0 |              |    0 |
|   162 | street3Discards             | INT         |         0 |              |    0 |
|   163 | handString                  | TEXT        |         0 |              |    0 |
|   164 | actionString                | VARCHAR(15) |         0 |              |    0 |

HandsPots:
|   cid | name      | type    |   notnull | dflt_value   |   pk |
|------:|:----------|:--------|----------:|:-------------|-----:|
|     0 | id        | INTEGER |         0 |              |    1 |
|     1 | handId    | INT     |         1 |              |    0 |
|     2 | potId     | INT     |         0 |              |    0 |
|     3 | boardId   | INT     |         0 |              |    0 |
|     4 | hiLo      | TEXT    |         1 |              |    0 |
|     5 | playerId  | INT     |         1 |              |    0 |
|     6 | pot       | INT     |         0 |              |    0 |
|     7 | collected | INT     |         0 |              |    0 |
|     8 | rake      | INT     |         0 |              |    0 |

HandsStove:
|   cid | name     | type    |   notnull | dflt_value   |   pk |
|------:|:---------|:--------|----------:|:-------------|-----:|
|     0 | id       | INTEGER |         0 |              |    1 |
|     1 | handId   | INT     |         1 |              |    0 |
|     2 | playerId | INT     |         1 |              |    0 |
|     3 | streetId | INT     |         0 |              |    0 |
|     4 | boardId  | INT     |         0 |              |    0 |
|     5 | hiLo     | TEXT    |         1 |              |    0 |
|     6 | rankId   | INT     |         0 |              |    0 |
|     7 | value    | INT     |         0 |              |    0 |
|     8 | cards    | TEXT    |         0 |              |    0 |
|     9 | ev       | decimal |         0 |              |    0 |

HudCache:
|   cid | name                        | type    |   notnull | dflt_value   |   pk |
|------:|:----------------------------|:--------|----------:|:-------------|-----:|
|     0 | id                          | INTEGER |         0 |              |    1 |
|     1 | gametypeId                  | INT     |         0 |              |    0 |
|     2 | playerId                    | INT     |         0 |              |    0 |
|     3 | seats                       | INT     |         0 |              |    0 |
|     4 | position                    | TEXT    |         0 |              |    0 |
|     5 | tourneyTypeId               | INT     |         0 |              |    0 |
|     6 | styleKey                    | TEXT    |         1 |              |    0 |
|     7 | n                           | INT     |         0 |              |    0 |
|     8 | street0VPIChance            | INT     |         0 |              |    0 |
|     9 | street0VPI                  | INT     |         0 |              |    0 |
|    10 | street0AggrChance           | INT     |         0 |              |    0 |
|    11 | street0Aggr                 | INT     |         0 |              |    0 |
|    12 | street0CalledRaiseChance    | INT     |         0 |              |    0 |
|    13 | street0CalledRaiseDone      | INT     |         0 |              |    0 |
|    14 | street0_2BChance            | INT     |         0 |              |    0 |
|    15 | street0_2BDone              | INT     |         0 |              |    0 |
|    16 | street0_3BChance            | INT     |         0 |              |    0 |
|    17 | street0_3BDone              | INT     |         0 |              |    0 |
|    18 | street0_4BChance            | INT     |         0 |              |    0 |
|    19 | street0_4BDone              | INT     |         0 |              |    0 |
|    20 | street0_C4BChance           | INT     |         0 |              |    0 |
|    21 | street0_C4BDone             | INT     |         0 |              |    0 |
|    22 | street0_FoldTo2BChance      | INT     |         0 |              |    0 |
|    23 | street0_FoldTo2BDone        | INT     |         0 |              |    0 |
|    24 | street0_FoldTo3BChance      | INT     |         0 |              |    0 |
|    25 | street0_FoldTo3BDone        | INT     |         0 |              |    0 |
|    26 | street0_FoldTo4BChance      | INT     |         0 |              |    0 |
|    27 | street0_FoldTo4BDone        | INT     |         0 |              |    0 |
|    28 | street0_SqueezeChance       | INT     |         0 |              |    0 |
|    29 | street0_SqueezeDone         | INT     |         0 |              |    0 |
|    30 | raiseToStealChance          | INT     |         0 |              |    0 |
|    31 | raiseToStealDone            | INT     |         0 |              |    0 |
|    32 | stealChance                 | INT     |         0 |              |    0 |
|    33 | stealDone                   | INT     |         0 |              |    0 |
|    34 | success_Steal               | INT     |         0 |              |    0 |
|    35 | street1Seen                 | INT     |         0 |              |    0 |
|    36 | street2Seen                 | INT     |         0 |              |    0 |
|    37 | street3Seen                 | INT     |         0 |              |    0 |
|    38 | street4Seen                 | INT     |         0 |              |    0 |
|    39 | sawShowdown                 | INT     |         0 |              |    0 |
|    40 | street1Aggr                 | INT     |         0 |              |    0 |
|    41 | street2Aggr                 | INT     |         0 |              |    0 |
|    42 | street3Aggr                 | INT     |         0 |              |    0 |
|    43 | street4Aggr                 | INT     |         0 |              |    0 |
|    44 | otherRaisedStreet0          | INT     |         0 |              |    0 |
|    45 | otherRaisedStreet1          | INT     |         0 |              |    0 |
|    46 | otherRaisedStreet2          | INT     |         0 |              |    0 |
|    47 | otherRaisedStreet3          | INT     |         0 |              |    0 |
|    48 | otherRaisedStreet4          | INT     |         0 |              |    0 |
|    49 | foldToOtherRaisedStreet0    | INT     |         0 |              |    0 |
|    50 | foldToOtherRaisedStreet1    | INT     |         0 |              |    0 |
|    51 | foldToOtherRaisedStreet2    | INT     |         0 |              |    0 |
|    52 | foldToOtherRaisedStreet3    | INT     |         0 |              |    0 |
|    53 | foldToOtherRaisedStreet4    | INT     |         0 |              |    0 |
|    54 | wonWhenSeenStreet1          | INT     |         0 |              |    0 |
|    55 | wonWhenSeenStreet2          | INT     |         0 |              |    0 |
|    56 | wonWhenSeenStreet3          | INT     |         0 |              |    0 |
|    57 | wonWhenSeenStreet4          | INT     |         0 |              |    0 |
|    58 | wonAtSD                     | INT     |         0 |              |    0 |
|    59 | raiseFirstInChance          | INT     |         0 |              |    0 |
|    60 | raisedFirstIn               | INT     |         0 |              |    0 |
|    61 | foldBbToStealChance         | INT     |         0 |              |    0 |
|    62 | foldedBbToSteal             | INT     |         0 |              |    0 |
|    63 | foldSbToStealChance         | INT     |         0 |              |    0 |
|    64 | foldedSbToSteal             | INT     |         0 |              |    0 |
|    65 | street1CBChance             | INT     |         0 |              |    0 |
|    66 | street1CBDone               | INT     |         0 |              |    0 |
|    67 | street2CBChance             | INT     |         0 |              |    0 |
|    68 | street2CBDone               | INT     |         0 |              |    0 |
|    69 | street3CBChance             | INT     |         0 |              |    0 |
|    70 | street3CBDone               | INT     |         0 |              |    0 |
|    71 | street4CBChance             | INT     |         0 |              |    0 |
|    72 | street4CBDone               | INT     |         0 |              |    0 |
|    73 | foldToStreet1CBChance       | INT     |         0 |              |    0 |
|    74 | foldToStreet1CBDone         | INT     |         0 |              |    0 |
|    75 | foldToStreet2CBChance       | INT     |         0 |              |    0 |
|    76 | foldToStreet2CBDone         | INT     |         0 |              |    0 |
|    77 | foldToStreet3CBChance       | INT     |         0 |              |    0 |
|    78 | foldToStreet3CBDone         | INT     |         0 |              |    0 |
|    79 | foldToStreet4CBChance       | INT     |         0 |              |    0 |
|    80 | foldToStreet4CBDone         | INT     |         0 |              |    0 |
|    81 | common                      | INT     |         0 |              |    0 |
|    82 | committed                   | INT     |         0 |              |    0 |
|    83 | winnings                    | INT     |         0 |              |    0 |
|    84 | rake                        | INT     |         0 |              |    0 |
|    85 | rakeDealt                   | decimal |         0 |              |    0 |
|    86 | rakeContributed             | decimal |         0 |              |    0 |
|    87 | rakeWeighted                | decimal |         0 |              |    0 |
|    88 | totalProfit                 | INT     |         0 |              |    0 |
|    89 | allInEV                     | decimal |         0 |              |    0 |
|    90 | showdownWinnings            | INT     |         0 |              |    0 |
|    91 | nonShowdownWinnings         | INT     |         0 |              |    0 |
|    92 | street1CheckCallRaiseChance | INT     |         0 |              |    0 |
|    93 | street1CheckCallDone        | INT     |         0 |              |    0 |
|    94 | street1CheckRaiseDone       | INT     |         0 |              |    0 |
|    95 | street2CheckCallRaiseChance | INT     |         0 |              |    0 |
|    96 | street2CheckCallDone        | INT     |         0 |              |    0 |
|    97 | street2CheckRaiseDone       | INT     |         0 |              |    0 |
|    98 | street3CheckCallRaiseChance | INT     |         0 |              |    0 |
|    99 | street3CheckCallDone        | INT     |         0 |              |    0 |
|   100 | street3CheckRaiseDone       | INT     |         0 |              |    0 |
|   101 | street4CheckCallRaiseChance | INT     |         0 |              |    0 |
|   102 | street4CheckCallDone        | INT     |         0 |              |    0 |
|   103 | street4CheckRaiseDone       | INT     |         0 |              |    0 |
|   104 | street0Calls                | INT     |         0 |              |    0 |
|   105 | street1Calls                | INT     |         0 |              |    0 |
|   106 | street2Calls                | INT     |         0 |              |    0 |
|   107 | street3Calls                | INT     |         0 |              |    0 |
|   108 | street4Calls                | INT     |         0 |              |    0 |
|   109 | street0Bets                 | INT     |         0 |              |    0 |
|   110 | street1Bets                 | INT     |         0 |              |    0 |
|   111 | street2Bets                 | INT     |         0 |              |    0 |
|   112 | street3Bets                 | INT     |         0 |              |    0 |
|   113 | street4Bets                 | INT     |         0 |              |    0 |
|   114 | street0Raises               | INT     |         0 |              |    0 |
|   115 | street1Raises               | INT     |         0 |              |    0 |
|   116 | street2Raises               | INT     |         0 |              |    0 |
|   117 | street3Raises               | INT     |         0 |              |    0 |
|   118 | street4Raises               | INT     |         0 |              |    0 |
|   119 | street1Discards             | INT     |         0 |              |    0 |
|   120 | street2Discards             | INT     |         0 |              |    0 |
|   121 | street3Discards             | INT     |         0 |              |    0 |

Months:
|   cid | name       | type      |   notnull | dflt_value   |   pk |
|------:|:-----------|:----------|----------:|:-------------|-----:|
|     0 | id         | INTEGER   |         0 |              |    1 |
|     1 | monthStart | timestamp |         1 |              |    0 |

Players:
|   cid | name      | type      |   notnull | dflt_value   |   pk |
|------:|:----------|:----------|----------:|:-------------|-----:|
|     0 | id        | INTEGER   |         0 |              |    1 |
|     1 | name      | TEXT      |         0 |              |    0 |
|     2 | siteId    | INTEGER   |         0 |              |    0 |
|     3 | hero      | BOOLEAN   |         0 |              |    0 |
|     4 | chars     | TEXT      |         0 |              |    0 |
|     5 | comment   | TEXT      |         0 |              |    0 |
|     6 | commentTs | timestamp |         0 |              |    0 |

PositionsCache:
|   cid | name                        | type    |   notnull | dflt_value   |   pk |
|------:|:----------------------------|:--------|----------:|:-------------|-----:|
|     0 | id                          | INTEGER |         0 |              |    1 |
|     1 | weekId                      | INT     |         0 |              |    0 |
|     2 | monthId                     | INT     |         0 |              |    0 |
|     3 | gametypeId                  | INT     |         0 |              |    0 |
|     4 | tourneyTypeId               | INT     |         0 |              |    0 |
|     5 | playerId                    | INT     |         0 |              |    0 |
|     6 | seats                       | INT     |         0 |              |    0 |
|     7 | maxPosition                 | INT     |         1 |              |    0 |
|     8 | position                    | TEXT    |         0 |              |    0 |
|     9 | n                           | INT     |         0 |              |    0 |
|    10 | street0VPIChance            | INT     |         0 |              |    0 |
|    11 | street0VPI                  | INT     |         0 |              |    0 |
|    12 | street0AggrChance           | INT     |         0 |              |    0 |
|    13 | street0Aggr                 | INT     |         0 |              |    0 |
|    14 | street0CalledRaiseChance    | INT     |         0 |              |    0 |
|    15 | street0CalledRaiseDone      | INT     |         0 |              |    0 |
|    16 | street0_2BChance            | INT     |         0 |              |    0 |
|    17 | street0_2BDone              | INT     |         0 |              |    0 |
|    18 | street0_3BChance            | INT     |         0 |              |    0 |
|    19 | street0_3BDone              | INT     |         0 |              |    0 |
|    20 | street0_4BChance            | INT     |         0 |              |    0 |
|    21 | street0_4BDone              | INT     |         0 |              |    0 |
|    22 | street0_C4BChance           | INT     |         0 |              |    0 |
|    23 | street0_C4BDone             | INT     |         0 |              |    0 |
|    24 | street0_FoldTo2BChance      | INT     |         0 |              |    0 |
|    25 | street0_FoldTo2BDone        | INT     |         0 |              |    0 |
|    26 | street0_FoldTo3BChance      | INT     |         0 |              |    0 |
|    27 | street0_FoldTo3BDone        | INT     |         0 |              |    0 |
|    28 | street0_FoldTo4BChance      | INT     |         0 |              |    0 |
|    29 | street0_FoldTo4BDone        | INT     |         0 |              |    0 |
|    30 | street0_SqueezeChance       | INT     |         0 |              |    0 |
|    31 | street0_SqueezeDone         | INT     |         0 |              |    0 |
|    32 | raiseToStealChance          | INT     |         0 |              |    0 |
|    33 | raiseToStealDone            | INT     |         0 |              |    0 |
|    34 | stealChance                 | INT     |         0 |              |    0 |
|    35 | stealDone                   | INT     |         0 |              |    0 |
|    36 | success_Steal               | INT     |         0 |              |    0 |
|    37 | street1Seen                 | INT     |         0 |              |    0 |
|    38 | street2Seen                 | INT     |         0 |              |    0 |
|    39 | street3Seen                 | INT     |         0 |              |    0 |
|    40 | street4Seen                 | INT     |         0 |              |    0 |
|    41 | sawShowdown                 | INT     |         0 |              |    0 |
|    42 | street1Aggr                 | INT     |         0 |              |    0 |
|    43 | street2Aggr                 | INT     |         0 |              |    0 |
|    44 | street3Aggr                 | INT     |         0 |              |    0 |
|    45 | street4Aggr                 | INT     |         0 |              |    0 |
|    46 | otherRaisedStreet0          | INT     |         0 |              |    0 |
|    47 | otherRaisedStreet1          | INT     |         0 |              |    0 |
|    48 | otherRaisedStreet2          | INT     |         0 |              |    0 |
|    49 | otherRaisedStreet3          | INT     |         0 |              |    0 |
|    50 | otherRaisedStreet4          | INT     |         0 |              |    0 |
|    51 | foldToOtherRaisedStreet0    | INT     |         0 |              |    0 |
|    52 | foldToOtherRaisedStreet1    | INT     |         0 |              |    0 |
|    53 | foldToOtherRaisedStreet2    | INT     |         0 |              |    0 |
|    54 | foldToOtherRaisedStreet3    | INT     |         0 |              |    0 |
|    55 | foldToOtherRaisedStreet4    | INT     |         0 |              |    0 |
|    56 | wonWhenSeenStreet1          | INT     |         0 |              |    0 |
|    57 | wonWhenSeenStreet2          | INT     |         0 |              |    0 |
|    58 | wonWhenSeenStreet3          | INT     |         0 |              |    0 |
|    59 | wonWhenSeenStreet4          | INT     |         0 |              |    0 |
|    60 | wonAtSD                     | INT     |         0 |              |    0 |
|    61 | raiseFirstInChance          | INT     |         0 |              |    0 |
|    62 | raisedFirstIn               | INT     |         0 |              |    0 |
|    63 | foldBbToStealChance         | INT     |         0 |              |    0 |
|    64 | foldedBbToSteal             | INT     |         0 |              |    0 |
|    65 | foldSbToStealChance         | INT     |         0 |              |    0 |
|    66 | foldedSbToSteal             | INT     |         0 |              |    0 |
|    67 | street1CBChance             | INT     |         0 |              |    0 |
|    68 | street1CBDone               | INT     |         0 |              |    0 |
|    69 | street2CBChance             | INT     |         0 |              |    0 |
|    70 | street2CBDone               | INT     |         0 |              |    0 |
|    71 | street3CBChance             | INT     |         0 |              |    0 |
|    72 | street3CBDone               | INT     |         0 |              |    0 |
|    73 | street4CBChance             | INT     |         0 |              |    0 |
|    74 | street4CBDone               | INT     |         0 |              |    0 |
|    75 | foldToStreet1CBChance       | INT     |         0 |              |    0 |
|    76 | foldToStreet1CBDone         | INT     |         0 |              |    0 |
|    77 | foldToStreet2CBChance       | INT     |         0 |              |    0 |
|    78 | foldToStreet2CBDone         | INT     |         0 |              |    0 |
|    79 | foldToStreet3CBChance       | INT     |         0 |              |    0 |
|    80 | foldToStreet3CBDone         | INT     |         0 |              |    0 |
|    81 | foldToStreet4CBChance       | INT     |         0 |              |    0 |
|    82 | foldToStreet4CBDone         | INT     |         0 |              |    0 |
|    83 | common                      | INT     |         0 |              |    0 |
|    84 | committed                   | INT     |         0 |              |    0 |
|    85 | winnings                    | INT     |         0 |              |    0 |
|    86 | rake                        | INT     |         0 |              |    0 |
|    87 | rakeDealt                   | decimal |         0 |              |    0 |
|    88 | rakeContributed             | decimal |         0 |              |    0 |
|    89 | rakeWeighted                | decimal |         0 |              |    0 |
|    90 | totalProfit                 | INT     |         0 |              |    0 |
|    91 | allInEV                     | decimal |         0 |              |    0 |
|    92 | showdownWinnings            | INT     |         0 |              |    0 |
|    93 | nonShowdownWinnings         | INT     |         0 |              |    0 |
|    94 | street1CheckCallRaiseChance | INT     |         0 |              |    0 |
|    95 | street1CheckCallDone        | INT     |         0 |              |    0 |
|    96 | street1CheckRaiseDone       | INT     |         0 |              |    0 |
|    97 | street2CheckCallRaiseChance | INT     |         0 |              |    0 |
|    98 | street2CheckCallDone        | INT     |         0 |              |    0 |
|    99 | street2CheckRaiseDone       | INT     |         0 |              |    0 |
|   100 | street3CheckCallRaiseChance | INT     |         0 |              |    0 |
|   101 | street3CheckCallDone        | INT     |         0 |              |    0 |
|   102 | street3CheckRaiseDone       | INT     |         0 |              |    0 |
|   103 | street4CheckCallRaiseChance | INT     |         0 |              |    0 |
|   104 | street4CheckCallDone        | INT     |         0 |              |    0 |
|   105 | street4CheckRaiseDone       | INT     |         0 |              |    0 |
|   106 | street0Calls                | INT     |         0 |              |    0 |
|   107 | street1Calls                | INT     |         0 |              |    0 |
|   108 | street2Calls                | INT     |         0 |              |    0 |
|   109 | street3Calls                | INT     |         0 |              |    0 |
|   110 | street4Calls                | INT     |         0 |              |    0 |
|   111 | street0Bets                 | INT     |         0 |              |    0 |
|   112 | street1Bets                 | INT     |         0 |              |    0 |
|   113 | street2Bets                 | INT     |         0 |              |    0 |
|   114 | street3Bets                 | INT     |         0 |              |    0 |
|   115 | street4Bets                 | INT     |         0 |              |    0 |
|   116 | street0Raises               | INT     |         0 |              |    0 |
|   117 | street1Raises               | INT     |         0 |              |    0 |
|   118 | street2Raises               | INT     |         0 |              |    0 |
|   119 | street3Raises               | INT     |         0 |              |    0 |
|   120 | street4Raises               | INT     |         0 |              |    0 |
|   121 | street1Discards             | INT     |         0 |              |    0 |
|   122 | street2Discards             | INT     |         0 |              |    0 |
|   123 | street3Discards             | INT     |         0 |              |    0 |

Rank:
|   cid | name   | type    |   notnull | dflt_value   |   pk |
|------:|:-------|:--------|----------:|:-------------|-----:|
|     0 | id     | INTEGER |         0 |              |    1 |
|     1 | name   | TEXT    |         1 |              |    0 |

RawHands:
|   cid | name     | type    |   notnull | dflt_value   |   pk |
|------:|:---------|:--------|----------:|:-------------|-----:|
|     0 | id       | INTEGER |         0 |              |    1 |
|     1 | handId   | BIGINT  |         1 |              |    0 |
|     2 | rawHand  | TEXT    |         1 |              |    0 |
|     3 | complain | BOOLEAN |         1 | FALSE        |    0 |

RawTourneys:
|   cid | name       | type    |   notnull | dflt_value   |   pk |
|------:|:-----------|:--------|----------:|:-------------|-----:|
|     0 | id         | INTEGER |         0 |              |    1 |
|     1 | tourneyId  | BIGINT  |         1 |              |    0 |
|     2 | rawTourney | TEXT    |         1 |              |    0 |
|     3 | complain   | BOOLEAN |         1 | FALSE        |    0 |

Sessions:
|   cid | name         | type      |   notnull | dflt_value   |   pk |
|------:|:-------------|:----------|----------:|:-------------|-----:|
|     0 | id           | INTEGER   |         0 |              |    1 |
|     1 | weekId       | INT       |         0 |              |    0 |
|     2 | monthId      | INT       |         0 |              |    0 |
|     3 | sessionStart | timestamp |         1 |              |    0 |
|     4 | sessionEnd   | timestamp |         1 |              |    0 |

SessionsCache:
|   cid | name                        | type      |   notnull | dflt_value   |   pk |
|------:|:----------------------------|:----------|----------:|:-------------|-----:|
|     0 | id                          | INTEGER   |         0 |              |    1 |
|     1 | sessionId                   | INT       |         0 |              |    0 |
|     2 | startTime                   | timestamp |         1 |              |    0 |
|     3 | endTime                     | timestamp |         1 |              |    0 |
|     4 | gametypeId                  | INT       |         0 |              |    0 |
|     5 | playerId                    | INT       |         0 |              |    0 |
|     6 | n                           | INT       |         0 |              |    0 |
|     7 | street0VPIChance            | INT       |         0 |              |    0 |
|     8 | street0VPI                  | INT       |         0 |              |    0 |
|     9 | street0AggrChance           | INT       |         0 |              |    0 |
|    10 | street0Aggr                 | INT       |         0 |              |    0 |
|    11 | street0CalledRaiseChance    | INT       |         0 |              |    0 |
|    12 | street0CalledRaiseDone      | INT       |         0 |              |    0 |
|    13 | street0_2BChance            | INT       |         0 |              |    0 |
|    14 | street0_2BDone              | INT       |         0 |              |    0 |
|    15 | street0_3BChance            | INT       |         0 |              |    0 |
|    16 | street0_3BDone              | INT       |         0 |              |    0 |
|    17 | street0_4BChance            | INT       |         0 |              |    0 |
|    18 | street0_4BDone              | INT       |         0 |              |    0 |
|    19 | street0_C4BChance           | INT       |         0 |              |    0 |
|    20 | street0_C4BDone             | INT       |         0 |              |    0 |
|    21 | street0_FoldTo2BChance      | INT       |         0 |              |    0 |
|    22 | street0_FoldTo2BDone        | INT       |         0 |              |    0 |
|    23 | street0_FoldTo3BChance      | INT       |         0 |              |    0 |
|    24 | street0_FoldTo3BDone        | INT       |         0 |              |    0 |
|    25 | street0_FoldTo4BChance      | INT       |         0 |              |    0 |
|    26 | street0_FoldTo4BDone        | INT       |         0 |              |    0 |
|    27 | street0_SqueezeChance       | INT       |         0 |              |    0 |
|    28 | street0_SqueezeDone         | INT       |         0 |              |    0 |
|    29 | raiseToStealChance          | INT       |         0 |              |    0 |
|    30 | raiseToStealDone            | INT       |         0 |              |    0 |
|    31 | stealChance                 | INT       |         0 |              |    0 |
|    32 | stealDone                   | INT       |         0 |              |    0 |
|    33 | success_Steal               | INT       |         0 |              |    0 |
|    34 | street1Seen                 | INT       |         0 |              |    0 |
|    35 | street2Seen                 | INT       |         0 |              |    0 |
|    36 | street3Seen                 | INT       |         0 |              |    0 |
|    37 | street4Seen                 | INT       |         0 |              |    0 |
|    38 | sawShowdown                 | INT       |         0 |              |    0 |
|    39 | street1Aggr                 | INT       |         0 |              |    0 |
|    40 | street2Aggr                 | INT       |         0 |              |    0 |
|    41 | street3Aggr                 | INT       |         0 |              |    0 |
|    42 | street4Aggr                 | INT       |         0 |              |    0 |
|    43 | otherRaisedStreet0          | INT       |         0 |              |    0 |
|    44 | otherRaisedStreet1          | INT       |         0 |              |    0 |
|    45 | otherRaisedStreet2          | INT       |         0 |              |    0 |
|    46 | otherRaisedStreet3          | INT       |         0 |              |    0 |
|    47 | otherRaisedStreet4          | INT       |         0 |              |    0 |
|    48 | foldToOtherRaisedStreet0    | INT       |         0 |              |    0 |
|    49 | foldToOtherRaisedStreet1    | INT       |         0 |              |    0 |
|    50 | foldToOtherRaisedStreet2    | INT       |         0 |              |    0 |
|    51 | foldToOtherRaisedStreet3    | INT       |         0 |              |    0 |
|    52 | foldToOtherRaisedStreet4    | INT       |         0 |              |    0 |
|    53 | wonWhenSeenStreet1          | INT       |         0 |              |    0 |
|    54 | wonWhenSeenStreet2          | INT       |         0 |              |    0 |
|    55 | wonWhenSeenStreet3          | INT       |         0 |              |    0 |
|    56 | wonWhenSeenStreet4          | INT       |         0 |              |    0 |
|    57 | wonAtSD                     | INT       |         0 |              |    0 |
|    58 | raiseFirstInChance          | INT       |         0 |              |    0 |
|    59 | raisedFirstIn               | INT       |         0 |              |    0 |
|    60 | foldBbToStealChance         | INT       |         0 |              |    0 |
|    61 | foldedBbToSteal             | INT       |         0 |              |    0 |
|    62 | foldSbToStealChance         | INT       |         0 |              |    0 |
|    63 | foldedSbToSteal             | INT       |         0 |              |    0 |
|    64 | street1CBChance             | INT       |         0 |              |    0 |
|    65 | street1CBDone               | INT       |         0 |              |    0 |
|    66 | street2CBChance             | INT       |         0 |              |    0 |
|    67 | street2CBDone               | INT       |         0 |              |    0 |
|    68 | street3CBChance             | INT       |         0 |              |    0 |
|    69 | street3CBDone               | INT       |         0 |              |    0 |
|    70 | street4CBChance             | INT       |         0 |              |    0 |
|    71 | street4CBDone               | INT       |         0 |              |    0 |
|    72 | foldToStreet1CBChance       | INT       |         0 |              |    0 |
|    73 | foldToStreet1CBDone         | INT       |         0 |              |    0 |
|    74 | foldToStreet2CBChance       | INT       |         0 |              |    0 |
|    75 | foldToStreet2CBDone         | INT       |         0 |              |    0 |
|    76 | foldToStreet3CBChance       | INT       |         0 |              |    0 |
|    77 | foldToStreet3CBDone         | INT       |         0 |              |    0 |
|    78 | foldToStreet4CBChance       | INT       |         0 |              |    0 |
|    79 | foldToStreet4CBDone         | INT       |         0 |              |    0 |
|    80 | common                      | INT       |         0 |              |    0 |
|    81 | committed                   | INT       |         0 |              |    0 |
|    82 | winnings                    | INT       |         0 |              |    0 |
|    83 | rake                        | INT       |         0 |              |    0 |
|    84 | rakeDealt                   | decimal   |         0 |              |    0 |
|    85 | rakeContributed             | decimal   |         0 |              |    0 |
|    86 | rakeWeighted                | decimal   |         0 |              |    0 |
|    87 | totalProfit                 | INT       |         0 |              |    0 |
|    88 | allInEV                     | decimal   |         0 |              |    0 |
|    89 | showdownWinnings            | INT       |         0 |              |    0 |
|    90 | nonShowdownWinnings         | INT       |         0 |              |    0 |
|    91 | street1CheckCallRaiseChance | INT       |         0 |              |    0 |
|    92 | street1CheckCallDone        | INT       |         0 |              |    0 |
|    93 | street1CheckRaiseDone       | INT       |         0 |              |    0 |
|    94 | street2CheckCallRaiseChance | INT       |         0 |              |    0 |
|    95 | street2CheckCallDone        | INT       |         0 |              |    0 |
|    96 | street2CheckRaiseDone       | INT       |         0 |              |    0 |
|    97 | street3CheckCallRaiseChance | INT       |         0 |              |    0 |
|    98 | street3CheckCallDone        | INT       |         0 |              |    0 |
|    99 | street3CheckRaiseDone       | INT       |         0 |              |    0 |
|   100 | street4CheckCallRaiseChance | INT       |         0 |              |    0 |
|   101 | street4CheckCallDone        | INT       |         0 |              |    0 |
|   102 | street4CheckRaiseDone       | INT       |         0 |              |    0 |
|   103 | street0Calls                | INT       |         0 |              |    0 |
|   104 | street1Calls                | INT       |         0 |              |    0 |
|   105 | street2Calls                | INT       |         0 |              |    0 |
|   106 | street3Calls                | INT       |         0 |              |    0 |
|   107 | street4Calls                | INT       |         0 |              |    0 |
|   108 | street0Bets                 | INT       |         0 |              |    0 |
|   109 | street1Bets                 | INT       |         0 |              |    0 |
|   110 | street2Bets                 | INT       |         0 |              |    0 |
|   111 | street3Bets                 | INT       |         0 |              |    0 |
|   112 | street4Bets                 | INT       |         0 |              |    0 |
|   113 | street0Raises               | INT       |         0 |              |    0 |
|   114 | street1Raises               | INT       |         0 |              |    0 |
|   115 | street2Raises               | INT       |         0 |              |    0 |
|   116 | street3Raises               | INT       |         0 |              |    0 |
|   117 | street4Raises               | INT       |         0 |              |    0 |
|   118 | street1Discards             | INT       |         0 |              |    0 |
|   119 | street2Discards             | INT       |         0 |              |    0 |
|   120 | street3Discards             | INT       |         0 |              |    0 |

Settings:
|   cid | name    | type    |   notnull | dflt_value   |   pk |
|------:|:--------|:--------|----------:|:-------------|-----:|
|     0 | version | INTEGER |         1 |              |    0 |

Sites:
|   cid | name   | type    |   notnull | dflt_value   |   pk |
|------:|:-------|:--------|----------:|:-------------|-----:|
|     0 | id     | INTEGER |         0 |              |    1 |
|     1 | name   | TEXT    |         1 |              |    0 |
|     2 | code   | TEXT    |         1 |              |    0 |

StartCards:
|   cid | name         | type     |   notnull | dflt_value   |   pk |
|------:|:-------------|:---------|----------:|:-------------|-----:|
|     0 | id           | INTEGER  |         0 |              |    1 |
|     1 | category     | TEXT     |         1 |              |    0 |
|     2 | name         | TEXT     |         1 |              |    0 |
|     3 | rank         | SMALLINT |         1 |              |    0 |
|     4 | combinations | SMALLINT |         1 |              |    0 |

TourneyTypes:
|   cid | name            | type       |   notnull | dflt_value   |   pk |
|------:|:----------------|:-----------|----------:|:-------------|-----:|
|     0 | id              | INTEGER    |         0 |              |    1 |
|     1 | siteId          | INT        |         1 |              |    0 |
|     2 | currency        | VARCHAR(4) |         0 |              |    0 |
|     3 | buyin           | INT        |         0 |              |    0 |
|     4 | fee             | INT        |         0 |              |    0 |
|     5 | category        | TEXT       |         0 |              |    0 |
|     6 | limitType       | TEXT       |         0 |              |    0 |
|     7 | buyInChips      | INT        |         0 |              |    0 |
|     8 | stack           | VARCHAR(8) |         0 |              |    0 |
|     9 | maxSeats        | INT        |         0 |              |    0 |
|    10 | rebuy           | BOOLEAN    |         0 |              |    0 |
|    11 | rebuyCost       | INT        |         0 |              |    0 |
|    12 | rebuyFee        | INT        |         0 |              |    0 |
|    13 | rebuyChips      | INT        |         0 |              |    0 |
|    14 | addOn           | BOOLEAN    |         0 |              |    0 |
|    15 | addOnCost       | INT        |         0 |              |    0 |
|    16 | addOnFee        | INT        |         0 |              |    0 |
|    17 | addOnChips      | INT        |         0 |              |    0 |
|    18 | knockout        | BOOLEAN    |         0 |              |    0 |
|    19 | koBounty        | INT        |         0 |              |    0 |
|    20 | progressive     | BOOLEAN    |         0 |              |    0 |
|    21 | step            | BOOLEAN    |         0 |              |    0 |
|    22 | stepNo          | INT        |         0 |              |    0 |
|    23 | chance          | BOOLEAN    |         0 |              |    0 |
|    24 | chanceCount     | INT        |         0 |              |    0 |
|    25 | speed           | TEXT       |         0 |              |    0 |
|    26 | shootout        | BOOLEAN    |         0 |              |    0 |
|    27 | matrix          | BOOLEAN    |         0 |              |    0 |
|    28 | multiEntry      | BOOLEAN    |         0 |              |    0 |
|    29 | reEntry         | BOOLEAN    |         0 |              |    0 |
|    30 | fast            | BOOLEAN    |         0 |              |    0 |
|    31 | newToGame       | BOOLEAN    |         0 |              |    0 |
|    32 | homeGame        | BOOLEAN    |         0 |              |    0 |
|    33 | split           | BOOLEAN    |         0 |              |    0 |
|    34 | sng             | BOOLEAN    |         0 |              |    0 |
|    35 | fifty50         | BOOLEAN    |         0 |              |    0 |
|    36 | time            | BOOLEAN    |         0 |              |    0 |
|    37 | timeAmt         | INT        |         0 |              |    0 |
|    38 | satellite       | BOOLEAN    |         0 |              |    0 |
|    39 | doubleOrNothing | BOOLEAN    |         0 |              |    0 |
|    40 | cashOut         | BOOLEAN    |         0 |              |    0 |
|    41 | onDemand        | BOOLEAN    |         0 |              |    0 |
|    42 | flighted        | BOOLEAN    |         0 |              |    0 |
|    43 | guarantee       | BOOLEAN    |         0 |              |    0 |
|    44 | guaranteeAmt    | INT        |         0 |              |    0 |

Tourneys:
|   cid | name            | type       |   notnull | dflt_value   |   pk |
|------:|:----------------|:-----------|----------:|:-------------|-----:|
|     0 | id              | INTEGER    |         0 |              |    1 |
|     1 | tourneyTypeId   | INT        |         0 |              |    0 |
|     2 | sessionId       | INT        |         0 |              |    0 |
|     3 | siteTourneyNo   | INT        |         0 |              |    0 |
|     4 | entries         | INT        |         0 |              |    0 |
|     5 | prizepool       | INT        |         0 |              |    0 |
|     6 | startTime       | timestamp  |         0 |              |    0 |
|     7 | endTime         | timestamp  |         0 |              |    0 |
|     8 | tourneyName     | TEXT       |         0 |              |    0 |
|     9 | totalRebuyCount | INT        |         0 |              |    0 |
|    10 | totalAddOnCount | INT        |         0 |              |    0 |
|    11 | added           | INT        |         0 |              |    0 |
|    12 | addedCurrency   | VARCHAR(4) |         0 |              |    0 |
|    13 | comment         | TEXT       |         0 |              |    0 |
|    14 | commentTs       | timestamp  |         0 |              |    0 |

TourneysCache:
|   cid | name                        | type      |   notnull | dflt_value   |   pk |
|------:|:----------------------------|:----------|----------:|:-------------|-----:|
|     0 | id                          | INTEGER   |         0 |              |    1 |
|     1 | sessionId                   | INT       |         0 |              |    0 |
|     2 | startTime                   | timestamp |         1 |              |    0 |
|     3 | endTime                     | timestamp |         1 |              |    0 |
|     4 | tourneyId                   | INT       |         0 |              |    0 |
|     5 | playerId                    | INT       |         0 |              |    0 |
|     6 | n                           | INT       |         0 |              |    0 |
|     7 | street0VPIChance            | INT       |         0 |              |    0 |
|     8 | street0VPI                  | INT       |         0 |              |    0 |
|     9 | street0AggrChance           | INT       |         0 |              |    0 |
|    10 | street0Aggr                 | INT       |         0 |              |    0 |
|    11 | street0CalledRaiseChance    | INT       |         0 |              |    0 |
|    12 | street0CalledRaiseDone      | INT       |         0 |              |    0 |
|    13 | street0_2BChance            | INT       |         0 |              |    0 |
|    14 | street0_2BDone              | INT       |         0 |              |    0 |
|    15 | street0_3BChance            | INT       |         0 |              |    0 |
|    16 | street0_3BDone              | INT       |         0 |              |    0 |
|    17 | street0_4BChance            | INT       |         0 |              |    0 |
|    18 | street0_4BDone              | INT       |         0 |              |    0 |
|    19 | street0_C4BChance           | INT       |         0 |              |    0 |
|    20 | street0_C4BDone             | INT       |         0 |              |    0 |
|    21 | street0_FoldTo2BChance      | INT       |         0 |              |    0 |
|    22 | street0_FoldTo2BDone        | INT       |         0 |              |    0 |
|    23 | street0_FoldTo3BChance      | INT       |         0 |              |    0 |
|    24 | street0_FoldTo3BDone        | INT       |         0 |              |    0 |
|    25 | street0_FoldTo4BChance      | INT       |         0 |              |    0 |
|    26 | street0_FoldTo4BDone        | INT       |         0 |              |    0 |
|    27 | street0_SqueezeChance       | INT       |         0 |              |    0 |
|    28 | street0_SqueezeDone         | INT       |         0 |              |    0 |
|    29 | raiseToStealChance          | INT       |         0 |              |    0 |
|    30 | raiseToStealDone            | INT       |         0 |              |    0 |
|    31 | stealChance                 | INT       |         0 |              |    0 |
|    32 | stealDone                   | INT       |         0 |              |    0 |
|    33 | success_Steal               | INT       |         0 |              |    0 |
|    34 | street1Seen                 | INT       |         0 |              |    0 |
|    35 | street2Seen                 | INT       |         0 |              |    0 |
|    36 | street3Seen                 | INT       |         0 |              |    0 |
|    37 | street4Seen                 | INT       |         0 |              |    0 |
|    38 | sawShowdown                 | INT       |         0 |              |    0 |
|    39 | street1Aggr                 | INT       |         0 |              |    0 |
|    40 | street2Aggr                 | INT       |         0 |              |    0 |
|    41 | street3Aggr                 | INT       |         0 |              |    0 |
|    42 | street4Aggr                 | INT       |         0 |              |    0 |
|    43 | otherRaisedStreet0          | INT       |         0 |              |    0 |
|    44 | otherRaisedStreet1          | INT       |         0 |              |    0 |
|    45 | otherRaisedStreet2          | INT       |         0 |              |    0 |
|    46 | otherRaisedStreet3          | INT       |         0 |              |    0 |
|    47 | otherRaisedStreet4          | INT       |         0 |              |    0 |
|    48 | foldToOtherRaisedStreet0    | INT       |         0 |              |    0 |
|    49 | foldToOtherRaisedStreet1    | INT       |         0 |              |    0 |
|    50 | foldToOtherRaisedStreet2    | INT       |         0 |              |    0 |
|    51 | foldToOtherRaisedStreet3    | INT       |         0 |              |    0 |
|    52 | foldToOtherRaisedStreet4    | INT       |         0 |              |    0 |
|    53 | wonWhenSeenStreet1          | INT       |         0 |              |    0 |
|    54 | wonWhenSeenStreet2          | INT       |         0 |              |    0 |
|    55 | wonWhenSeenStreet3          | INT       |         0 |              |    0 |
|    56 | wonWhenSeenStreet4          | INT       |         0 |              |    0 |
|    57 | wonAtSD                     | INT       |         0 |              |    0 |
|    58 | raiseFirstInChance          | INT       |         0 |              |    0 |
|    59 | raisedFirstIn               | INT       |         0 |              |    0 |
|    60 | foldBbToStealChance         | INT       |         0 |              |    0 |
|    61 | foldedBbToSteal             | INT       |         0 |              |    0 |
|    62 | foldSbToStealChance         | INT       |         0 |              |    0 |
|    63 | foldedSbToSteal             | INT       |         0 |              |    0 |
|    64 | street1CBChance             | INT       |         0 |              |    0 |
|    65 | street1CBDone               | INT       |         0 |              |    0 |
|    66 | street2CBChance             | INT       |         0 |              |    0 |
|    67 | street2CBDone               | INT       |         0 |              |    0 |
|    68 | street3CBChance             | INT       |         0 |              |    0 |
|    69 | street3CBDone               | INT       |         0 |              |    0 |
|    70 | street4CBChance             | INT       |         0 |              |    0 |
|    71 | street4CBDone               | INT       |         0 |              |    0 |
|    72 | foldToStreet1CBChance       | INT       |         0 |              |    0 |
|    73 | foldToStreet1CBDone         | INT       |         0 |              |    0 |
|    74 | foldToStreet2CBChance       | INT       |         0 |              |    0 |
|    75 | foldToStreet2CBDone         | INT       |         0 |              |    0 |
|    76 | foldToStreet3CBChance       | INT       |         0 |              |    0 |
|    77 | foldToStreet3CBDone         | INT       |         0 |              |    0 |
|    78 | foldToStreet4CBChance       | INT       |         0 |              |    0 |
|    79 | foldToStreet4CBDone         | INT       |         0 |              |    0 |
|    80 | common                      | INT       |         0 |              |    0 |
|    81 | committed                   | INT       |         0 |              |    0 |
|    82 | winnings                    | INT       |         0 |              |    0 |
|    83 | rake                        | INT       |         0 |              |    0 |
|    84 | rakeDealt                   | decimal   |         0 |              |    0 |
|    85 | rakeContributed             | decimal   |         0 |              |    0 |
|    86 | rakeWeighted                | decimal   |         0 |              |    0 |
|    87 | totalProfit                 | INT       |         0 |              |    0 |
|    88 | allInEV                     | decimal   |         0 |              |    0 |
|    89 | showdownWinnings            | INT       |         0 |              |    0 |
|    90 | nonShowdownWinnings         | INT       |         0 |              |    0 |
|    91 | street1CheckCallRaiseChance | INT       |         0 |              |    0 |
|    92 | street1CheckCallDone        | INT       |         0 |              |    0 |
|    93 | street1CheckRaiseDone       | INT       |         0 |              |    0 |
|    94 | street2CheckCallRaiseChance | INT       |         0 |              |    0 |
|    95 | street2CheckCallDone        | INT       |         0 |              |    0 |
|    96 | street2CheckRaiseDone       | INT       |         0 |              |    0 |
|    97 | street3CheckCallRaiseChance | INT       |         0 |              |    0 |
|    98 | street3CheckCallDone        | INT       |         0 |              |    0 |
|    99 | street3CheckRaiseDone       | INT       |         0 |              |    0 |
|   100 | street4CheckCallRaiseChance | INT       |         0 |              |    0 |
|   101 | street4CheckCallDone        | INT       |         0 |              |    0 |
|   102 | street4CheckRaiseDone       | INT       |         0 |              |    0 |
|   103 | street0Calls                | INT       |         0 |              |    0 |
|   104 | street1Calls                | INT       |         0 |              |    0 |
|   105 | street2Calls                | INT       |         0 |              |    0 |
|   106 | street3Calls                | INT       |         0 |              |    0 |
|   107 | street4Calls                | INT       |         0 |              |    0 |
|   108 | street0Bets                 | INT       |         0 |              |    0 |
|   109 | street1Bets                 | INT       |         0 |              |    0 |
|   110 | street2Bets                 | INT       |         0 |              |    0 |
|   111 | street3Bets                 | INT       |         0 |              |    0 |
|   112 | street4Bets                 | INT       |         0 |              |    0 |
|   113 | street0Raises               | INT       |         0 |              |    0 |
|   114 | street1Raises               | INT       |         0 |              |    0 |
|   115 | street2Raises               | INT       |         0 |              |    0 |
|   116 | street3Raises               | INT       |         0 |              |    0 |
|   117 | street4Raises               | INT       |         0 |              |    0 |
|   118 | street1Discards             | INT       |         0 |              |    0 |
|   119 | street2Discards             | INT       |         0 |              |    0 |
|   120 | street3Discards             | INT       |         0 |              |    0 |

TourneysPlayers:
|   cid | name             | type       |   notnull | dflt_value   |   pk |
|------:|:-----------------|:-----------|----------:|:-------------|-----:|
|     0 | id               | INTEGER    |         0 |              |    1 |
|     1 | tourneyId        | INT        |         0 |              |    0 |
|     2 | playerId         | INT        |         0 |              |    0 |
|     3 | entryId          | INT        |         0 |              |    0 |
|     4 | rank             | INT        |         0 |              |    0 |
|     5 | winnings         | INT        |         0 |              |    0 |
|     6 | winningsCurrency | VARCHAR(4) |         0 |              |    0 |
|     7 | rebuyCount       | INT        |         0 |              |    0 |
|     8 | addOnCount       | INT        |         0 |              |    0 |
|     9 | koCount          | decimal    |         0 |              |    0 |
|    10 | comment          | TEXT       |         0 |              |    0 |
|    11 | commentTs        | timestamp  |         0 |              |    0 |

Weeks:
|   cid | name      | type      |   notnull | dflt_value   |   pk |
|------:|:----------|:----------|----------:|:-------------|-----:|
|     0 | id        | INTEGER   |         0 |              |    1 |
|     1 | weekStart | timestamp |         1 |              |    0 |

sqlite_stat1:
|   cid | name   | type   |   notnull | dflt_value   |   pk |
|------:|:-------|:-------|----------:|:-------------|-----:|
|     0 | tbl    |        |         0 |              |    0 |
|     1 | idx    |        |         0 |              |    0 |
|     2 | stat   |        |         0 |              |    0 |