"""Root hand persistence query."""

from __future__ import annotations


def hand_root_persistence_queries() -> dict[str, str]:
    """Return the root Hands insert query."""
    query: dict[str, str] = {}
    query["store_hand"] = """insert into Hands (
                                        id,
                                        tablename,
                                        sitehandno,
                                        tourneyId,
                                        gametypeid,
                                        sessionId,
                                        fileId,
                                        startTime,
                                        importtime,
                                        seats,
                                        heroSeat,
                                        maxPosition,
                                        texture,
                                        playersVpi,
                                        boardcard1,
                                        boardcard2,
                                        boardcard3,
                                        boardcard4,
                                        boardcard5,
                                        runItTwice,
                                        playersAtStreet1,
                                        playersAtStreet2,
                                        playersAtStreet3,
                                        playersAtStreet4,
                                        playersAtShowdown,
                                        street0Raises,
                                        street1Raises,
                                        street2Raises,
                                        street3Raises,
                                        street4Raises,
                                        street0Pot,
                                        street1Pot,
                                        street2Pot,
                                        street3Pot,
                                        street4Pot,
                                        finalPot,
                                        bombPot,
                                        splashPot
                                         )
                                         values
                                          (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                           %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                           %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                           %s, %s, %s, %s, %s)"""
    return query
