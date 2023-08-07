from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sql_request import *
from base_model import *
from typing import List, Optional
import math

app = FastAPI()



@app.get("/hands", response_model=List[Hand])
async def get_hands_api():
    hands = get_hands()
    return JSONResponse(content=hands)



@app.get("/handsPlayers", response_model=List[HandsPlayer])
async def get_handsPlayers_api():
    handsPlayers = get_handsPlayers()
    return JSONResponse(content=handsPlayers)


@app.get("/heroes", response_model=List[Player])
async def get_heroes_api():
    heroes = get_heroes()
    return JSONResponse(content=heroes)


@app.get("/RingProfitAllHandsPlayerIdSite")
async def get_ring_profit_all_hands_api(
    site: int = None,
    player: int = None,
    limit: str = None,
    bigBlind: int = None,
    category: str = None,
    currency: str = None,
    startdate: str = None,
    enddate: str = None
):


    # Call get_RingProfitAllHandsPlayerIdSite() and unpack profits
    profits = get_RingProfitAllHandsPlayerIdSite(
        site=site,
        player=player,
        limit=limit,
        bigBlind=bigBlind,
        category=category,
        currency=currency,
        startdate=startdate,
        enddate=enddate
    )

    return JSONResponse(content=profits)


@app.get("/players")
async def get_players_api(
  name: str = None,
  site: str = None,
  page: int = 1, 
  per_page: int = 10
):

  # Call get_players() and unpack players and total
  players, total = get_players(
    name=name,
    site=site, 
    page=page,
    per_page=per_page
  )

  # Calculate total pages from total count
  total_pages = math.ceil(total / per_page)

  return JSONResponse({
    "data": players,
    "page": page,
    "per_page": per_page,
    "total": total,
    "total_pages": total_pages,
    "name": name, 
    "site": site
  })

@app.get("/players/{playerId}/hands", response_model=List[HandsPlayer])
def get_player_hands_api(playerId: int):
    # Your database query logic here to retrieve hands for the player with the given playerId
    # Replace this with your actual database query code
    
    handsPlayers = get_hands_players(playerId)  # Replace with your own function or code to retrieve hands
    
    return JSONResponse(content=handsPlayers)

@app.get("/hands/count")
async def get_handscount_api():
    hands_count = get_handscount()
    return JSONResponse(content=hands_count)

@app.get("/hands/count/cashgame")
async def get_handscount_cg_api():
    handscount_cg = get_handscount_cg()
    return JSONResponse(content=handscount_cg)

@app.get("/hands/count/tourneys")
async def get_handscount_tour_api():
    handscount_tour = get_handscount_tour()
    return JSONResponse(content=handscount_tour)

@app.get("/players/count")
async def get_playerscount_api():
    playerscount = get_playerscount()
    return JSONResponse(content=playerscount)

@app.get("/players/count/cashgame")
async def get_playerscount_cg_api():
    playerscount_cg = get_playerscount_cg()
    return JSONResponse(content=playerscount_cg)

@app.get("/players/count/tourneys")
async def get_playerscount_tour_api():
    playerscount_tour = get_playerscount_tour()
    return JSONResponse(content=playerscount_tour)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


