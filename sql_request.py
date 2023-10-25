import sqlite3
from base_model import *
import Configuration
import pathlib
import math
import itertools

DATABASE = pathlib.Path(Configuration.CONFIG_PATH, "database", "fpdb.db3")

def get_backings():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Backings")
    backings = cursor.fetchall()
    conn.close()
    return backings

def get_actions():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Actions")
    actions = cursor.fetchall()
    conn.close()
    return actions

def get_autorates():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Autorates")
    autorates = cursor.fetchall()
    conn.close()
    return autorates

def get_boards():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Boards")
    boards = cursor.fetchall()
    conn.close()
    return boards

def get_cardsCaches():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM CardsCaches")
    cardsCaches = cursor.fetchall()
    conn.close()
    return cardsCaches

def get_files():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Files")
    files = cursor.fetchall()
    conn.close()
    return files

def get_gametypes():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Gametypes")
    gametypes = cursor.fetchall()
    conn.close()
    return gametypes

def get_hands():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Hands")
    hands = cursor.fetchall()
    conn.close()
    return hands

def get_handsActions():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM HandsActions")
    handsActions = cursor.fetchall()
    conn.close()
    return handsActions

def get_handsPlayers():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM HandsPlayers")
    handsPlayer = cursor.fetchall()
    conn.close()
    return handsPlayer

def get_handsPots():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM HandsPots")
    handsPots = cursor.fetchall()
    conn.close()
    return handsPots

def get_handsStove():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM HandsStove")
    handsStoves = cursor.fetchall()
    conn.close()
    return handsStoves

def get_RingProfitAllHandsPlayerIdSite(
    site=None,
    player=None,
    limit=None,
    bigBlind=None,
    currency=None,
    category=None,
    startdate=None,
    enddate=None
):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # SQL query string
    sql = """
        SELECT hp.handId, hp.totalProfit, hp.sawShowdown, hp.allInEV
        FROM HandsPlayers hp
        INNER JOIN Players pl ON (pl.id = hp.playerId)
        INNER JOIN Hands h ON (h.id = hp.handId)
        INNER JOIN Gametypes gt ON (gt.id = h.gametypeId)
        WHERE pl.id IN (:player)
        AND (:site IS NULL OR pl.siteId = :site)
        AND (h.startTime > :startdate OR :startdate IS NULL)
        AND (h.startTime < :enddate OR :enddate IS NULL)
        AND (gt.limitType = :limit OR :limit IS NULL) 
        AND (gt.bigBlind IN (:bigBlind) OR :bigBlind IS NULL)
        AND (gt.category IN (:category) OR :category IS NULL)
        AND (gt.currency = :currency OR :currency IS NULL)
        AND hp.tourneysPlayersId IS NULL
        GROUP BY h.startTime, hp.handId, hp.sawShowdown, hp.totalProfit, hp.allInEV
        ORDER BY h.startTime
    """

    # Parameters dict
    params = {
        'player': player,
        'site': site,
        'limit': limit,
        'bigBlind': bigBlind,
        'category': category,
        'currency': currency,
        'startdate': startdate,
        'enddate': enddate
    }

    # Execute query
    cursor.execute(sql, params)

    return cursor.fetchall()

def get_tourneysProfitPlayerIdSite(
    site=None,
    player=None,
    limit=None,
    buyin=None,
    currency=None,
    category=None,
    startdate=None,
    enddate=None
):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # SQL query string
    sql = """
            SELECT tp.tourneyId, (coalesce(tp.winnings,0) - coalesce(tt.buyIn,0) - coalesce(tt.fee,0)) as profit, tp.koCount, tp.rebuyCount, tp.addOnCount, tt.buyIn, tt.fee, t.siteTourneyNo
            FROM TourneysPlayers tp
            INNER JOIN Players pl      ON  (pl.id = tp.playerId)
            INNER JOIN Tourneys t         ON  (t.id  = tp.tourneyId)
            INNER JOIN TourneyTypes tt    ON  (tt.id = t.tourneyTypeId)
            WHERE pl.id in (:player)
            AND (:site IS NULL OR pl.siteId = :site)
            AND (tt.category in (:category) OR :category IS NULL)
            AND (tt.limitType = :limit OR :limit IS NULL)
            AND (tt.buyin in (:buyin) OR :buyin IS NULL)
            AND (t.startTime > :startdate OR :startdate IS NULL)
            AND (t.startTime < :enddate OR :enddate IS NULL)
            AND (tt.currency = :currency OR :currency IS NULL)
            GROUP BY t.startTime, tp.tourneyId, tp.winningsCurrency,
                     tp.winnings, tp.koCount,
                     tp.rebuyCount, tp.addOnCount,
                     tt.buyIn, tt.fee, t.siteTourneyNo
            ORDER BY t.startTime
    """

    # Parameters dict
    params = {
        'player': player,
        'site': site,
        'limit': limit,
        'buyin': buyin,
        'category': category,
        'currency': currency,
        'startdate': startdate,
        'enddate': enddate
    }

    # Execute query
    cursor.execute(sql, params)

    return cursor.fetchall()


