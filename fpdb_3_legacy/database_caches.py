"""Statistics cache writers for the fpdb database.

Split out of Database.py: these methods own the HudCache, CardsCache,
PositionsCache, Sessions, SessionsCache and TourneysCache tables, whose rows
aggregate hands rather than record them.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from time import strftime
from typing import TYPE_CHECKING, Any

import pytz

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")

CACHE_KEYS = [
    "n",
    "street0VPIChance",
    "street0VPI",
    "street0AggrChance",
    "street0Aggr",
    "street0CalledRaiseChance",
    "street0CalledRaiseDone",
    "street0FaceRaise",
    "street0_2BChance",
    "street0_2BDone",
    "street0_3BChance",
    "street0_3BDone",
    "street0_4BChance",
    "street0_4BDone",
    "street0_C4BChance",
    "street0_C4BDone",
    "street0_FoldTo2BChance",
    "street0_FoldTo2BDone",
    "street0_FoldTo3BChance",
    "street0_FoldTo3BDone",
    "street0_FoldTo4BChance",
    "street0_FoldTo4BDone",
    "street0_SqueezeChance",
    "street0_SqueezeDone",
    "raiseToStealChance",
    "raiseToStealDone",
    "stealChance",
    "stealDone",
    "success_Steal",
    "street1Seen",
    "street2Seen",
    "street3Seen",
    "street4Seen",
    "sawShowdown",
    "street1Aggr",
    "street2Aggr",
    "street3Aggr",
    "street4Aggr",
    "otherRaisedStreet0",
    "otherRaisedStreet1",
    "otherRaisedStreet2",
    "otherRaisedStreet3",
    "otherRaisedStreet4",
    "foldToOtherRaisedStreet0",
    "foldToOtherRaisedStreet1",
    "foldToOtherRaisedStreet2",
    "foldToOtherRaisedStreet3",
    "foldToOtherRaisedStreet4",
    "wonWhenSeenStreet1",
    "wonWhenSeenStreet2",
    "wonWhenSeenStreet3",
    "wonWhenSeenStreet4",
    "wonAtSD",
    "raiseFirstInChance",
    "raisedFirstIn",
    "foldBbToStealChance",
    "foldedBbToSteal",
    "foldSbToStealChance",
    "foldedSbToSteal",
    "street1CBChance",
    "street1CBDone",
    "street2CBChance",
    "street2CBDone",
    "street3CBChance",
    "street3CBDone",
    "street4CBChance",
    "street4CBDone",
    "foldToStreet1CBChance",
    "foldToStreet1CBDone",
    "foldToStreet2CBChance",
    "foldToStreet2CBDone",
    "foldToStreet3CBChance",
    "foldToStreet3CBDone",
    "foldToStreet4CBChance",
    "foldToStreet4CBDone",
    "common",
    "committed",
    "winnings",
    "rake",
    "rakeDealt",
    "rakeContributed",
    "rakeWeighted",
    "totalProfit",
    "allInEV",
    "showdownWinnings",
    "nonShowdownWinnings",
    "street1CheckCallRaiseChance",
    "street1CheckCallDone",
    "street1CheckRaiseDone",
    "street2CheckCallRaiseChance",
    "street2CheckCallDone",
    "street2CheckRaiseDone",
    "street3CheckCallRaiseChance",
    "street3CheckCallDone",
    "street3CheckRaiseDone",
    "street4CheckCallRaiseChance",
    "street4CheckCallDone",
    "street4CheckRaiseDone",
    "street0Calls",
    "street1Calls",
    "street2Calls",
    "street3Calls",
    "street4Calls",
    "street0Bets",
    "street1Bets",
    "street2Bets",
    "street3Bets",
    "street4Bets",
    "street0Raises",
    "street1Raises",
    "street2Raises",
    "street3Raises",
    "street4Raises",
    "street1Discards",
    "street2Discards",
    "street3Discards",
    "street0Limp",
    "street0OpenLimpChance",
    "street0OpenLimp",
    # Postflop per-street 3-bet — appended at the end so insert/update_hudcache
    # column positions stay aligned with this list (see storeHudCache).
    "street1_3BChance",
    "street1_3BDone",
    "street2_3BChance",
    "street2_3BDone",
    "street3_3BChance",
    "street3_3BDone",
    "street1_4BChance",
    "street1_4BDone",
    "street1_FoldTo4BChance",
    "street1_FoldTo4BDone",
    "street2_4BChance",
    "street2_4BDone",
    "street2_FoldTo4BChance",
    "street2_FoldTo4BDone",
    "street3_4BChance",
    "street3_4BDone",
    "street3_FoldTo4BChance",
    "street3_FoldTo4BDone",
    "street1OpenChance",
    "street1OpenDone",
    "street2OpenChance",
    "street2OpenDone",
    "street3OpenChance",
    "street3OpenDone",
    "flg_f_fold",
    "flg_t_fold",
    "flg_r_fold",
    "street1FirstRaise",
    "street2FirstRaise",
    "street3FirstRaise",
    "street1FaceRaise",
    "street2FaceRaise",
    "street3FaceRaise",
    "flg_f_donk_def_opp",
    "flg_t_float_opp",
    "flg_t_float",
    "flg_t_float_def_opp",
    "flg_r_float_opp",
    "flg_r_float",
    "flg_r_float_def_opp",
    "flg_t_donk_def_opp",
    "flg_r_donk_def_opp",
    # Fold-to-3bet postflop (computed in calc3BetPostflop) — appended at the end.
    "street1_FoldTo3BChance",
    "street1_FoldTo3BDone",
    "street2_FoldTo3BChance",
    "street2_FoldTo3BDone",
    "street3_FoldTo3BChance",
    "street3_FoldTo3BDone",
    # Preflop squeeze defense + limpers faced — appended at the end.
    "street0_FoldToSqueezeChance",
    "street0_FoldToSqueezeDone",
    "street0_FaceLimpers",
    # GenerationPoker open-sizing / limp counts (PT4 cnt_gp_* custom pack).
    "cnt_gp_open_opp",
    "cnt_gp_2x",
    "cnt_gp_os",
    "cnt_gp_limp",
    # Special blinds (dead small/big blind, straddle) — appended at the end.
    "flg_blind_ds",
    "flg_blind_db",
    "flg_blind_k",
    # Faced an all-in + fold response — appended at the end.
    "flg_faced_allin",
    "flg_fold_to_allin",
    # Bet-sizing: flop bet faced (count + basis points of pot) — appended at the end.
    "cnt_f_bet_facing",
    "val_f_bet_facing_bp",
    # Bet-sizing: turn + river bet faced — appended at the end.
    "cnt_t_bet_facing",
    "val_t_bet_facing_bp",
    "cnt_r_bet_facing",
    "val_r_bet_facing_bp",
    # Bet-sizing: preflop raise faced per level (count + basis points) — appended at the end.
    "cnt_p_2bet_facing",
    "val_p_2bet_facing_bp",
    "cnt_p_3bet_facing",
    "val_p_3bet_facing_bp",
    "cnt_p_4bet_facing",
    "val_p_4bet_facing_bp",
    # Bet-sizing: postflop bet made per street (count + basis points) — appended at the end.
    "cnt_f_bet_made",
    "val_f_bet_made_bp",
    "cnt_t_bet_made",
    "val_t_bet_made_bp",
    "cnt_r_bet_made",
    "val_r_bet_made_bp",
    # Bet-sizing: postflop SPR per street (count + SPR*100) — appended at the end.
    "cnt_f_spr",
    "val_f_spr",
    "cnt_t_spr",
    "val_t_spr",
    "cnt_r_spr",
    "val_r_spr",
    # Bet-sizing: size of the first raise made per street (count + basis points) — appended at the end.
    "cnt_p_raise_made",
    "val_p_raise_made_bp",
    "cnt_f_raise_made",
    "val_f_raise_made_bp",
    "cnt_t_raise_made",
    "val_t_raise_made_bp",
    "cnt_r_raise_made",
    "val_r_raise_made_bp",
    # Bet-sizing: postflop raise faced per street and level (count + basis points) — appended at the end.
    "cnt_f_2bet_facing",
    "val_f_2bet_facing_bp",
    "cnt_f_3bet_facing",
    "val_f_3bet_facing_bp",
    "cnt_f_4bet_facing",
    "val_f_4bet_facing_bp",
    "cnt_t_2bet_facing",
    "val_t_2bet_facing_bp",
    "cnt_t_3bet_facing",
    "val_t_3bet_facing_bp",
    "cnt_t_4bet_facing",
    "val_t_4bet_facing_bp",
    "cnt_r_2bet_facing",
    "val_r_2bet_facing_bp",
    "cnt_r_3bet_facing",
    "val_r_3bet_facing_bp",
    "cnt_r_4bet_facing",
    "val_r_4bet_facing_bp",
    # Bet-sizing completion (raw amounts, generic raise faced, 2nd raise, 5bet) — appended at the end.
    "amt_blind",
    "amt_bet_p",
    "amt_bet_f",
    "amt_bet_t",
    "amt_bet_r",
    "amt_bet_ttl",
    "cnt_p_raise_facing",
    "val_p_raise_facing_bp",
    "cnt_f_raise_facing",
    "val_f_raise_facing_bp",
    "cnt_t_raise_facing",
    "val_t_raise_facing_bp",
    "cnt_r_raise_facing",
    "val_r_raise_facing_bp",
    "cnt_p_raise_made_2",
    "val_p_raise_made_2_bp",
    "cnt_f_raise_made_2",
    "val_f_raise_made_2_bp",
    "cnt_t_raise_made_2",
    "val_t_raise_made_2_bp",
    "cnt_r_raise_made_2",
    "val_r_raise_made_2_bp",
    "cnt_p_5bet_facing",
    "val_p_5bet_facing_bp",
]

# HudCache-ONLY stat columns, kept OUT of the shared CACHE_KEYS so the other
# four caches (Cards/Positions/Sessions/Tourneys), which build their own lines
# from CACHE_KEYS, are completely unaffected. storeHudCache appends these to its
# line after the CACHE_KEYS values; the order here must match the tail of
# insert_hudcache / update_hudcache and the HudCache CREATE columns.
HUDCACHE_EXTRA_KEYS = [
    "street2DelayedCBChance",
    "street2DelayedCBDone",
    "street2ProbeChance",
    "street2ProbeDone",
]


class DatabaseCachesMixin:
    """Writes the aggregate caches the HUD and the reports read from.

    Mixed into Database, which provides the connection, the query catalogue and
    the per-import buffers named below.
    """

    # Provided by Database.
    sql: Any
    import_options: dict[str, Any]
    build_full_hudcache: bool
    day_start: float
    sessionTimeout: float
    hids: list[Any]
    hbulk: list[Any]
    dcbulk: dict[Any, Any]
    hcbulk: dict[Any, Any]
    pcbulk: dict[Any, Any]
    tbulk: dict[Any, Any]
    s: dict[str, Any]
    sc: dict[Any, Any]
    tc: dict[Any, Any]
    ttold: set[Any]
    ttnew: set[Any]
    wmold: set[Any]
    wmnew: set[Any]

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def commit(self, force: bool = False) -> None: ...

        def executemany(self, c: Any, q: Any, values: Any) -> None: ...

        def fetchallDict(self, cursor: Any, desc: Any) -> Any: ...

        def get_last_insert_id(self, cursor: Any = None) -> Any: ...

        def insertOrUpdate(self, type: Any, cursor: Any, key: Any, select: Any, insert: Any) -> Any: ...

    def storeHudCache(self, gid, gametype, pids, starttime, pdata, doinsert=False) -> None:
        """Update cached statistics. If update fails because no record exists, do an insert."""
        if pdata:
            tz = datetime.utcnow() - datetime.today()
            tz_offset = (tz.seconds) // (3600)
            tz_day_start_offset = self.day_start + tz_offset

            d = timedelta(hours=tz_day_start_offset)
            starttime_offset = starttime - d
            styleKey = datetime.strftime(starttime_offset, "d%y%m%d")
            seats = len(pids)

        pos = {
            "B": "B",
            "S": "S",
            0: "D",
            1: "C",
            2: "M",
            3: "M",
            4: "M",
            5: "E",
            6: "E",
            7: "E",
            8: "E",
            9: "E",
        }

        for p in pdata:
            player_stats = pdata.get(p)
            garbageTourneyTypes = (
                player_stats["tourneyTypeId"] in self.ttnew or player_stats["tourneyTypeId"] in self.ttold
            )
            if self.import_options["hhBulkPath"] == "" or not garbageTourneyTypes:
                position = pos[player_stats["position"]]
                k = (
                    gid,
                    pids[p],
                    seats,
                    position,
                    player_stats["tourneyTypeId"],
                    styleKey if self.build_full_hudcache else "A000000",
                )
                player_stats["n"] = 1
                line = [
                    (int(player_stats[s]) if isinstance(player_stats[s], bool) else player_stats[s]) for s in CACHE_KEYS
                ]
                # HudCache-only columns (see HUDCACHE_EXTRA_KEYS): appended after
                # the shared CACHE_KEYS values, matching insert/update_hudcache.
                line += [int(player_stats.get(k, 0)) for k in HUDCACHE_EXTRA_KEYS]

                hud = self.hcbulk.get(k)
                # Add line to the old line in the hudcache.
                if hud is not None:
                    for idx, val in enumerate(line):
                        hud[idx] += val
                else:
                    self.hcbulk[k] = line

        if doinsert:
            update_hudcache = self.sql.query["update_hudcache"]
            update_hudcache = update_hudcache.replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_hudcache = self.sql.query["insert_hudcache"]
            insert_hudcache = insert_hudcache.replace(
                "%s",
                self.sql.query["placeholder"],
            )

            select_hudcache_ring = self.sql.query["select_hudcache_ring"]
            select_hudcache_ring = select_hudcache_ring.replace(
                "%s",
                self.sql.query["placeholder"],
            )
            select_hudcache_tour = self.sql.query["select_hudcache_tour"]
            select_hudcache_tour = select_hudcache_tour.replace(
                "%s",
                self.sql.query["placeholder"],
            )
            inserts = []
            c = self.get_cursor()
            for k, item in list(self.hcbulk.items()):
                if not k[4]:
                    q = select_hudcache_ring
                    row = [*list(k[:4]), k[-1]]
                else:
                    q = select_hudcache_tour
                    row = list(k)

                c.execute(q, row)
                result = c.fetchone()
                if result:
                    id = result[0]
                    update = [*item, id]
                    c.execute(update_hudcache, update)

                else:
                    inserts.append(list(k) + item)

            if inserts:
                self.executemany(c, insert_hudcache, inserts)
            self.commit()
    def storeSessions(self, hid, pids, startTime, tid, heroes, tz_name, doinsert=False) -> None:
        """Update cached sessions. If no record exists, do an insert."""
        THRESHOLD = timedelta(seconds=int(self.sessionTimeout * 60))
        if tz_name in pytz.common_timezones:
            naive = startTime.replace(tzinfo=None)
            utc_start = pytz.utc.localize(naive)
            tz = pytz.timezone(tz_name)
            loc_tz = utc_start.astimezone(tz).strftime("%z")
            offset = timedelta(
                hours=int(loc_tz[:-2]),
                minutes=int(loc_tz[0] + loc_tz[-2:]),
            )
            local = naive + offset
            monthStart = datetime(local.year, local.month, 1)
            weekdate = datetime(local.year, local.month, local.day)
            weekStart = weekdate - timedelta(days=weekdate.weekday())
        else:
            if strftime("%Z") == "UTC":
                local = startTime
                loc_tz = "0"
            else:
                tz_dt = datetime.today() - datetime.utcnow()
                loc_tz = (tz_dt.seconds) // (3600) - 24
                offset = timedelta(hours=int(loc_tz))
                local = startTime + offset
            monthStart = datetime(local.year, local.month, 1)
            weekdate = datetime(local.year, local.month, local.day)
            weekStart = weekdate - timedelta(days=weekdate.weekday())

        j, hand = None, {}
        for _p, id in list(pids.items()):
            if id in heroes:
                hand["startTime"] = startTime.replace(tzinfo=None)
                hand["weekStart"] = weekStart
                hand["monthStart"] = monthStart
                hand["ids"] = [hid]
                hand["tourneys"] = set()

        id = []
        if hand:
            lower = hand["startTime"] - THRESHOLD
            upper = hand["startTime"] + THRESHOLD
            for i in range(len(self.s["bk"])):
                if ((lower <= self.s["bk"][i]["sessionEnd"]) and (upper >= self.s["bk"][i]["sessionStart"])) or (
                    tid in self.s["bk"][i]["tourneys"]
                ):
                    if (hand["startTime"] <= self.s["bk"][i]["sessionEnd"]) and (
                        hand["startTime"] >= self.s["bk"][i]["sessionStart"]
                    ):
                        id.append(i)
                    elif hand["startTime"] < self.s["bk"][i]["sessionStart"]:
                        self.s["bk"][i]["sessionStart"] = hand["startTime"]
                        self.s["bk"][i]["weekStart"] = hand["weekStart"]
                        self.s["bk"][i]["monthStart"] = hand["monthStart"]
                        id.append(i)
                    elif hand["startTime"] > self.s["bk"][i]["sessionEnd"]:
                        self.s["bk"][i]["sessionEnd"] = hand["startTime"]
                        id.append(i)
            if len(id) == 1:
                j = id[0]
                self.s["bk"][j]["ids"] += [hid]
                if tid:
                    self.s["bk"][j]["tourneys"].add(tid)
            elif len(id) > 1:
                merged: dict[str, Any] = {"ids": [hid], "tourneys": set()}
                if tid:
                    merged["tourneys"].add(tid)
                for n in id:
                    h = self.s["bk"][n]
                    if not merged.get("sessionStart") or merged.get("sessionStart") > h["sessionStart"]:
                        merged["sessionStart"] = h["sessionStart"]
                        merged["weekStart"] = h["weekStart"]
                        merged["monthStart"] = h["monthStart"]
                    if not merged.get("sessionEnd") or merged.get("sessionEnd") < h["sessionEnd"]:
                        merged["sessionEnd"] = h["sessionEnd"]
                    merged["ids"] += h["ids"]
                    merged["tourneys"].update(h["tourneys"])
                    self.s["bk"][n]["delete"] = True

                self.s["bk"] = [item for item in self.s["bk"] if not item.get("delete")]
                self.s["bk"].append(merged)
            elif len(id) == 0:
                j = len(self.s["bk"])
                hand["id"] = None
                hand["sessionStart"] = hand["startTime"]
                hand["sessionEnd"] = hand["startTime"]
                if tid:
                    hand["tourneys"].add(tid)
                self.s["bk"].append(hand)

        if doinsert:
            select_S = self.sql.query["select_S"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            select_W = self.sql.query["select_W"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            select_M = self.sql.query["select_M"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            update_S = self.sql.query["update_S"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_W = self.sql.query["insert_W"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_M = self.sql.query["insert_M"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_S = self.sql.query["insert_S"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            update_S_SC = self.sql.query["update_S_SC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            update_S_TC = self.sql.query["update_S_TC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            update_S_T = self.sql.query["update_S_T"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            update_S_H = self.sql.query["update_S_H"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            delete_S = self.sql.query["delete_S"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            c = self.get_cursor()
            for i in range(len(self.s["bk"])):
                lower = self.s["bk"][i]["sessionStart"] - THRESHOLD
                upper = self.s["bk"][i]["sessionEnd"] + THRESHOLD
                tourneys = self.s["bk"][i]["tourneys"]
                if self.s["bk"][i]["tourneys"]:
                    toursql = "OR SC.id in (SELECT DISTINCT sessionId FROM Tourneys T WHERE T.id in ({}))".format(
                        ", ".join(str(t) for t in tourneys)
                    )
                    q = select_S.replace("<TOURSELECT>", toursql)
                else:
                    q = select_S.replace("<TOURSELECT>", "")
                c.execute(q, (lower, upper))
                r = self.fetchallDict(
                    c,
                    [
                        "id",
                        "sessionStart",
                        "sessionEnd",
                        "weekStart",
                        "monthStart",
                        "weekId",
                        "monthId",
                    ],
                )
                num = len(r)
                if num == 1:
                    start, end = r[0]["sessionStart"], r[0]["sessionEnd"]
                    week, month = r[0]["weekStart"], r[0]["monthStart"]
                    wid, mid = r[0]["weekId"], r[0]["monthId"]
                    update, updateW, updateM = False, False, False
                    if self.s["bk"][i]["sessionStart"] < start:
                        start, update = self.s["bk"][i]["sessionStart"], True
                        if self.s["bk"][i]["weekStart"] != week:
                            week, updateW = self.s["bk"][i]["weekStart"], True
                        if self.s["bk"][i]["monthStart"] != month:
                            month, updateM = self.s["bk"][i]["monthStart"], True
                        if updateW or updateM:
                            self.wmold.add((wid, mid))
                    if self.s["bk"][i]["sessionEnd"] > end:
                        end, update = self.s["bk"][i]["sessionEnd"], True
                    if updateW:
                        wid = self.insertOrUpdate(
                            "weeks",
                            c,
                            (week,),
                            select_W,
                            insert_W,
                        )
                    if updateM:
                        mid = self.insertOrUpdate(
                            "months",
                            c,
                            (month,),
                            select_M,
                            insert_M,
                        )
                    if updateW or updateM:
                        self.wmnew.add((wid, mid))
                    if update:
                        c.execute(update_S, [wid, mid, start, end, r[0]["id"]])
                    for h in self.s["bk"][i]["ids"]:
                        self.s[h] = {"id": r[0]["id"], "wid": wid, "mid": mid}
                elif num > 1:
                    start, end, wmold, merge = None, None, set(), []
                    for n in r:
                        merge.append(n["id"])
                    merge.sort()
                    r.append(self.s["bk"][i])
                    for n in r:
                        if "weekId" in n:
                            wmold.add((n["weekId"], n["monthId"]))
                        if start:
                            if start > n["sessionStart"]:
                                start = n["sessionStart"]
                                week = n["weekStart"]
                                month = n["monthStart"]
                        else:
                            start = n["sessionStart"]
                            week = n["weekStart"]
                            month = n["monthStart"]
                        end = max(end, n["sessionEnd"]) if end else n["sessionEnd"]
                    wid = self.insertOrUpdate("weeks", c, (week,), select_W, insert_W)
                    mid = self.insertOrUpdate("months", c, (month,), select_M, insert_M)
                    wmold.discard((wid, mid))
                    if len(wmold) > 0:
                        self.wmold = self.wmold.union(wmold)
                        self.wmnew.add((wid, mid))
                    row = [wid, mid, start, end]
                    c.execute(insert_S, row)
                    sid = self.get_last_insert_id(c)
                    for h in self.s["bk"][i]["ids"]:
                        self.s[h] = {"id": sid, "wid": wid, "mid": mid}
                    for m in merge:
                        for h, n in list(self.s.items()):
                            if h != "bk" and n["id"] == m:
                                self.s[h] = {"id": sid, "wid": wid, "mid": mid}
                        c.execute(update_S_TC, (sid, m))
                        c.execute(update_S_SC, (sid, m))
                        c.execute(update_S_T, (sid, m))
                        c.execute(update_S_H, (sid, m))
                        c.execute(delete_S, (m,))
                elif num == 0:
                    start = self.s["bk"][i]["sessionStart"]
                    end = self.s["bk"][i]["sessionEnd"]
                    week = self.s["bk"][i]["weekStart"]
                    month = self.s["bk"][i]["monthStart"]
                    wid = self.insertOrUpdate("weeks", c, (week,), select_W, insert_W)
                    mid = self.insertOrUpdate("months", c, (month,), select_M, insert_M)
                    row = [wid, mid, start, end]
                    c.execute(insert_S, row)
                    sid = self.get_last_insert_id(c)
                    for h in self.s["bk"][i]["ids"]:
                        self.s[h] = {"id": sid, "wid": wid, "mid": mid}
            self.commit()
    def storeSessionsCache(
        self,
        hid,
        pids,
        startTime,
        gametypeId,
        gametype,
        pdata,
        heroes,
        doinsert=False,
    ) -> None:
        """Update cached cash sessions. If no record exists, do an insert."""
        THRESHOLD = timedelta(seconds=int(self.sessionTimeout * 60))
        if pdata:  # gametype['type']=='ring' and
            for p, pid in list(pids.items()):
                hp: dict[str, Any] = {}
                k = (gametypeId, pid)
                hp["startTime"] = startTime.replace(tzinfo=None)
                hp["hid"] = hid
                hp["ids"] = []
                pdata[p]["n"] = 1
                hp["line"] = [int(pdata[p][s]) if isinstance(pdata[p][s], bool) else pdata[p][s] for s in CACHE_KEYS]
                session_indices: list[int] = []
                sessionplayer: list[dict[str, Any]] | None = self.sc.get(k)
                if sessionplayer is not None:
                    lower = hp["startTime"] - THRESHOLD
                    upper = hp["startTime"] + THRESHOLD
                    for i in range(len(sessionplayer)):
                        if lower <= sessionplayer[i]["endTime"] and upper >= sessionplayer[i]["startTime"]:
                            if len(session_indices) == 0:
                                for idx, val in enumerate(hp["line"]):
                                    sessionplayer[i]["line"][idx] += val
                            if (hp["startTime"] <= sessionplayer[i]["endTime"]) and (
                                hp["startTime"] >= sessionplayer[i]["startTime"]
                            ):
                                session_indices.append(i)
                            elif hp["startTime"] < sessionplayer[i]["startTime"]:
                                sessionplayer[i]["startTime"] = hp["startTime"]
                                session_indices.append(i)
                            elif hp["startTime"] > sessionplayer[i]["endTime"]:
                                sessionplayer[i]["endTime"] = hp["startTime"]
                                session_indices.append(i)
                if len(session_indices) == 1:
                    i = session_indices[0]
                    if pids[p] == heroes[0]:
                        self.sc[k][i]["ids"].append(hid)
                elif len(session_indices) == 2:
                    i, j = session_indices[0], session_indices[1]
                    if sessionplayer is None:
                        continue
                    if sessionplayer[i]["startTime"] < sessionplayer[j]["startTime"]:
                        sessionplayer[i]["endTime"] = sessionplayer[j]["endTime"]
                    else:
                        sessionplayer[i]["startTime"] = sessionplayer[j]["startTime"]
                    for idx, val in enumerate(sessionplayer[j]["line"]):
                        sessionplayer[i]["line"][idx] += val
                    g = sessionplayer.pop(j)
                    if pids[p] == heroes[0]:
                        self.sc[k][i]["ids"].append(hid)
                        self.sc[k][i]["ids"] += g["ids"]
                elif len(session_indices) == 0:
                    if sessionplayer is None:
                        self.sc[k] = []
                    hp["endTime"] = hp["startTime"]
                    if pids[p] == heroes[0]:
                        hp["ids"].append(hid)
                    self.sc[k].append(hp)

        if doinsert:
            select_SC = self.sql.query["select_SC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            update_SC = self.sql.query["update_SC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_SC = self.sql.query["insert_SC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            delete_SC = self.sql.query["delete_SC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            c = self.get_cursor()
            for k, sessionplayer in list(self.sc.items()):
                for session in sessionplayer:
                    hid = session["hid"]
                    session_record = self.s.get(hid)
                    if session_record is None:
                        log.warning("Ignoring session cache entry without its session record: hand %s", hid)
                        continue
                    sid = session_record["id"]
                    lower = session["startTime"] - THRESHOLD
                    upper = session["endTime"] + THRESHOLD
                    row = [lower, upper, *list(k[:2])]
                    c.execute(select_SC, row)
                    r = self.fetchallDict(
                        c,
                        ["id", "sessionId", "startTime", "endTime", *CACHE_KEYS],
                    )
                    num = len(r)
                    d: list[dict[str, Any]] = [{} for _ in range(num)]
                    for z in range(num):
                        d[z] = {}
                        d[z]["line"] = [int(r[z][s]) if isinstance(r[z][s], bool) else r[z][s] for s in CACHE_KEYS]
                        d[z]["id"] = r[z]["id"]
                        d[z]["sessionId"] = r[z]["sessionId"]
                        d[z]["startTime"] = r[z]["startTime"]
                        d[z]["endTime"] = r[z]["endTime"]
                    if num == 1:
                        start, end, id = r[0]["startTime"], r[0]["endTime"], r[0]["id"]
                        start = min(session["startTime"], start)
                        end = max(session["endTime"], end)
                        row = [start, end] + session["line"] + [id]
                        c.execute(update_SC, row)
                    elif num > 1:
                        start, end, merge, line = None, None, [], [0] * len(CACHE_KEYS)
                        for n in r:
                            merge.append(n["id"])
                        merge.sort()
                        merged_rows = d + [session]
                        for n in merged_rows:
                            start = min(start, n["startTime"]) if start else n["startTime"]
                            end = max(end, n["endTime"]) if end else n["endTime"]
                            for idx in range(len(CACHE_KEYS)):
                                line[idx] += int(n["line"][idx]) if isinstance(n["line"][idx], bool) else n["line"][idx]
                        row = [sid, start, end, *list(k[:2]), *line]
                        c.execute(insert_SC, row)
                        id = self.get_last_insert_id(c)
                        for m in merge:
                            c.execute(delete_SC, (m,))
                            self.commit()
                    elif num == 0:
                        start = session["startTime"]
                        end = session["endTime"]
                        row = [sid, start, end] + list(k[:2]) + session["line"]
                        c.execute(insert_SC, row)
                        id = self.get_last_insert_id(c)
            self.commit()
    def storeTourneysCache(
        self,
        hid,
        pids,
        startTime,
        tid,
        gametype,
        pdata,
        heroes,
        doinsert=False,
    ) -> None:
        """Update cached tour sessions. If no record exists, do an insert."""
        if gametype["type"] == "tour" and pdata:
            for p in pdata:
                k = (tid, pids[p])
                pdata[p]["n"] = 1
                line = [int(pdata[p][s]) if isinstance(pdata[p][s], bool) else pdata[p][s] for s in CACHE_KEYS]
                tourplayer = self.tc.get(k)
                # Add line to the old line in the tourcache.
                if tourplayer is not None:
                    for idx, val in enumerate(line):
                        tourplayer["line"][idx] += val
                    if pids[p] == heroes[0]:
                        tourplayer["ids"].append(hid)
                else:
                    self.tc[k] = {
                        "startTime": None,
                        "endTime": None,
                        "hid": hid,
                        "ids": [],
                    }
                    self.tc[k]["line"] = line
                    if pids[p] == heroes[0]:
                        self.tc[k]["ids"].append(hid)

                if not self.tc[k]["startTime"] or startTime < self.tc[k]["startTime"]:
                    self.tc[k]["startTime"] = startTime
                    self.tc[k]["hid"] = hid
                if not self.tc[k]["endTime"] or startTime > self.tc[k]["endTime"]:
                    self.tc[k]["endTime"] = startTime

        if doinsert:
            update_TC = self.sql.query["update_TC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_TC = self.sql.query["insert_TC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            select_TC = self.sql.query["select_TC"].replace(
                "%s",
                self.sql.query["placeholder"],
            )

            inserts = []
            c = self.get_cursor()
            for k, tc in list(self.tc.items()):
                sc = self.s.get(tc["hid"])
                if sc is None:
                    log.warning("Ignoring tournament cache entry without its session record: hand %s", tc["hid"])
                    continue
                tc["startTime"] = tc["startTime"].replace(tzinfo=None)
                tc["endTime"] = tc["endTime"].replace(tzinfo=None)
                c.execute(select_TC, k)
                r = self.fetchallDict(c, ["id", "startTime", "endTime"])
                num = len(r)
                if num == 1:
                    update = not r[0]["startTime"] or not r[0]["endTime"]
                    if update or (tc["startTime"] < r[0]["startTime"] and tc["endTime"] > r[0]["endTime"]):
                        q = update_TC.replace("<UPDATE>", "startTime=%s, endTime=%s,")
                        row = [tc["startTime"], tc["endTime"]] + tc["line"] + list(k[:2])
                    elif tc["startTime"] < r[0]["startTime"]:
                        q = update_TC.replace("<UPDATE>", "startTime=%s, ")
                        row = [tc["startTime"]] + tc["line"] + list(k[:2])
                    elif tc["endTime"] > r[0]["endTime"]:
                        q = update_TC.replace("<UPDATE>", "endTime=%s, ")
                        row = [tc["endTime"]] + tc["line"] + list(k[:2])
                    else:
                        q = update_TC.replace("<UPDATE>", "")
                        row = tc["line"] + list(k[:2])
                    c.execute(q, row)
                elif num == 0:
                    row = [sc["id"], tc["startTime"], tc["endTime"]] + list(k[:2]) + tc["line"]
                    # append to the bulk inserts
                    inserts.append(row)

            if inserts:
                self.executemany(c, insert_TC, inserts)
            self.commit()
    def storeCardsCache(
        self,
        hid,
        pids,
        startTime,
        gametypeId,
        tourneyTypeId,
        pdata,
        heroes,
        tz_name,
        doinsert,
    ) -> None:
        """Update cached cards statistics. If update fails because no record exists, do an insert."""
        for p in pdata:
            k = (hid, gametypeId, tourneyTypeId, pids[p], pdata[p]["startCards"])
            pdata[p]["n"] = 1
            line = [int(pdata[p][s]) if isinstance(pdata[p][s], bool) else pdata[p][s] for s in CACHE_KEYS]
            self.dcbulk[k] = line

        if doinsert:
            update_cardscache = self.sql.query["update_cardscache"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_cardscache = self.sql.query["insert_cardscache"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            select_cardscache_ring = self.sql.query["select_cardscache_ring"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            select_cardscache_tour = self.sql.query["select_cardscache_tour"].replace(
                "%s",
                self.sql.query["placeholder"],
            )

            # Removed unused variables
            # select_W = self.sql.query["select_W"].replace("%s", self.sql.query["placeholder"])
            # select_M = self.sql.query["select_M"].replace("%s", self.sql.query["placeholder"])
            # insert_W = self.sql.query["insert_W"].replace("%s", self.sql.query["placeholder"])
            # insert_M = self.sql.query["insert_M"].replace("%s", self.sql.query["placeholder"])

            dccache: dict[tuple[Any, ...], list[Any]] = {}
            inserts: list[Any] = []
            for cache_key, line in list(self.dcbulk.items()):
                sc = self.s.get(cache_key[0])
                if sc is not None:
                    garbageWeekMonths = (sc["wid"], sc["mid"]) in self.wmnew or (
                        sc["wid"],
                        sc["mid"],
                    ) in self.wmold
                    garbageTourneyTypes = cache_key[2] in self.ttnew or cache_key[2] in self.ttold
                    if self.import_options["hhBulkPath"] == "" or (not garbageWeekMonths and not garbageTourneyTypes):
                        group_key = (sc["wid"], sc["mid"], cache_key[1], cache_key[2], cache_key[3], cache_key[4])
                        startCards = dccache.get(group_key)
                        # Add line to the old line in the hudcache.
                        if startCards is not None:
                            for idx, val in enumerate(line):
                                dccache[group_key][idx] += val
                        else:
                            dccache[group_key] = line

            c = self.get_cursor()
            for cache_key, item in list(dccache.items()):
                if cache_key[3]:
                    q = select_cardscache_tour
                    row = list(cache_key)
                else:
                    q = select_cardscache_ring
                    row = list(cache_key[:3]) + list(cache_key[-2:])
                c.execute(q, row)
                result = c.fetchone()
                if result:
                    id = result[0]
                    update = [*item, id]
                    c.execute(update_cardscache, update)
                else:
                    insert = list(cache_key) + item
                    inserts.append(insert)

            if inserts:
                self.executemany(c, insert_cardscache, inserts)
                self.commit()
    def storePositionsCache(
        self,
        hid,
        pids,
        startTime,
        gametypeId,
        tourneyTypeId,
        pdata,
        hdata,
        heroes,
        tz_name,
        doinsert,
    ) -> None:
        """Update cached position statistics. If update fails because no record exists, do an insert."""
        for p in pdata:
            position = str(pdata[p]["position"])
            k = (
                hid,
                gametypeId,
                tourneyTypeId,
                pids[p],
                len(pids),
                hdata["maxPosition"],
                position,
            )
            pdata[p]["n"] = 1
            line = [int(pdata[p][s]) if isinstance(pdata[p][s], bool) else pdata[p][s] for s in CACHE_KEYS]
            self.pcbulk[k] = line

        if doinsert:
            update_positionscache = self.sql.query["update_positionscache"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            insert_positionscache = self.sql.query["insert_positionscache"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            select_positionscache_ring = self.sql.query["select_positionscache_ring"].replace(
                "%s", self.sql.query["placeholder"]
            )
            select_positionscache_tour = self.sql.query["select_positionscache_tour"].replace(
                "%s", self.sql.query["placeholder"]
            )

            # Removed unused variables:
            # select_W = self.sql.query["select_W"].replace("%s", self.sql.query["placeholder"])
            # select_M = self.sql.query["select_M"].replace("%s", self.sql.query["placeholder"])
            # insert_W = self.sql.query["insert_W"].replace("%s", self.sql.query["placeholder"])
            # insert_M = self.sql.query["insert_M"].replace("%s", self.sql.query["placeholder"])

            position_cache: dict[tuple[Any, ...], list[Any]] = {}
            inserts: list[Any] = []
            for cache_key, line in list(self.pcbulk.items()):
                sc = self.s.get(cache_key[0])
                if sc is not None:
                    garbageWeekMonths = (sc["wid"], sc["mid"]) in self.wmnew or (
                        sc["wid"],
                        sc["mid"],
                    ) in self.wmold
                    garbageTourneyTypes = cache_key[2] in self.ttnew or cache_key[2] in self.ttold
                    if self.import_options["hhBulkPath"] == "" or (not garbageWeekMonths and not garbageTourneyTypes):
                        group_key = (
                            sc["wid"], sc["mid"], cache_key[1], cache_key[2], cache_key[3],
                            cache_key[4], cache_key[5], cache_key[6],
                        )
                        positions = position_cache.get(group_key)
                        # Add line to the old line in the hudcache.
                        if positions is not None:
                            for idx, val in enumerate(line):
                                position_cache[group_key][idx] += val
                        else:
                            position_cache[group_key] = line

            c = self.get_cursor()
            for cache_key, item in list(position_cache.items()):
                if cache_key[3]:  # Check if it's a tournament
                    q = select_positionscache_tour
                    row = list(cache_key)
                else:  # It's a ring game
                    q = select_positionscache_ring
                    row = list(cache_key[:3]) + list(cache_key[-4:])

                c.execute(q, row)
                result = c.fetchone()
                if result:
                    id = result[0]
                    update = [*item, id]
                    c.execute(update_positionscache, update)
                else:
                    insert = list(cache_key) + item
                    inserts.append(insert)

            if inserts:
                self.executemany(c, insert_positionscache, inserts)
                self.commit()
    def appendHandsSessionIds(self) -> None:
        for i in range(len(self.hbulk)):
            hid = self.hids[i]
            tid = self.hbulk[i][2]
            sc = self.s.get(hid)
            if sc is not None:
                self.hbulk[i][4] = sc["id"]
                if tid:
                    self.tbulk[tid] = sc["id"]
