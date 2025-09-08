"""Pydantic base models for FPDB web API.

This module contains all the Pydantic BaseModel classes used for data validation
and serialization in the FPDB web API.

Note: Variable names use mixedCase to match database column names and maintain
API compatibility. This is intentional and follows the existing database schema.
"""

# ruff: noqa: N815
# Ignore mixedCase variable names as they match database schema

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

sys.path.append(str(Path(__file__).parent.parent))


class Backing(BaseModel):
    """Backing model for tournament player backing information."""

    id: int
    tourneysPlayersId: int
    playerId: int
    buyInPercentage: float
    payOffPercentage: float


class Action(BaseModel):
    """Action model for player actions in poker hands."""

    id: int
    name: str
    code: str


class Autorate(BaseModel):
    """Autorate model for automatic player ratings."""

    id: int
    playerId: int | None
    gametypeId: int | None
    description: str | None
    shortDesc: str | None
    ratingTime: str | None
    handCount: int | None


class Board(BaseModel):
    """Board model for community cards in poker hands."""

    id: int
    handId: int
    boardId: int | None
    boardcard1: int | None
    boardcard2: int | None
    boardcard3: int | None
    boardcard4: int | None
    boardcard5: int | None


class CardsCache(BaseModel):
    """CardsCache model for cached card statistics."""

    id: int
    weekId: int | None
    monthId: int | None
    gametypeId: int | None
    tourneyTypeId: int | None
    playerId: int | None
    startCards: int | None
    n: int | None
    street0VPIChance: int | None
    street0VPI: int | None
    street0AggrChance: int | None
    street0Aggr: int | None
    street0CalledRaiseChance: int | None
    street0CalledRaiseDone: int | None
    street0_2BChance: int | None
    street0_2BDone: int | None
    street0_3BChance: int | None
    street0_3BDone: int | None
    street0_4BChance: int | None
    street0_4BDone: int | None
    street0_C4BChance: int | None
    street0_C4BDone: int | None
    street0_FoldTo2BChance: int | None
    street0_FoldTo2BDone: int | None
    street0_FoldTo3BChance: int | None
    street0_FoldTo3BDone: int | None
    street0_FoldTo4BChance: int | None
    street0_FoldTo4BDone: int | None
    street0_SqueezeChance: int | None
    street0_SqueezeDone: int | None
    raiseToStealChance: int | None
    raiseToStealDone: int | None
    stealChance: int | None
    stealDone: int | None
    success_Steal: int | None
    street1Seen: int | None
    street2Seen: int | None
    street3Seen: int | None
    street4Seen: int | None
    sawShowdown: int | None
    street1Aggr: int | None
    street2Aggr: int | None
    street3Aggr: int | None
    street4Aggr: int | None
    otherRaisedStreet0: int | None
    otherRaisedStreet1: int | None
    otherRaisedStreet2: int | None
    otherRaisedStreet3: int | None
    otherRaisedStreet4: int | None
    foldToOtherRaisedStreet0: int | None
    foldToOtherRaisedStreet1: int | None
    foldToOtherRaisedStreet2: int | None
    foldToOtherRaisedStreet3: int | None
    foldToOtherRaisedStreet4: int | None
    wonWhenSeenStreet1: int | None
    wonWhenSeenStreet2: int | None
    wonWhenSeenStreet3: int | None
    wonWhenSeenStreet4: int | None
    wonAtSD: int | None
    raiseFirstInChance: int | None
    raisedFirstIn: int | None
    foldBbToStealChance: int | None
    foldedBbToSteal: int | None
    foldSbToStealChance: int | None
    foldedSbToSteal: int | None
    street1CBChance: int | None
    street1CBDone: int | None
    street2CBChance: int | None
    street2CBDone: int | None
    street3CBChance: int | None
    street3CBDone: int | None
    street4CBChance: int | None
    street4CBDone: int | None
    foldToStreet1CBChance: int | None
    foldToStreet1CBDone: int | None
    foldToStreet2CBChance: int | None
    foldToStreet2CBDone: int | None
    foldToStreet3CBChance: int | None
    foldToStreet3CBDone: int | None
    foldToStreet4CBChance: int | None
    foldToStreet4CBDone: int | None
    common: int | None
    committed: int | None
    winnings: int | None
    rake: int | None
    rakeDealt: float | None
    rakeContributed: float | None
    rakeWeighted: float | None
    totalProfit: int | None
    allInEV: float | None
    showdownWinnings: int | None
    nonShowdownWinnings: int | None
    street1CheckCallRaiseChance: int | None
    street1CheckCallDone: int | None
    street1CheckRaiseDone: int | None
    street2CheckCallRaiseChance: int | None
    street2CheckCallDone: int | None
    street2CheckRaiseDone: int | None
    street3CheckCallRaiseChance: int | None
    street3CheckCallDone: int | None
    street3CheckRaiseDone: int | None
    street4CheckCallRaiseChance: int | None
    street4CheckCallDone: int | None
    street4CheckRaiseDone: int | None
    street0Calls: int | None
    street1Calls: int | None
    street2Calls: int | None
    street3Calls: int | None
    street4Calls: int | None
    street0Bets: int | None
    street1Bets: int | None
    street2Bets: int | None
    street3Bets: int | None
    street4Bets: int | None
    street0Raises: int | None
    street1Raises: int | None
    street2Raises: int | None
    street3Raises: int | None
    street4Raises: int | None
    street1Discards: int | None
    street2Discards: int | None
    street3Discards: int | None


