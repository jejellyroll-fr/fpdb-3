import requests
from pydantic import BaseModel
import json

class PokenumRequest(BaseModel):
    game: str
    hand: list
    board: list = []
    dead: list = []
    method: str = None
    iterations: str = None
    histogram: bool = False

app_url = "http://localhost:8000"  # Replace with the actual URL of the API
endpoint = "/pokenum"

def run_pokenum(method, iterations, game, hand, board, dead):
    # Create a PokenumRequest object with the desired parameters
    request_body = PokenumRequest(
        method=method,
        iterations=iterations,
        game=game,
        hand=hand,
        board=board,
        dead=dead,
        histogram=False
    )

    # Send a POST request to the API with the request body
    response = requests.post(f"{app_url}{endpoint}", json=request_body.dict())
    content = response.content.decode("utf-8")
    data_dict = json.loads(content)
    # Return the response content
    return data_dict

