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