class File(BaseModel):
    """File model for hand history files."""

    id: int
    file: str
    site: str | None
    type: str | None
    startTime: datetime
    lastUpdate: datetime
    endTime: datetime | None
    hands: int | None
    storedHands: int | None
    dups: int | None
    partial: int | None
    skipped: int | None
    errs: int | None
    ttime100: int | None
    finished: bool | None


class Gametype(BaseModel):
    """Gametype model for different poker game types."""

    id: int
    siteId: int
    currency: str
    type: str
    base: str
    category: str
    limitType: str
    hiLo: str
    mix: str
    smallBlind: int | None
    bigBlind: int | None
    smallBet: int
    bigBet: int
    maxSeats: int
    ante: int
    buyinType: str
    fast: int | None
    newToGame: int | None
    homeGame: int | None
    split: int | None


class Hand(BaseModel):
    """Hand model for individual poker hands."""

    id: int
    tableName: str
    siteHandNo: int
    tourneyId: int | None
    gametypeId: int
    sessionId: int | None
    fileId: int
    startTime: str
    importTime: str
    seats: int
    heroSeat: int
    maxPosition: int
    boardcard1: int | None
    boardcard2: int | None
    boardcard3: int | None
    boardcard4: int | None
    boardcard5: int | None
    texture: int | None
    runItTwice: bool | None
    playersVpi: int
    playersAtStreet1: int
    playersAtStreet2: int
    playersAtStreet3: int
    playersAtStreet4: int
    playersAtShowdown: int
    street0Raises: int
    street1Raises: int
    street2Raises: int
    street3Raises: int
    street4Raises: int
    street0Pot: int | None
    street1Pot: int | None
    street2Pot: int | None
    street3Pot: int | None
    street4Pot: int | None
    finalPot: int | None
    comment: str | None
    commentTs: str | None


class HandsAction(BaseModel):
    """HandsAction model for actions taken during poker hands."""

    id: int
    handId: int
    playerId: int
    street: int | None
    actionNo: int | None
    streetActionNo: int | None
    actionId: int | None
    amount: int | None
    raiseTo: int | None
    amountCalled: int | None
    numDiscarded: int | None
    cardsDiscarded: str | None
    allIn: bool | None


