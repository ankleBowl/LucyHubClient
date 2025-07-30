#!/bin/bash

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Store current git commit hash
CURRENT_COMMIT=$(git rev-parse HEAD)
COMMIT_FILE=".last_commit"

# Check if dependencies need to be reinstalled
if [ ! -f "$COMMIT_FILE" ] || [ "$(cat $COMMIT_FILE)" != "$CURRENT_COMMIT" ]; then
    echo "Git commit changed, reinstalling dependencies..."
    pip install -r requirements.txt
    echo "$CURRENT_COMMIT" > "$COMMIT_FILE"
else
    echo "Dependencies up to date."
fi

# Load environment variables
if [ -f ".env" ]; then
    echo "Loading environment variables..."
    export $(grep -v '^#' .env | xargs)
else
    echo "Warning: .env file not found."
fi

# Run the main application
echo "Starting application..."
python main.py