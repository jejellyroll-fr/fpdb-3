"""Hand action, stove, showdown, and cashout queries."""

from __future__ import annotations


def hand_artifact_queries() -> dict[str, str]:
    """Return persistence and lookup queries for secondary hand artifacts."""
    query: dict[str, str] = {}
    query["store_hands_actions"] = """insert into HandsActions (
                    handId,
                    playerId,
                    street,
                    actionNo,
                    streetActionNo,
                    actionId,
                    amount,
                    raiseTo,
                    amountCalled,
                    numDiscarded,
                    cardsDiscarded,
                    allIn
           )
           values (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            )"""

    query["store_hands_stove"] = """insert into HandsStove (
                    handId,
                    playerId,
                    streetId,
                    boardId,
                    hiLo,
                    rankId,
                    value,
                    cards,
                    ev
           )
           values (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
           )"""

    query["store_hands_showdown"] = """insert into HandsShowdown (
                    handId,
                    playerId,
                    combo,
                    cards
           )
           values (
                %s, %s, %s, %s
           )"""

    query["get_hands_showdown"] = """select p.name, hs.combo, hs.cards
            from HandsShowdown hs, Players p
            where hs.handId=%s and hs.playerId=p.id"""

    query["store_hands_cashout"] = """insert into HandsCashout (
                    handId,
                    playerId,
                    amount,
                    fee
           )
           values (
                %s, %s, %s, %s
           )"""

    query["get_hands_cashout"] = """select p.name, hc.amount, hc.fee
            from HandsCashout hc, Players p
            where hc.handId=%s and hc.playerId=p.id"""

    # Le splash est paye hors du pot : il a sa colonne sur HandsPlayers plutot
    # qu'une table a lui, et se relit avec les joueurs de la main.
    query["get_hands_splash"] = """select p.name, hp.splashWinnings
            from HandsPlayers hp, Players p
            where hp.handId=%s and hp.playerId=p.id and hp.splashWinnings<>0"""
    return query