class HandsPlayer(BaseModel):
    """HandsPlayer model for player data in poker hands."""

    id: int
    handId: int
    playerId: int
    startCash: int
    effStack: int
    startBounty: int | None
    endBounty: int | None
    position: str | None
    seatNo: int
    sitout: bool
    card1: int
    card2: int
    card3: int | None
    card4: int | None
    card5: int | None
    card6: int | None
    card7: int | None
    card8: int | None
    card9: int | None
    card10: int | None
    card11: int | None
    card12: int | None
    card13: int | None
    card14: int | None
    card15: int | None
    card16: int | None
    card17: int | None
    card18: int | None
    card19: int | None
    card20: int | None
    startCards: int | None
    common: int
    committed: int
    winnings: int
    rake: int
    rakeDealt: float
    rakeContributed: float
    rakeWeighted: float
    totalProfit: int | None
    allInEV: float | None
    comment: str | None
    commentTs: datetime | None
    tourneysPlayersId: int | None
    wonWhenSeenStreet1: int | None
    wonWhenSeenStreet2: int | None
    wonWhenSeenStreet3: int | None
    wonWhenSeenStreet4: int | None
    wonAtSD: int | None
    street0VPIChance: int | None
    street0VPI: int | None
    street0AggrChance: int | None
    street0Aggr: int | None
    street0CalledRaiseChance: int | None
    street0CalledRaiseDone: int | None
    street0_2BChance: int | None
    street0_2BDone: int | None
    street0_3BChance: int | None
    street0_3BDone: int | None
    street0_4BChance: int | None
    street0_4BDone: int | None
    street0_C4BChance: int | None
    street0_C4BDone: int | None
    street0_FoldTo2BChance: int | None
    street0_FoldTo2BDone: int | None
    street0_FoldTo3BChance: int | None
    street0_FoldTo3BDone: int | None
    street0_FoldTo4BChance: int | None
    street0_FoldTo4BDone: int | None
    street0_SqueezeChance: int | None
    street0_SqueezeDone: int | None
    raiseToStealChance: int | None
    raiseToStealDone: int | None
    stealChance: int | None
    stealDone: int | None
    success_Steal: int | None
    street1Seen: int | None
    street2Seen: int | None
    street3Seen: int | None
    street4Seen: int | None
    sawShowdown: int | None
    showed: int | None
    street0AllIn: int | None
    street1AllIn: int | None
    street2AllIn: int | None
    street3AllIn: int | None
    street4AllIn: int | None
    wentAllIn: int | None
    street0InPosition: int | None
    street1InPosition: int | None
    street2InPosition: int | None
    street3InPosition: int | None
    street4InPosition: int | None
    street0FirstToAct: int | None
    street1FirstToAct: int | None
    street2FirstToAct: int | None
    street3FirstToAct: int | None
    street4FirstToAct: int | None
    street1Aggr: int | None
    street2Aggr: int | None
    street3Aggr: int | None
    street4Aggr: int | None
    otherRaisedStreet0: int | None
    otherRaisedStreet1: int | None
    otherRaisedStreet2: int | None
    otherRaisedStreet3: int | None
    otherRaisedStreet4: int | None
    foldToOtherRaisedStreet0: int | None
    foldToOtherRaisedStreet1: int | None
    foldToOtherRaisedStreet2: int | None
    foldToOtherRaisedStreet3: int | None
    foldToOtherRaisedStreet4: int | None
    raiseFirstInChance: int | None
    raisedFirstIn: int | None
    foldBbToStealChance: int | None
    foldedBbToSteal: int | None
    foldSbToStealChance: int | None
    foldedSbToSteal: int | None
    street1CBChance: int | None
    street1CBDone: int | None
    street2CBChance: int | None
    street2CBDone: int | None
    street3CBChance: int | None
    street3CBDone: int | None
    street4CBChance: int | None
    street4CBDone: int | None
    foldToStreet1CBChance: int | None
    foldToStreet1CBDone: int | None
    foldToStreet2CBChance: int | None
    foldToStreet2CBDone: int | None
    foldToStreet3CBChance: int | None
    foldToStreet3CBDone: int | None
    foldToStreet4CBChance: int | None
    foldToStreet4CBDone: int | None
    street1CheckCallRaiseChance: int | None
    street1CheckCallDone: int | None
    street1CheckRaiseDone: int | None
    street2CheckCallRaiseChance: int | None
    street2CheckCallDone: int | None
    street2CheckRaiseDone: int | None
    street3CheckCallRaiseChance: int | None
    street3CheckCallDone: int | None
    street3CheckRaiseDone: int | None
    street4CheckCallRaiseChance: int | None
    street4CheckCallDone: int | None
    street4CheckRaiseDone: int | None
    street0Calls: int | None
    street1Calls: int | None
    street2Calls: int | None
    street3Calls: int | None
    street4Calls: int | None
    street0Bets: int | None
    street1Bets: int | None
    street2Bets: int | None
    street3Bets: int | None
    street4Bets: int | None
    street0Raises: int | None
    street1Raises: int | None
    street2Raises: int | None
    street3Raises: int | None
    street4Raises: int | None
    street1Discards: int | None
    street2Discards: int | None
    street3Discards: int | None
    handString: str | None
    actionString: str | None


