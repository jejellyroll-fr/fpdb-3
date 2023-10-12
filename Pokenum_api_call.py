import requests
from pydantic import BaseModel

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

# Create a PokenumRequest object with the desired parameters
request_body = PokenumRequest(
    game="-h",
    hand=['As', 'Ad', '-', 'Ks', 'Qs'],
    board=["--"],
    dead=["/"],
    method="",
    iterations="",
    histogram=False
)

# Send a POST request to the API with the request body
response = requests.post(f"{app_url}{endpoint}", json=request_body.dict())

# Print the response content
print(response.content)
