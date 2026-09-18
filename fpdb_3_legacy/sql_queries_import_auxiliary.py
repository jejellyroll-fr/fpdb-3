"""Auxiliary hand and import-file persistence queries."""

from __future__ import annotations


def import_auxiliary_queries() -> dict[str, str]:
    """Return board, pot, and import-file persistence queries."""
    query: dict[str, str] = {}
    query["store_boards"] = """insert into Boards (
                    handId,
                    boardId,
                    boardcard1,
                    boardcard2,
                    boardcard3,
                    boardcard4,
                    boardcard5
           )
           values (
                %s, %s, %s, %s, %s,
                %s, %s
            )"""

    # One row per board and community street, classified once at import time
    # (#295). The column order is board_features.BOARD_FEATURE_COLUMNS, and
    # test_board_features guards the two against drift.
    query["store_board_features"] = """insert into BoardFeatures (
                    handId,
                    boardId,
                    street,
                    streetName,
                    cardCount,
                    textureMask,
                    runoutMask,
                    topRank,
                    suitStructure,
                    pairing,
                    rankBucket,
                    connectivity
           )
           values (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            )"""

    # One row per persisted decision situation (#294, stored since #305).
    # The column order is analytics_lifecycle.HANDS_SITUATION_COLUMNS, and
    # test_analytics_lifecycle guards the two against drift.
    query["store_hands_situations"] = """insert into HandsSituations (
                    handId,
                    playerId,
                    actionNo,
                    street,
                    streetName,
                    position,
                    relativePosition,
                    inPosition,
                    effectiveStack,
                    effectiveStackBB,
                    stackBucket,
                    sprBefore,
                    isHero,
                    potType,
                    multiway,
                    playersInHand,
                    preflopAggressor,
                    isPreflopAggressor,
                    streetAggressor,
                    isAggressor,
                    previousAggressor,
                    isPreviousAggressor,
                    previousAggressorLed,
                    previousAggressorChecked,
                    previousAggressorPosition,
                    inPositionVsPreviousAggressor,
                    aggressorCheckedThisStreet,
                    previousRaiser,
                    isPreviousRaiser,
                    toCall,
                    potBefore,
                    potAfter,
                    potOddsBp,
                    facingAction,
                    facingPlayer,
                    facingPosition,
                    inPositionVsFacing,
                    facingAmount,
                    facingSizingBp,
                    facingAllIn,
                    betLevelFaced,
                    raisesBefore,
                    callsBefore,
                    callersBetweenRaises,
                    callersSinceRaise,
                    streetActions,
                    previousStreetActions,
                    board,
                    response,
                    isAllIn,
                    role,
                    labels,
                    primaryLabel,
                    groupName,
                    enumKey,
                    enumResponse,
                    enumAnswers,
                    situationVersion
           )
           values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
           )"""

    query["store_hands_pots"] = """insert into HandsPots (
                    handId,
                    potId,
                    boardId,
                    hiLo,
                    playerId,
                    pot,
                    collected,
                    rake
           )
           values (
                %s, %s, %s, %s,
                %s, %s, %s, %s
           )"""

    ################################
    # queries for Files Table
    ################################

    query["get_id"] = """
                    SELECT id
                    FROM Files
                    WHERE file=%s"""

    query["store_file"] = """  insert into Files (
                    file,
                    site,
                    startTime,
                    lastUpdate,
                    hands,
                    storedHands,
                    dups,
                    partial,
                    skipped,
                    errs,
                    ttime100,
                    finished)
           values (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            )"""

    query["update_file"] = """
                UPDATE Files SET
                type=%s,
                lastUpdate=%s,
                endTime=%s,
                hands=hands+%s,
                storedHands=storedHands+%s,
                dups=dups+%s,
                partial=partial+%s,
                skipped=skipped+%s,
                errs=errs+%s,
                ttime100=ttime100+%s,
                finished=%s
                WHERE id=%s"""
    return query