class HandsPots(BaseModel):
    """HandsPots model for pot information in poker hands."""

    id: int
    handId: int
    potId: int | None
    boardId: int | None
    hiLo: str
    playerId: int
    pot: int | None
    collected: int | None
    rake: int | None


class HandsStove(BaseModel):
    """HandsStove model for stove analysis data."""

    id: int
    handId: int
    playerId: int
    streetId: int | None
    boardId: int | None
    hiLo: str
    rankId: int | None
    value: int | None
    cards: str | None
    ev: Decimal | None


class HudCache(BaseModel):
    """HudCache model for cached HUD statistics."""

    id: int
    gametypeId: int | None
    playerId: int | None
    seats: int | None
    position: str | None
    tourneyTypeId: int | None
    styleKey: str
    n: int | None
    street0VPIChance: int | None
    street0VPI: int | None
    street0AggrChance: int | None
    street0Aggr: int | None
    street0CalledRaiseChance: int | None
    street0CalledRaiseDone: int | None
    street0_2BChance: int | None
    street0_2BDone: int | None
    street0_3BChance: int | None
    street0_3BDone: int | None
    street0_4BChance: int | None
    street0_4BDone: int | None
    street0_C4BChance: int
    street0_C4BDone: int | None
    street0_FoldTo2BChance: int | None
    street0_FoldTo2BDone: int | None
    street0_FoldTo3BChance: int | None
    street0_FoldTo3BDone: int | None
    street0_FoldTo4BChance: int | None
    street0_FoldTo4BDone: int | None
    street0_SqueezeChance: int | None
    street0_SqueezeDone: int | None
    raiseToStealChance: int | None
    raiseToStealDone: int | None
    stealChance: int | None
    stealDone: int | None
    success_Steal: int | None
    street1Seen: int | None
    street2Seen: int | None
    street3Seen: int | None
    street4Seen: int | None
    sawShowdown: int | None
    street1Aggr: int | None
    street2Aggr: int | None
    street3Aggr: int | None
    street4Aggr: int | None
    otherRaisedStreet0: int | None
    otherRaisedStreet1: int | None
    otherRaisedStreet2: int | None
    otherRaisedStreet3: int | None
    otherRaisedStreet4: int | None
    foldToOtherRaisedStreet0: int | None
    foldToOtherRaisedStreet1: int | None
    foldToOtherRaisedStreet2: int | None
    foldToOtherRaisedStreet3: int | None
    foldToOtherRaisedStreet4: int | None
    wonWhenSeenStreet1: int | None
    wonWhenSeenStreet2: int | None
    wonWhenSeenStreet3: int | None
    wonWhenSeenStreet4: int | None
    wonAtSD: int | None
    raiseFirstInChance: int | None
    raisedFirstIn: int | None
    foldBbToStealChance: int | None
    foldedBbToSteal: int | None
    foldSbToStealChance: int | None
    foldedSbToSteal: int | None
    street1CBChance: int | None
    street1CBDone: int | None
    street2CBChance: int | None
    street2CBDone: int | None
    street3CBChance: int | None
    street3CBDone: int | None
    street4CBChance: int | None
    street4CBDone: int | None
    foldToStreet1CBChance: int | None
    foldToStreet1CBDone: int | None
    foldToStreet2CBChance: int | None
    foldToStreet2CBDone: int | None
    foldToStreet3CBChance: int | None
    foldToStreet3CBDone: int | None
    foldToStreet4CBChance: int | None
    foldToStreet4CBDone: int | None
    common: int | None
    committed: int | None
    winnings: int | None
    rake: int | None
    rakeDealt: Decimal | None
    rakeContributed: Decimal | None
    rakeWeighted: Decimal | None
    totalProfit: Decimal | None
    allInEV: Decimal | None
    showdownWinnings: int | None
    nonShowdownWinnings: int | None
    street1CheckCallRaiseChance: int | None
    street1CheckCallDone: int | None
    street1CheckRaiseDone: int | None
    street2CheckCallRaiseChance: int | None
    street2CheckCallDone: int | None
    street2CheckRaiseDone: int | None
    street3CheckCallRaiseChance: int | None
    street3CheckCallDone: int | None
    street3CheckRaiseDone: int | None
    street4CheckCallRaiseChance: int | None
    street4CheckCallDone: int | None
    street4CheckRaiseDone: int | None
    street0Calls: int | None
    street1Calls: int | None
    street2Calls: int | None
    street3Calls: int | None
    street4Calls: int | None
    street0Bets: int | None
    street1Bets: int | None
    street2Bets: int | None
    street3Bets: int | None
    street4Bets: int | None
    street0Raises: int | None
    street1Raises: int | None
    street2Raises: int | None
    street3Raises: int | None
    street4Raises: int | None
    street1Discards: int | None
    street2Discards: int | None
    street3Discards: int | None


