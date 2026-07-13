"""PT4 vs FPDB comparison utilities."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class StatComparison:
    """Result of comparing a single stat between PT4 and FPDB."""

    name: str
    pt4_value: Any
    fpdb_value: Any
    matched: bool
    delta: Optional[float] = None


def compare_hand(
    pt4_conn,
    fpdb_db,
    pt4_hand_id: int,
    fpdb_hand_id: int,
) -> list[StatComparison]:
    """Compare stats between PT4 and FPDB for a given hand.

    Args:
        pt4_conn: psycopg connection to PT4 database
        fpdb_db: fpdb_3_legacy Database instance
        pt4_hand_id: PT4 hand ID
        fpdb_hand_id: FPDB hand ID

    Returns:
        List of StatComparison objects for each compared stat
    """
    from fpdb_3_legacy.pt4_adapter.queries import get_pt4_stats_for_hand

    comparisons = []

    # Get PT4 stats
    pt4_stats = get_pt4_stats_for_hand(pt4_conn, pt4_hand_id)

    # Get FPDB stats
    fpdb_stats = fpdb_db.get_stats_from_hand(fpdb_hand_id, "ring")

    # Build lookup by player name for PT4
    pt4_by_name = {s["player_name"]: s for s in pt4_stats}

    # Compare each player
    for player_name, stat_dict in fpdb_stats.items():
        if player_name not in pt4_by_name:
            continue

        pt4_player = pt4_by_name[player_name]

        # Compare vpip
        comparisons.append(_compare_bool(
            "vpip", pt4_player.get("flg_vpip"), stat_dict.get("vpip"),
        ))

        # Compare pfr
        comparisons.append(_compare_bool(
            "pfr", pt4_player.get("pfr"), stat_dict.get("pfr"),
        ))

        # Compare three_bet
        comparisons.append(_compare_bool(
            "three_bet", pt4_player.get("three_bet"), stat_dict.get("tb_0"),
        ))

        # Compare saw_flop
        comparisons.append(_compare_bool(
            "saw_flop", pt4_player.get("flg_saw_flop"), stat_dict.get("saw_f"),
        ))

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
