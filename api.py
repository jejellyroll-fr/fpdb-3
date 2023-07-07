from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sql_request import *
from base_model import *
from typing import List, Optional

app = FastAPI()



@app.get("/hands", response_model=List[Hand])
async def get_hands_api():
    hands = get_hands()
    return JSONResponse(content=hands)



@app.get("/handsPlayers", response_model=List[HandsPlayer])
async def get_handsPlayers_api():
    handsPlayers = get_handsPlayers()
    return JSONResponse(content=handsPlayers)



@app.get("/players", response_model=List[Player])
async def get_players_api():
    players = get_players()
    return JSONResponse(content=players)

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