class Month(BaseModel):
    """Month model for monthly time periods."""

    id: int
    monthStart: datetime


class Player(BaseModel):
    """Player model for poker players."""

    id: int
    name: str | None
    siteId: int | None
    hero: bool | None
    chars: str | None
    comment: str | None
    commentTs: str | None


class PositionsCache(BaseModel):
    """PositionsCache model for cached position statistics."""

    id: int
    weekId: int | None
    monthId: int | None
    gametypeId: int | None
    tourneyTypeId: int | None
    playerId: int | None
    seats: int | None
    maxPosition: int
    position: str | None
    n: int | None
    street0VPIChance: int | None
    street0VPI: int | None
    street0AggrChance: int | None
    street0Aggr: int | None
    street0CalledRaiseChance: int | None
    street0CalledRaiseDone: int | None
    street0_2BChance: int | None
    street0_2BDone: int | None
    street0_3BChance: int | None
    street0_3BDone: int | None
    street0_4BChance: int | None
    street0_4BDone: int | None
    street0_C4BChance: int | None
    street0_C4BDone: int | None
    street0_FoldTo2BChance: int | None
    street0_FoldTo2BDone: int | None
    street0_FoldTo3BChance: int | None
    street0_FoldTo3BDone: int | None
    street0_FoldTo4BChance: int | None
    street0_FoldTo4BDone: int | None
    street0_SqueezeChance: int | None
    street0_SqueezeDone: int | None
    raiseToStealChance: int | None
    raiseToStealDone: int | None
    stealChance: int | None
    stealDone: int | None
    success_Steal: int | None
    street1Seen: int | None
    street2Seen: int | None
    street3Seen: int | None
    street4Seen: int | None
    sawShowdown: int | None
    street1Aggr: int | None
    street2Aggr: int | None
    street3Aggr: int | None
    street4Aggr: int | None
    otherRaisedStreet0: int | None
    otherRaisedStreet1: int | None
    otherRaisedStreet2: int | None
    otherRaisedStreet3: int | None
    otherRaisedStreet4: int | None
    foldToOtherRaisedStreet0: int | None
    foldToOtherRaisedStreet1: int | None
    foldToOtherRaisedStreet2: int | None
    foldToOtherRaisedStreet3: int | None
    foldToOtherRaisedStreet4: int | None
    wonWhenSeenStreet1: int | None
    wonWhenSeenStreet2: int | None
    wonWhenSeenStreet3: int | None
    wonWhenSeenStreet4: int | None
    wonAtSD: int | None
    raiseFirstInChance: int | None
    raisedFirstIn: int | None
    foldBbToStealChance: int | None
    foldedBbToSteal: int | None
    foldSbToStealChance: int | None
    foldedSbToSteal: int | None
    street1CBChance: int | None
    street1CBDone: int | None
    street2CBChance: int | None
    street2CBDone: int | None
    street3CBChance: int | None
    street3CBDone: int | None
    street4CBChance: int | None
    street4CBDone: int | None
    foldToStreet1CBChance: int | None
    foldToStreet1CBDone: int | None
    foldToStreet2CBChance: int | None
    foldToStreet2CBDone: int | None
    foldToStreet3CBChance: int | None
    foldToStreet3CBDone: int | None
    foldToStreet4CBChance: int | None
    foldToStreet4CBDone: int | None
    common: int | None
    committed: int | None
    winnings: int | None
    rake: int | None
    rakeDealt: Decimal | None
    rakeContributed: Decimal | None
    rakeWeighted: Decimal | None
    totalProfit: Decimal | None
    allInEV: Decimal | None
    showdownWinnings: int | None
    nonShowdownWinnings: int | None
    street1CheckCallRaiseChance: int | None
    street1CheckCallDone: int | None
    street1CheckRaiseDone: int | None
    street2CheckCallRaiseChance: int | None
    street2CheckCallDone: int | None
    street2CheckRaiseDone: int | None
    street3CheckCallRaiseChance: int | None
    street3CheckCallDone: int | None
    street3CheckRaiseDone: int | None
    street4CheckCallRaiseChance: int | None
    street4CheckCallDone: int | None
    street4CheckRaiseDone: int | None
    street0Calls: int | None
    street1Calls: int | None
    street2Calls: int | None
    street3Calls: int | None
    street4Calls: int | None
    street0Bets: int | None
    street1Bets: int | None
    street2Bets: int | None
    street3Bets: int | None
    street4Bets: int | None
    street0Raises: int | None
    street1Raises: int | None
    street2Raises: int | None
    street3Raises: int | None
    street4Raises: int | None
    street1Discards: int | None
    street2Discards: int | None
    street3Discards: int | None


