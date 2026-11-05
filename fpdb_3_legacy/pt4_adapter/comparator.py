"""PT4 vs FPDB comparison utilities."""

from dataclasses import dataclass
from typing import Any


@dataclass
class StatComparison:
    """Result of comparing a single stat between PT4 and FPDB."""

    name: str
    pt4_value: Any
    fpdb_value: Any
    matched: bool
    delta: float | None = None
    player: str = ""


# One row per player of one hand. get_stats_from_hand would not do: it returns the HUD's
# aggregates over a stat range, keyed by player id.
FPDB_STATS_PER_HAND = (
    "SELECT p.name, hp.street0VPI, hp.street0Aggr, hp.street0_3BDone, hp.street1Seen "  # nosec B608  # nosemgrep
    "FROM HandsPlayers hp "
    "INNER JOIN Players p ON hp.playerId = p.id "
    "WHERE hp.handId = %s"
)

# (compared stat, key in the PT4 row, key in the FPDB row)
_COMPARED_STATS = (
    ("vpip", "flg_vpip", "street0VPI"),
    ("pfr", "pfr", "street0Aggr"),
    ("three_bet", "three_bet", "street0_3BDone"),
    ("saw_flop", "flg_f_saw", "street1Seen"),
)


def _get_fpdb_stats_for_hand(fpdb_db, fpdb_hand_id: int) -> dict[str, dict[str, Any]]:
    """Return player name -> this hand's HandsPlayers flags."""
    placeholder = fpdb_db.sql.query.get("placeholder", "%s")
    cursor = fpdb_db.connection.cursor()
    cursor.execute(FPDB_STATS_PER_HAND.replace("%s", placeholder), (fpdb_hand_id,))  # nosemgrep
    return {
        row[0]: {"street0VPI": row[1], "street0Aggr": row[2], "street0_3BDone": row[3], "street1Seen": row[4]}
        for row in cursor.fetchall()
    }


def compare_hand(
    pt4_conn,
    fpdb_db,
    pt4_hand_id: int,
    fpdb_hand_id: int,
) -> list[StatComparison]:
    """Compare stats between PT4 and FPDB for a given hand.

    A player found on one side only is reported as a failed "seated" comparison,
    so that a hand no name matches on cannot pass for a hand without differences.

    Args:
        pt4_conn: psycopg connection to PT4 database
        fpdb_db: fpdb_3_legacy Database instance
        pt4_hand_id: PT4 hand ID
        fpdb_hand_id: FPDB hand ID

    Returns:
        List of StatComparison objects for each compared stat
    """
    from fpdb_3_legacy.pt4_adapter.queries import get_pt4_stats_for_hand

    pt4_by_name = {s["player_name"]: s for s in get_pt4_stats_for_hand(pt4_conn, pt4_hand_id)}
    fpdb_by_name = _get_fpdb_stats_for_hand(fpdb_db, fpdb_hand_id)

    comparisons = []
    for player_name in sorted(pt4_by_name.keys() | fpdb_by_name.keys()):
        pt4_player = pt4_by_name.get(player_name)
        fpdb_player = fpdb_by_name.get(player_name)
        if pt4_player is None or fpdb_player is None:
            comparisons.append(StatComparison(
                name="seated",
                pt4_value=pt4_player is not None,
                fpdb_value=fpdb_player is not None,
                matched=False,
                player=player_name,
            ))
            continue
        for stat, pt4_key, fpdb_key in _COMPARED_STATS:
            comparison = _compare_bool(stat, pt4_player.get(pt4_key), fpdb_player.get(fpdb_key))
            comparison.player = player_name
            comparisons.append(comparison)

    return comparisons


def _compare_bool(name: str, pt4_val: Any, fpdb_val: Any) -> StatComparison:
    """Compare boolean stats with exact matching."""
    pt4_bool = bool(pt4_val) if pt4_val is not None else False
    fpdb_bool = bool(fpdb_val) if fpdb_val is not None else False
    matched = pt4_bool == fpdb_bool
    return StatComparison(
        name=name,
        pt4_value=pt4_bool,
        fpdb_value=fpdb_bool,
        matched=matched,
    )


def _compare_ratio(
    name: str,
    pt4_num: Any,
    pt4_den: Any,
    fpdb_stat: Any,
    tolerance: float = 0.01,
) -> StatComparison:
    """Compare ratio stats with tolerance."""
    try:
        if pt4_den and int(pt4_den) > 0:
            pt4_ratio = float(pt4_num) / float(pt4_den)
        else:
            pt4_ratio = 0.0
        fpdb_ratio = float(fpdb_stat) if fpdb_stat else 0.0
        delta = abs(pt4_ratio - fpdb_ratio)
        matched = delta <= tolerance
        return StatComparison(
            name=name,
            pt4_value=pt4_ratio,
            fpdb_value=fpdb_ratio,
            matched=matched,
            delta=delta,
        )
    except (ValueError, TypeError, ZeroDivisionError):
        return StatComparison(
            name=name,
            pt4_value=None,
            fpdb_value=fpdb_stat,
            matched=False,
        )
