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
    three_bet_opp: bool
    saw_flop: bool
    saw_showdown: bool
    won: float
    all_in_ev: float
    steal_att: bool
    steal_opp: bool
    rfi: bool
    position: int | None
    cbet: bool
    cbet_opp: bool
    f_cbet_opp: bool
    car: int
    hand_id: int
    hand_no: str
    pt4_player_id: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pt4PlayerStat":
        """Create Pt4PlayerStat from dictionary (raw query result)."""
        return cls(
            player_name=data.get("player_name", ""),
            vpip=bool(data.get("flg_vpip", False)),
            pfr=bool(data.get("pfr", False)),
            three_bet=bool(data.get("three_bet", False)),
            three_bet_opp=bool(data.get("three_bet_opp", False)),
            saw_flop=bool(data.get("flg_f_saw", False)),
            saw_showdown=bool(data.get("flg_showdown", False)),
            won=float(data.get("amt_won", 0) or 0),
            all_in_ev=float(data.get("all_in_ev", 0) or 0),
            steal_att=bool(data.get("flg_steal_att", False)),
            steal_opp=bool(data.get("flg_steal_opp", False)),
            rfi=bool(data.get("rfi", False)),
            position=data.get("position"),
            cbet=bool(data.get("cbet", False)),
            cbet_opp=bool(data.get("cbet_opp", False)),
            f_cbet_opp=bool(data.get("f_cbet_opp", False)),
            car=data.get("car", 0) or 0,
            hand_id=data.get("hand_id", 0) or 0,
            hand_no=str(data.get("hand_no", "") or ""),
            pt4_player_id=data.get("pt4_player_id", 0) or 0,
        )