class Rank(BaseModel):
    """Rank model for player ranks."""

    id: int
    name: str


class RawHands(BaseModel):
    """RawHands model for raw hand history data."""

    id: int
    handId: int
    rawHand: str
    complain: bool


class RawTourneys(BaseModel):
    """RawTourneys model for raw tournament data."""

    id: int
    tourneyId: int
    rawTourney: str
    complain: bool


class Sessions(BaseModel):
    """Sessions model for poker playing sessions."""

    id: int
    weekId: int | None
    monthId: int | None
    sessionStart: datetime
    sessionEnd: datetime


class SessionsCache(BaseModel):
    """SessionsCache model for cached session statistics."""

    id: int
    sessionId: int | None
    startTime: datetime
    endTime: datetime
    gametypeId: int | None
    playerId: int | None
    n: int | None
    street0VPIChance: int | None
    street0VPI: int | None
    street0AggrChance: int | None
    street0Aggr: int | None
    street0CalledRaiseChance: int | None
    street0CalledRaiseDone: int | None
    street0_2BChance: int | None
    street0_2BDone: int | None
    street0_3BChance: int | None
    street0_3BDone: int | None
    street0_4BChance: int | None
    street0_4BDone: int | None
    street0_C4BChance: int | None
    street0_C4BDone: int | None
    street0_FoldTo2BChance: int | None
    street0_FoldTo2BDone: int | None
    street0_FoldTo3BChance: int | None
    street0_FoldTo3BDone: int | None
    street0_FoldTo4BChance: int | None
    street0_FoldTo4BDone: int | None
    street0_SqueezeChance: int | None
    street0_SqueezeDone: int | None
    raiseToStealChance: int | None
    raiseToStealDone: int | None
    stealChance: int | None
    stealDone: int | None
    success_Steal: int | None
    street1Seen: int | None
    street2Seen: int | None
    street3Seen: int | None
    street4Seen: int | None
    sawShowdown: int | None
    street1Aggr: int | None
    street2Aggr: int | None
    street3Aggr: int | None
    street4Aggr: int | None
    otherRaisedStreet0: int | None
    otherRaisedStreet1: int | None
    otherRaisedStreet2: int | None
    otherRaisedStreet3: int | None
    otherRaisedStreet4: int | None
    foldToOtherRaisedStreet0: int | None
    foldToOtherRaisedStreet1: int | None
    foldToOtherRaisedStreet2: int | None
    foldToOtherRaisedStreet3: int | None
    foldToOtherRaisedStreet4: int | None
    wonWhenSeenStreet1: int | None
    wonWhenSeenStreet2: int | None
    wonWhenSeenStreet3: int | None
    wonWhenSeenStreet4: int | None
    wonAtSD: int | None
    raiseFirstInChance: int | None
    raisedFirstIn: int | None
    foldBbToStealChance: int | None
    foldedBbToSteal: int | None
    foldSbToStealChance: int | None
    foldedSbToSteal: int | None
    street1CBChance: int | None
    street1CBDone: int | None
    street2CBChance: int | None
    street2CBDone: int | None
    street3CBChance: int | None
    street3CBDone: int | None
    street4CBChance: int | None
    street4CBDone: int | None
    foldToStreet1CBChance: int | None
    foldToStreet1CBDone: int | None
    foldToStreet2CBChance: int | None
    foldToStreet2CBDone: int | None
    foldToStreet3CBChance: int | None
    foldToStreet3CBDone: int | None
    foldToStreet4CBChance: int | None
    foldToStreet4CBDone: int | None
    common: int | None
    committed: int | None
    winnings: int | None
    rake: int | None
    rakeDealt: Decimal | None
    rakeContributed: Decimal | None
    rakeWeighted: Decimal | None
    totalProfit: Decimal | None
    allInEV: Decimal | None
    showdownWinnings: int | None
    nonShowdownWinnings: int | None
    street1CheckCallRaiseChance: int | None
    street1CheckCallDone: int | None
    street1CheckRaiseDone: int | None
    street2CheckCallRaiseChance: int | None
    street2CheckCallDone: int | None
    street2CheckRaiseDone: int | None
    street3CheckCallRaiseChance: int | None
    street3CheckCallDone: int | None
    street3CheckRaiseDone: int | None
    street4CheckCallRaiseChance: int | None
    street4CheckCallDone: int | None
    street4CheckRaiseDone: int | None
    street0Calls: int | None
    street1Calls: int | None
    street2Calls: int | None
    street3Calls: int | None
    street4Calls: int | None
    street0Bets: int | None
    street1Bets: int | None
    street2Bets: int | None
    street3Bets: int | None
    street4Bets: int | None
    street0Raises: int | None
    street1Raises: int | None
    street2Raises: int | None
    street3Raises: int | None
    street4Raises: int | None
    street1Discards: int | None
    street2Discards: int | None
    street3Discards: int | None