def get_players(
  name=None,
  site=None,
  page=1,
  per_page=10
):

  conn = sqlite3.connect(DATABASE)
  cursor = conn.cursor()

  # Get total count
  cursor.execute("SELECT COUNT(*) AS total FROM Players p")
  total = cursor.fetchone()[0]

  # Calculate offset
  offset = (page - 1) * per_page
  
  # SQL query string
  sql = """
        SELECT 
        p.id, p.name AS player_name , s.name AS site, p.hero, p.siteId,
        COUNT(hp.id) AS total_hands,
        SUM(CASE WHEN hp.tourneysPlayersId IS NULL THEN 1 ELSE 0 END) AS cash_hands, 
        SUM(CASE WHEN hp.tourneysPlayersId IS NOT NULL THEN 1 ELSE 0 END) AS tournament_hands
        FROM Players p
        LEFT JOIN Sites s ON p.siteId = s.id 
        LEFT JOIN HandsPlayers hp ON hp.playerId = p.id
        WHERE
        (:name IS NULL OR p.name LIKE :name) 
        AND
        (:site IS NULL OR s.name = :site)
        GROUP BY 
        p.id, p.name, s.name, p.hero 
        LIMIT
        :per_page
        OFFSET 
        :offset
  """

  # Parameters dict
  params = {
    'name': name,
    'site': site,
    'per_page': per_page,
    'offset': offset
  }
  
  # Convert dict to string
  params_str = str(params)

  # Join query string  
  query = " ".join([sql, params_str])

  # Print formatted query
  #print(query)

  # Execute query
  cursor.execute(sql, params)

  players = cursor.fetchall()

  return players, total

def get_heroes():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
                        SELECT p.name AS hero_name, s.name AS site_name, p.id, p.siteId
                        FROM Players p
                        JOIN Sites s ON p.siteId = s.id
                        WHERE p.hero = 1;
                      
                   """)
    heroes = cursor.fetchall()
    conn.close()
    return heroes



def get_hands_players(player_id, tourney=False, cash=False, sort_by=None):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    query = """
    SELECT
        HP.*,
        HPots.*,
        HStove.*,
        H.*,
        GT.*
    FROM HandsPlayers AS HP
    LEFT JOIN Hands AS H ON HP.handId = H.id
    LEFT JOIN HandsPots AS HPots ON HP.handId = HPots.handId
    LEFT JOIN HandsStove AS HStove ON HP.handId = HStove.handId
    LEFT JOIN Gametypes AS GT ON H.gametypeId = GT.id
    WHERE HP.playerId = ?
    """

    if tourney:
        query += " AND H.tourneyId IS NOT NULL"
    elif cash:
        query += " AND H.tourneyId IS NULL"

    if sort_by:
        query += f" ORDER BY {sort_by}"

    cursor.execute(query, (player_id,))
    
    hands_players = cursor.fetchall()

    conn.close()
    return hands_players

def get_handscount():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS handCount FROM Hands")
    handscount = cursor.fetchall()
    conn.close()
    return handscount

def get_handscount_cg():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) AS handCount
                        FROM Hands
                        WHERE tourneyId IS NULL""")
    handscount_cg = cursor.fetchall()
    conn.close()
    return handscount_cg

def get_handscount_tour():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) AS handCount
                        FROM Hands
                        WHERE tourneyId IS NOT NULL""")
    handscount_tour = cursor.fetchall()
    conn.close()
    return handscount_tour

def get_playerscount():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(DISTINCT playerId) AS distinctPlayerCount FROM HandsPlayers;
    """)
    playerscount = cursor.fetchall()
    conn.close()
    return playerscount

def get_playerscount_cg():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(DISTINCT playerId) AS distinctPlayerCount FROM HandsPlayers
                    WHERE tourneysPlayersId IS NULL 
                    """)
    playerscount_cg = cursor.fetchall()
    conn.close()
    return playerscount_cg

def get_playerscount_tour():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(DISTINCT playerId) AS distinctPlayerCount FROM HandsPlayers
                    WHERE tourneysPlayersId IS NOT NULL
                    """)
    playerscount_tour = cursor.fetchall()
    conn.close()
    return playerscount_tour

