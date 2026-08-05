"""Player automatic-note persistence and reporting queries."""

from __future__ import annotations


def player_auto_note_queries() -> dict[str, str]:
    """Return automatic-note write, lookup, search, and summary queries."""
    query: dict[str, str] = {}
    query["find_player_auto_note"] = """select id
            from PlayerAutoNotes
            where playerId=%s and handId=%s and ruleId=%s and ruleVersion=%s"""

    query["store_player_auto_note"] = """insert into PlayerAutoNotes (
                    playerId,
                    handId,
                    ruleId,
                    ruleVersion,
                    noteText,
                    evidence
           )
           values (
                %s, %s, %s, %s, %s, %s
           )"""

    query["update_player_auto_note"] = """update PlayerAutoNotes
            set noteText=%s, evidence=%s, updatedTs=CURRENT_TIMESTAMP
            where id=%s"""

    query["count_player_auto_notes"] = """select count(*)
            from PlayerAutoNotes
            where playerId=%s"""

    query["get_player_auto_notes"] = """select
                pan.id,
                pan.handId,
                pan.ruleId,
                pan.ruleVersion,
                pan.noteText,
                pan.evidence,
                pan.createdTs,
                pan.updatedTs,
                h.siteHandNo,
                h.startTime
            from PlayerAutoNotes pan
            left join Hands h on pan.handId=h.id
            where pan.playerId=%s
            order by pan.createdTs desc, pan.id desc"""

    query["search_players_with_auto_notes"] = """select distinct
                p.id,
                p.name,
                p.siteId
            from Players p
            join PlayerAutoNotes pan on pan.playerId=p.id
            where lower(p.name) like lower(%s)
            order by p.name
            limit 50"""

    query["get_recent_player_auto_notes"] = """select
                pan.id,
                pan.playerId,
                p.name,
                pan.handId,
                h.siteHandNo,
                pan.ruleId,
                pan.ruleVersion,
                pan.noteText,
                pan.evidence,
                pan.createdTs,
                pan.updatedTs,
                h.startTime
            from PlayerAutoNotes pan
            join Players p on pan.playerId=p.id
            left join Hands h on pan.handId=h.id
            left join Gametypes g on h.gametypeId=g.id
            /*AUTONOTE_FILTERS*/
            order by pan.createdTs desc, pan.id desc
            limit %s"""

    query["get_auto_note_player_summary"] = """select
                pan.playerId,
                p.name,
                count(*) as noteCount,
                max(pan.createdTs) as lastNoteTs
            from PlayerAutoNotes pan
            join Players p on pan.playerId=p.id
            left join Hands h on pan.handId=h.id
            left join Gametypes g on h.gametypeId=g.id
            /*AUTONOTE_FILTERS*/
            group by pan.playerId, p.name
            order by noteCount desc, p.name
            limit %s"""

    query["get_auto_note_rule_summary"] = """select
                pan.ruleId,
                count(*) as noteCount
            from PlayerAutoNotes pan
            join Players p on pan.playerId=p.id
            left join Hands h on pan.handId=h.id
            left join Gametypes g on h.gametypeId=g.id
            /*AUTONOTE_FILTERS*/
            group by pan.ruleId
            order by noteCount desc, pan.ruleId
            limit %s"""

    query["player_has_any_notes"] = """select
            case
                when exists (
                    select 1 from Players
                    where id=%s and comment is not null and comment <> ''
                ) then 1
                when exists (
                    select 1 from PlayerAutoNotes
                    where playerId=%s
                ) then 1
                else 0
            end"""
    return query

