"""PT4 data models."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Pt4PlayerStat:
    """Parsed PT4 player statistics from cash_hand_player_statistics."""

    player_name: str
    vpip: bool
    pfr: bool
    three_bet: bool
    three_bet_opp: int
    saw_flop: bool
    saw_showdown: bool
    won: float
    all_in_ev: float
    steal_opp: bool
    rfi: bool
    position: str
    three_bet_count: int
    three_bet_opp_count: int
    three_bet_done: bool
    cbet: int
    cbet_opp: int
    f_cbet: int
    f_cbet_opp: int
    car: int
    car_opp: int
    hand_id: int
    pt4_player_id: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pt4PlayerStat":
        """Create Pt4PlayerStat from dictionary (raw query result)."""
        return cls(
            player_name=data.get("player_name", ""),
            vpip=bool(data.get("flg_vpip", False)),
            pfr=bool(data.get("pfr", False)),
            three_bet=bool(data.get("three_bet", False)),
            three_bet_opp=data.get("three_bet_opp", 0) or 0,
            saw_flop=bool(data.get("flg_saw_flop", False)),
            saw_showdown=bool(data.get("flg_saw_showdown", False)),
            won=float(data.get("amt_won", 0) or 0),
            all_in_ev=float(data.get("all_in_ev", 0) or 0),
            steal_opp=bool(data.get("flg_steal_att", False)),
            rfi=bool(data.get("rfi", False)),
            position=data.get("enum_position", ""),
            three_bet_count=data.get("three_bet_count", 0) or 0,
            three_bet_opp_count=data.get("three_bet_opp_count", 0) or 0,
            three_bet_done=bool(data.get("three_bet_done", False)),
            cbet=data.get("cbet", 0) or 0,
            cbet_opp=data.get("cbet_opp", 0) or 0,
            f_cbet=data.get("f_cbet", 0) or 0,
            f_cbet_opp=data.get("f_cbet_opp", 0) or 0,
            car=data.get("car", 0) or 0,
            car_opp=data.get("car_opp", 0) or 0,
            hand_id=data.get("hand_id", 0) or 0,
            pt4_player_id=data.get("pt4_player_id", 0) or 0,
        )
