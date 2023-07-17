import sqlite3
from base_model import *
import Configuration
import pathlib

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
        p.id, p.name AS player_name , s.name AS site, p.hero,
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

def get_hands_players(player_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM HandsPlayers
    WHERE playerId = (
        SELECT id FROM Players WHERE id = ?
    );
    """, (player_id,))  # Pass player_id as a parameter to the execute function

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