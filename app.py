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
    return templates.TemplateResponse("index.html", {"request": request, "handscount": handscount, "handscount_cg": handscount_cg, "handscount_tour": handscount_tour, "playerscount": playerscount, "playerscount_cg": playerscount_cg, "playerscount_tour": playerscount_tour})



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
    # Your code to fetch hands for the playerId goes here
    handsPlayers = get_hands_players(playerId)

    # Return the hands_players as a JSON response
    return templates.TemplateResponse("handsPlayers.html", {"request": request, "handsPlayers": handsPlayers})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)





