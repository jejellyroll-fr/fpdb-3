from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sql_request import *
from base_model import *

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    context = {"request": request, "name": "World"}
    return templates.TemplateResponse("index.html", context)

@app.get("/backings", response_class=HTMLResponse)
async def get_backings_api(request: Request):
    backings = get_backings()
    return templates.TemplateResponse("backings.html", {"request": request, "backings": backings})

@app.get("/actions", response_class=HTMLResponse)
async def get_actions_api(request: Request):
    actions = get_actions()
    return templates.TemplateResponse("actions.html", {"request": request, "actions": actions})

@app.get("/autorates", response_class=HTMLResponse)
async def get_autorates_api(request: Request):
    autorates = get_autorates()
    return templates.TemplateResponse("autorates.html", {"request": request, "autorates": autorates})

@app.get("/boards", response_class=HTMLResponse)
async def get_boards_api(request: Request):
    boards = get_boards()
    return templates.TemplateResponse("boards.html", {"request": request, "boards": boards})

@app.get("/cardsCaches", response_class=HTMLResponse)
async def get_cardsCaches_api(request: Request):
    cardsCaches = get_cardsCaches()
    return templates.TemplateResponse("cardsCaches.html", {"request": request, "cardsCaches": cardsCaches})

@app.get("/files", response_class=HTMLResponse)
async def get_files_api(request: Request):
    files = get_files()
    return templates.TemplateResponse("files.html", {"request": request, "files": files})

@app.get("/gametypes", response_class=HTMLResponse)
async def get_gametypes_api(request: Request):
    gametypes = get_gametypes()
    return templates.TemplateResponse("gametypes.html", {"request": request, "gametypes": gametypes})

@app.get("/hands", response_class=HTMLResponse)
async def get_hands_api(request: Request):
    hands = get_hands()
    return templates.TemplateResponse("hands.html", {"request": request, "hands": hands})
    
@app.get("/handsActions", response_class=HTMLResponse)
async def get_handsActions_api(request: Request):
    handsActions = get_handsActions()
    return templates.TemplateResponse("handsActions.html", {"request": request, "handsActions": handsActions})

@app.get("/handsPlayers", response_class=HTMLResponse)
async def get_handsPlayers_api(request: Request):
    handsPlayers = get_handsPlayers()
    return templates.TemplateResponse("handsPlayers.html", {"request": request, "handsPlayers": handsPlayers})

@app.get("/handsPots", response_class=HTMLResponse)
async def get_handsPots_api(request: Request):
    handsPots = get_handsPots()
    return templates.TemplateResponse("handsPots.html", {"request": request, "handsPots": handsPots})

@app.get("/handsStoves", response_class=HTMLResponse)
async def get_handsStoves_api(request: Request):
    handsStoves = get_handsStove()
    return templates.TemplateResponse("handsStoves.html", {"request": request, "handsStoves": handsStoves})

@app.get("/players", response_class=HTMLResponse)
async def get_players_api(request: Request):
    players = get_players()
    return templates.TemplateResponse("players.html", {"request": request, "players": players})

@app.get("/players/{playerId}/hands", response_class=HTMLResponse)
async def get_hands_players_api(playerId: int, request: Request):
    # Your code to fetch hands for the playerId goes here
    handsPlayers = get_hands_players(playerId)

    # Return the hands_players as a JSON response
    return templates.TemplateResponse("handsPlayers.html", {"request": request, "handsPlayers": handsPlayers})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=80)





