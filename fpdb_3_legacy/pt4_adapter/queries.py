"""PT4 PostgreSQL queries."""

from typing import Any

PT4_STATS_PER_HAND = """
SELECT
    p.player_name,
    s.flg_vpip,
    s.flg_p_first_raise          AS pfr,
    s.flg_p_3bet                 AS three_bet,
    s.cnt_p_3bet_opp             AS three_bet_opp,
    s.flg_saw_flop,
    s.flg_saw_showdown,
    s.amt_won,
    s.amt_expected_won           AS all_in_ev,
    s.flg_steal_att,
    s.flg_p_first_raise_open     AS rfi,
    s.enum_position              AS position,
    s.cnt_p_3bet                 AS three_bet_count,
    s.cnt_p_3bet_opp             AS three_bet_opp_count,
    s.flg_p_3bet                 AS three_bet_done,
    s.cnt_p_cbet                 AS cbet,
    s.cnt_p_cbet_opp             AS cbet_opp,
    s.cnt_p_f_cbet               AS f_cbet,
    s.cnt_p_f_cbet_opp           AS f_cbet_opp,
    s.cnt_p_call                 AS car,
    s.cnt_p_call_opp             AS car_opp,
    s.hand_no                    AS hand_id,
    s.player_id                  AS pt4_player_id
FROM cash_hand_player_statistics s
JOIN player p ON p.player_id = s.id_player
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