def get_statsplayers(
    site=None,
    player=None,
    limit=None,
    bigBlind=None,
    currency=None,
    category=None,
    startdate=None,
    enddate=None
):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    query = """
    SELECT h.gametypeId AS hgametypeid, p.name AS pname, gt.base, gt.category AS category, upper(gt.limitType) AS limittype, s.name AS name, min(gt.bigBlind) AS minbigblind, max(gt.bigBlind) AS maxbigblind, gt.ante AS ante, gt.currency AS currency,
    gt.base AS plposition, gt.fast AS fast, count(1) AS n,
    case when sum(cast(hp.street0VPIChance as integer)) = 0 then -999 else 100.0*sum(cast(hp.street0VPI as integer))/sum(cast(hp.street0VPIChance as integer)) end AS vpip,
    case when sum(cast(hp.street0AggrChance as integer)) = 0 then -999 else 100.0*sum(cast(hp.street0Aggr as integer))/sum(cast(hp.street0AggrChance as integer)) end AS pfr,
    case when sum(cast(hp.street0CalledRaiseChance as integer)) = 0 then -999 else 100.0*sum(cast(hp.street0CalledRaiseDone as integer))/sum(cast(hp.street0CalledRaiseChance as integer)) end AS car0,
    case when sum(cast(hp.street0_3Bchance as integer)) = 0 then -999 else 100.0*sum(cast(hp.street0_3Bdone as integer))/sum(cast(hp.street0_3Bchance as integer)) end AS pf3,
    case when sum(cast(hp.street0_4Bchance as integer)) = 0 then -999 else 100.0*sum(cast(hp.street0_4Bdone as integer))/sum(cast(hp.street0_4Bchance as integer)) end AS pf4,
    case when sum(cast(hp.street0_FoldTo3Bchance as integer)) = 0 then -999 else 100.0*sum(cast(hp.street0_FoldTo3Bdone as integer))/sum(cast(hp.street0_FoldTo3Bchance as integer)) end AS pff3,
    case when sum(cast(hp.street0_FoldTo4Bchance as integer)) = 0 then -999 else 100.0*sum(cast(hp.street0_FoldTo4Bdone as integer))/sum(cast(hp.street0_FoldTo4Bchance as integer)) end AS pff4,
    case when sum(cast(hp.raiseFirstInChance as integer)) = 0 then -999 else 100.0*sum(cast(hp.raisedFirstIn as integer))/sum(cast(hp.raiseFirstInChance as integer)) end AS rfi,
    case when sum(cast(hp.stealChance as integer)) = 0 then -999 else 100.0*sum(cast(hp.stealDone as integer))/sum(cast(hp.stealChance as integer)) end AS steals,
    case when sum(cast(hp.stealDone as integer)) = 0 then -999 else 100.0*sum(cast(hp.success_Steal as integer))/sum(cast(hp.stealDone as integer)) end AS suc_steal,
    100.0*sum(cast(hp.street1Seen as integer))/count(1) AS saw_f,
    100.0*sum(cast(hp.sawShowdown as integer))/count(1) AS sawsd,
    case when sum(cast(hp.street1Seen as integer)) = 0 then -999 else 100.0*sum(cast(hp.wonWhenSeenStreet1 as integer))/sum(cast(hp.street1Seen as integer)) end AS wmsf,
    case when sum(cast(hp.street1Seen as integer)) = 0 then -999 else 100.0*sum(cast(hp.sawShowdown as integer))/sum(cast(hp.street1Seen as integer)) end AS wtsdwsf,
    case when sum(cast(hp.sawShowdown as integer)) = 0 then -999 else 100.0*sum(cast(hp.wonAtSD as integer))/sum(cast(hp.sawShowdown as integer)) end AS wmsd,
    case when sum(cast(hp.street1Seen as integer)) = 0 then -999 else 100.0*sum(cast(hp.street1Aggr as integer))/sum(cast(hp.street1Seen as integer)) end AS flafq,
    case when sum(cast(hp.street2Seen as integer)) = 0 then -999 else 100.0*sum(cast(hp.street2Aggr as integer))/sum(cast(hp.street2Seen as integer)) end AS tuafq,
    case when sum(cast(hp.street3Seen as integer)) = 0 then -999 else 100.0*sum(cast(hp.street3Aggr as integer))/sum(cast(hp.street3Seen as integer)) end AS rvafq,
    case when sum(cast(hp.street1Seen as integer))+sum(cast(hp.street2Seen as integer))+sum(cast(hp.street3Seen as integer)) = 0 then -999 else 100.0*(sum(cast(hp.street1Aggr as integer))+sum(cast(hp.street2Aggr as integer))+sum(cast(hp.street3Aggr as integer))) / (sum(cast(hp.street1Seen as integer))+sum(cast(hp.street2Seen as integer))+sum(cast(hp.street3Seen as integer))) end AS pofafq,
    case when sum(cast(hp.street1Calls as integer))+sum(cast(hp.street2Calls as integer))+sum(cast(hp.street3Calls as integer))+sum(cast(hp.street4Calls as integer)) = 0 then -999 else (sum(cast(hp.street1Aggr as integer)) + sum(cast(hp.street2Aggr as integer)) + sum(cast(hp.street3Aggr as integer)) + sum(cast(hp.street4Aggr as integer))) /(0.0+sum(cast(hp.street1Calls as integer))+sum(cast(hp.street2Calls as integer))+sum(cast(hp.street3Calls as integer))+sum(cast(hp.street4Calls as integer))) end AS aggfac,
    100.0*(sum(cast(hp.street1Aggr as integer)) + sum(cast(hp.street2Aggr as integer)) + sum(cast(hp.street3Aggr as integer)) + sum(cast(hp.street4Aggr as integer))) / ((sum(cast(hp.foldToOtherRaisedStreet1 as integer))+sum(cast(hp.foldToOtherRaisedStreet2 as integer))+sum(cast(hp.foldToOtherRaisedStreet3 as integer))+sum(cast(hp.foldToOtherRaisedStreet4 as integer))) + (sum(cast(hp.street1Calls as integer))+sum(cast(hp.street2Calls as integer))+sum(cast(hp.street3Calls as integer))+sum(cast(hp.street4Calls as integer))) + (sum(cast(hp.street1Aggr as integer)) + sum(cast(hp.street2Aggr as integer)) + sum(cast(hp.street3Aggr as integer)) + sum(cast(hp.street4Aggr as integer)))) AS aggfrq,
    100.0*(sum(cast(hp.street1CBDone as integer)) + sum(cast(hp.street2CBDone as integer)) + sum(cast(hp.street3CBDone as integer)) + sum(cast(hp.street4CBDone as integer))) / (sum(cast(hp.street1CBChance as integer))+sum(cast(hp.street2CBChance as integer))+sum(cast(hp.street3CBChance as integer))+sum(cast(hp.street4CBChance as integer))) AS conbet,
    sum(hp.totalProfit)/100.0 AS net,
    sum(hp.rake)/100.0 AS rake,
    100.0*avg(hp.totalProfit/(gt.bigBlind+0.0)) AS bbper100,
    avg(hp.totalProfit)/100.0 AS profitperhand,
    100.0*avg((hp.totalProfit+hp.rake)/(gt.bigBlind+0.0)) AS bb100xr,
    avg((hp.totalProfit+hp.rake)/100.0) AS profhndxr,
    avg(h.seats+0.0) AS avgseats
    FROM HandsPlayers hp
    INNER JOIN Hands h ON (h.id = hp.handId)
    INNER JOIN Gametypes gt ON (gt.Id = h.gametypeId)
    INNER JOIN Sites s ON (s.Id = gt.siteId)
    INNER JOIN Players p ON (p.Id = hp.playerId)
    WHERE hp.playerId IN (:player)
    AND (gt.category IN (:category) OR :category IS NULL)
    AND gt.siteId IN (:site)
    AND (gt.currency = :currency OR :currency IS NULL)
    AND h.seats BETWEEN 2 AND 10
    AND (gt.bigBlind IN (:bigBlind) OR :bigBlind IS NULL)
    AND (gt.limitType = :limit OR :limit IS NULL)
    AND (
    (h.startTime >= :startdate OR :startdate IS NULL)
    AND
    (h.startTime <= :enddate OR :enddate IS NULL)
    )
    GROUP BY hgametypeId, hp.playerId, gt.base, gt.category, plposition, upper(gt.limitType), gt.fast, s.name
    HAVING 1 = 1
    ORDER BY hp.playerId, gt.base, gt.category,
         CASE gt.base
            WHEN 'B' THEN 'B'
            WHEN 'S' THEN 'S'
            WHEN '0' THEN 'Y'
            ELSE 'Z' || gt.base
         END,
         CASE
            WHEN CAST((hp.startcards - 1) / 13 AS INTEGER) >= (hp.startcards - 1) % 13 THEN hp.startcards + 0.1
            ELSE 13 * ((hp.startcards - 1) % 13) + CAST((hp.startcards - 1) / 13 AS INTEGER) + 1
         END DESC,
         upper(gt.limitType) DESC,
         max(gt.bigBlind) DESC,
         gt.fast,
         s.name"""

    # Parameters dict
    params = {
        'player': player,
        'site': site,
        'limit': limit,
        'bigBlind': bigBlind,
        'category': category,
        'currency': currency,
        'startdate': startdate,
        'enddate': enddate
    }

    cursor.execute(query, params)
    result = cursor.fetchall()

    conn.close()

    return result

def get_player_name(player_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM Players WHERE id = ?", (player_id,))
    player_name = cursor.fetchone()
    conn.close()
    return player_name[0] if player_name else None


