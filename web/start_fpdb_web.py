import subprocess

# Start the API server (api.py) as a separate process
api_process = subprocess.Popen(['python', 'api.py'])

# Start the Flask app (app.py) as a separate process
app_process = subprocess.Popen(['python', 'app.py'])

# Wait for both processes to complete
api_process.wait()
app_process.wait()