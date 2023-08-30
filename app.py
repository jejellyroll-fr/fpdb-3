from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sql_request import *
from base_model import *
import math

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    handscount = get_handscount()
    handscount_cg = get_handscount_cg()
    handscount_tour = get_handscount_tour()
    playerscount = get_playerscount()
    playerscount_cg = get_playerscount_cg()
    playerscount_tour = get_playerscount_tour()
    heroes = get_heroes()
    return templates.TemplateResponse("index.html", {"request": request, "handscount": handscount, "handscount_cg": handscount_cg, "handscount_tour": handscount_tour, "playerscount": playerscount, "playerscount_cg": playerscount_cg, "playerscount_tour": playerscount_tour, "heroes": heroes})



@app.get("/hands", response_class=HTMLResponse)
async def get_hands_api(request: Request):
    hands = get_hands()
    return templates.TemplateResponse("hands.html", {"request": request, "hands": hands})
    


@app.get("/handsPlayers", response_class=HTMLResponse)
async def get_handsPlayers_api(request: Request):
    handsPlayers = get_handsPlayers()
    return templates.TemplateResponse("handsPlayers.html", {"request": request, "handsPlayers": handsPlayers})



@app.get("/players")
def get_players_endpoint(request: Request,
                         name: str = None, 
                         site: str = None,
                         page: int = 1,
                         per_page: int = 10):

  # Call get_players() and unpack players and total  
  players, total = get_players(
                               name=name,
                               site=site,
                               page=page,
                               per_page=per_page)

  # Calculate total pages from total count
  total_pages = math.ceil(total / per_page)

  return templates.TemplateResponse("players.html", {
    "request": request,
    "players": players,
    "page": page, 
    "per_page": per_page,
    "total": total,
    "total_pages": total_pages, 
    "name": name,
    "site": site  
  })

@app.get("/players/{playerId}/hands", response_class=HTMLResponse)
async def get_hands_players_api(playerId: int, request: Request):
    
    handsPlayers = get_hands_players(playerId)

    
    return templates.TemplateResponse("handsPlayers.html", {"request": request, "handsPlayers": handsPlayers})

@app.get("/RingProfitAllHandsPlayerIdSite", response_class=HTMLResponse)
async def get_ring_profit_all_hands_api(
    request: Request,
    site: int = None,
    player: int = None,
    limit: str = None,
    bigBlind: int = None,
    category: str = None,
    currency: str = None,
    startdate: str = None,
    enddate: str = None # Add this parameter
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

    # Fetch the player's name from your data source based on the 'player' parameter
    player_name = get_player_name(player)  

    return templates.TemplateResponse("RingGraph.html", {"request": request, "profits": profits, "player_name": player_name})

@app.get("/TourneysProfitPlayerIdSite", response_class=HTMLResponse)
async def get_torneys_profit_api(
    request: Request,
    site: int = None,
    player: int = None,
    limit: str = None,
    buyin: int = None,
    category: str = None,
    currency: str = None,
    startdate: str = None,
    enddate: str = None # Add this parameter
):

    # Call get_RingProfitAllHandsPlayerIdSite() and unpack profits
    profits = get_tourneysProfitPlayerIdSite(
        site=site,
        player=player,
        limit=limit,
        buyin=buyin,
        category=category,
        currency=currency,
        startdate=startdate,
        enddate=enddate
    )

    # Fetch the player's name from your data source based on the 'player' parameter
    player_name = get_player_name(player)  

    return templates.TemplateResponse("TourneysGraph.html", {"request": request, "profits": profits, "player_name": player_name})

@app.get("/statsplayers", response_class=HTMLResponse)
async def get_statsplayers_api(
    request: Request,
    site: int = None,
    player: int = None,
    limit: str = None,
    bigBlind: int = None,
    category: str = None,
    currency: str = None,
    startdate: str = None,
    enddate: str = None
):
    result = get_statsplayers(
        site=site,
        player=player,
        limit=limit,
        bigBlind=bigBlind,
        category=category,
        currency=currency,
        startdate=startdate,
        enddate=enddate
    )  # Call the get_statsplayers() function to retrieve the statistics

    return templates.TemplateResponse("statsplayers.html", {"request": request, "result": result})



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)





