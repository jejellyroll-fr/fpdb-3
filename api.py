from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sql_request import *
from base_model import *

app = FastAPI()

@app.get("/backings")
async def get_backings_api():
    backings = get_backings()
    return JSONResponse(content=backings)

@app.get("/actions")
async def get_actions_api():
    actions = get_actions()
    return JSONResponse(content=actions)

@app.get("/autorates")
async def get_autorates_api():
    autorates = get_autorates()
    return JSONResponse(content=autorates)

@app.get("/boards")
async def get_boards_api():
    boards = get_boards()
    return JSONResponse(content=boards)

@app.get("/cardsCaches")
async def get_cardsCaches_api():
    cardsCaches = get_cardsCaches()
    return JSONResponse(content=cardsCaches)

@app.get("/files")
async def get_files_api():
    files = get_files()
    return JSONResponse(content=files)

@app.get("/gametypes")
async def get_gametypes_api():
    gametypes = get_gametypes()
    return JSONResponse(content=gametypes)

@app.get("/hands")
async def get_hands_api():
    hands = get_hands()
    return JSONResponse(content=hands)

@app.get("/handsActions")
async def get_handsActions_api():
    handsActions = get_handsActions()
    return JSONResponse(content=handsActions)

@app.get("/handsPlayers")
async def get_handsPlayers_api():
    handsPlayers = get_handsPlayers()
    return JSONResponse(content=handsPlayers)

@app.get("/handsPots")
async def get_handsPots_api():
    handsPots = get_handsPots()
    return JSONResponse(content=handsPots)

@app.get("/handsStoves")
async def get_handsStoves_api():
    handsStoves = get_handsStove()
    return JSONResponse(content=handsStoves)

@app.get("/players")
async def get_players_api():
    players = get_players()
    return JSONResponse(content=players)

@app.get("/players/{playerId}/hands")
def get_player_hands_api(playerId: int):
    # Your database query logic here to retrieve hands for the player with the given playerId
    # Replace this with your actual database query code
    
    handsPlayers = get_hands_players(playerId)  # Replace with your own function or code to retrieve hands
    
    return JSONResponse(content=handsPlayers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