class Settings(BaseModel):
    """Settings model for application settings."""

    version: int


class Sites(BaseModel):
    """Sites model for poker sites."""

    id: int
    name: str
    code: str


class StartCards(BaseModel):
    """StartCards model for starting hand cards."""

    id: int
    category: str
    name: str
    rank: int
    combinations: int


class TourneyTypes(BaseModel):
    """TourneyTypes model for tournament types."""

    id: int
    siteId: int
    currency: str | None
    buyin: int | None
    fee: int | None
    category: str | None
    limitType: str | None
    buyInChips: int | None
    stack: str | None
    maxSeats: int | None
    rebuy: bool | None
    rebuyCost: int | None
    rebuyFee: int | None
    rebuyChips: int | None
    addOn: bool | None
    addOnCost: int | None
    addOnFee: int | None
    addOnChips: int | None
    knockout: bool | None
    koBounty: int | None
    progressive: bool | None
    step: bool | None
    stepNo: int | None
    chance: bool | None
    chanceCount: int | None
    speed: str | None
    shootout: bool | None
    matrix: bool | None
    multiEntry: bool | None
    reEntry: bool | None
    fast: bool | None
    newToGame: bool | None
    homeGame: bool | None
    split: bool | None
    sng: bool | None
    fifty50: bool | None
    time: bool | None
    timeAmt: int | None
    satellite: bool | None
    doubleOrNothing: bool | None
    cashOut: bool | None
    onDemand: bool | None
    flighted: bool | None
    guarantee: bool | None
    guaranteeAmt: int | None


class Tourneys(BaseModel):
    """Tourneys model for tournament data."""

    id: int
    tourneyTypeId: int | None
    sessionId: int | None
    siteTourneyNo: int | None
    entries: int | None
    prizepool: int | None
    startTime: datetime | None
    endTime: datetime | None
    tourneyName: str | None
    totalRebuyCount: int | None
    totalAddOnCount: int | None
    added: int | None
    addedCurrency: str | None
    comment: str | None
    commentTs: datetime | None


