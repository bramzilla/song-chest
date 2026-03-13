#!/bin/bash

# Song Forge — start script
# Run this from the songforge folder: ./start.sh

cd "$(dirname "$0")"

# Create venv if it doesn't exist yet
if [ ! -d "venv" ]; then
  echo "Setting up virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  echo "Done."
else
  source venv/bin/activate
fi

echo ""
echo "🎵  Starting Song Forge..."
echo "   Open http://localhost:5000 in your browser"
echo "   Press Ctrl+C to stop"
echo ""

python server.py
