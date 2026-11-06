"""PT4 PostgreSQL queries."""

from typing import Any

PT4_STATS_PER_HAND = """
SELECT
    p.player_name,
    s.flg_vpip,
    s.cnt_p_raise > 0            AS pfr,
    s.flg_p_3bet                 AS three_bet,
    s.flg_p_3bet_opp             AS three_bet_opp,
    s.flg_f_saw,
    s.flg_showdown,
    s.amt_won,
    s.amt_expected_won           AS all_in_ev,
    s.flg_steal_att,
    s.flg_steal_opp,
    s.flg_p_open                 AS rfi,
    s.position,
    s.flg_f_cbet                 AS cbet,
    s.flg_f_cbet_opp             AS cbet_opp,
    s.flg_f_cbet_def_opp         AS f_cbet_opp,
    s.cnt_p_call                 AS car,
    s.id_hand                    AS hand_id,
    h.hand_no,
    s.id_player                  AS pt4_player_id
FROM cash_hand_player_statistics s
JOIN cash_hand_summary h ON h.id_hand = s.id_hand
JOIN player p ON p.id_player = s.id_player
WHERE s.id_hand = %s
"""


def get_pt4_stats_for_hand(conn, pt4_hand_id: int) -> list[dict[str, Any]]:
    """Get PT4 statistics for a specific hand.

    Args:
        conn: psycopg connection to PT4 database
        pt4_hand_id: PT4 hand ID to query

    Returns:
        List of dictionaries containing player stats
    """
    with conn.cursor() as cur:
        cur.execute(PT4_STATS_PER_HAND, (pt4_hand_id,))
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