class TourneysCache(BaseModel):
    """TourneysCache model for cached tournament statistics."""

    id: int
    sessionId: int | None
    startTime: datetime
    endTime: datetime
    tourneyId: int | None
    playerId: int | None
    n: int | None
    street0VPIChance: int | None
    street0VPI: int | None
    street0AggrChance: int | None
    street0Aggr: int | None
    street0CalledRaiseChance: int | None
    street0CalledRaiseDone: int | None
    street0_2BChance: int | None
    street0_2BDone: int | None
    street0_3BChance: int | None
    street0_3BDone: int | None
    street0_4BChance: int | None
    street0_4BDone: int | None
    street0_C4BChance: int | None
    street0_C4BDone: int | None
    street0_FoldTo2BChance: int | None
    street0_FoldTo2BDone: int | None
    street0_FoldTo3BChance: int | None
    street0_FoldTo3BDone: int | None
    street0_FoldTo4BChance: int | None
    street0_FoldTo4BDone: int | None
    street0_SqueezeChance: int | None
    street0_SqueezeDone: int | None
    raiseToStealChance: int | None
    raiseToStealDone: int | None
    stealChance: int | None
    stealDone: int | None
    success_Steal: int | None
    street1Seen: int | None
    street2Seen: int | None
    street3Seen: int | None
    street4Seen: int | None
    sawShowdown: int | None
    street1Aggr: int | None
    street2Aggr: int | None
    street3Aggr: int | None
    street4Aggr: int | None
    otherRaisedStreet0: int | None
    otherRaisedStreet1: int | None
    otherRaisedStreet2: int | None
    otherRaisedStreet3: int | None
    otherRaisedStreet4: int | None
    foldToOtherRaisedStreet0: int | None
    foldToOtherRaisedStreet1: int | None
    foldToOtherRaisedStreet2: int | None
    foldToOtherRaisedStreet3: int | None
    foldToOtherRaisedStreet4: int | None
    wonWhenSeenStreet1: int | None
    wonWhenSeenStreet2: int | None
    wonWhenSeenStreet3: int | None
    wonWhenSeenStreet4: int | None
    wonAtSD: int | None
    raiseFirstInChance: int | None
    raisedFirstIn: int | None
    foldBbToStealChance: int | None
    foldedBbToSteal: int | None
    foldSbToStealChance: int | None
    foldedSbToSteal: int | None
    street1CBChance: int | None
    street1CBDone: int | None
    street2CBChance: int | None
    street2CBDone: int | None
    street3CBChance: int | None
    street3CBDone: int | None
    street4CBChance: int | None
    street4CBDone: int | None
    foldToStreet1CBChance: int | None
    foldToStreet1CBDone: int | None
    foldToStreet2CBChance: int | None
    foldToStreet2CBDone: int | None
    foldToStreet3CBChance: int | None
    foldToStreet3CBDone: int | None
    foldToStreet4CBChance: int | None
    foldToStreet4CBDone: int | None
    common: int | None
    committed: int | None
    winnings: int | None
    rake: int | None
    rakeDealt: Decimal | None
    rakeContributed: Decimal | None
    rakeWeighted: Decimal | None
    totalProfit: Decimal | None
    allInEV: Decimal | None
    showdownWinnings: int | None
    nonShowdownWinnings: int | None
    street1CheckCallRaiseChance: int | None
    street1CheckCallDone: int | None
    street1CheckRaiseDone: int | None
    street2CheckCallRaiseChance: int | None
    street2CheckCallDone: int | None
    street2CheckRaiseDone: int | None
    street3CheckCallRaiseChance: int | None
    street3CheckCallDone: int | None
    street3CheckRaiseDone: int | None
    street4CheckCallRaiseChance: int | None
    street4CheckCallDone: int | None
    street4CheckRaiseDone: int | None
    street0Calls: int | None
    street1Calls: int | None
    street2Calls: int | None
    street3Calls: int | None
    street4Calls: int | None
    street0Bets: int | None
    street1Bets: int | None
    street2Bets: int | None
    street3Bets: int | None
    street4Bets: int | None
    street0Raises: int | None
    street1Raises: int | None
    street2Raises: int | None
    street3Raises: int | None
    street4Raises: int | None
    street1Discards: int | None
    street2Discards: int | None
    street3Discards: int | None


class TourneysPlayers(BaseModel):
    """TourneysPlayers model for tournament player data."""

    id: int
    tourneyId: int | None
    playerId: int | None
    entryId: int | None
    rank: int | None
    winnings: int | None
    winningsCurrency: str | None
    rebuyCount: int | None
    addOnCount: int | None
    koCount: float | None
    comment: str | None
    commentTs: str | None


class Weeks(BaseModel):
    """Weeks model for weekly time periods."""

    id: int
    weekStart: datetime
