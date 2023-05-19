import subprocess

# Set the path to the Python module
MODULE_PATH = "/Users/jdenis/fpdb-3/pyfpdb/*.py"

# Set the path to the source root directory
SOURCE_DIR = "/Users/jdenis/fpdb-3/pyfpdb"

# Define the Pyreverse command to generate the PlantUML output
COMMAND = f"pyreverse -o puml -p FPDB --source {SOURCE_DIR} {MODULE_PATH}"

# Execute the Pyreverse command and capture its output
output_bytes = subprocess.check_output(COMMAND, shell=True)

# Decode the output bytes into a string
output_string = output_bytes.decode()

# Print the PlantUML output
print(output_string)







