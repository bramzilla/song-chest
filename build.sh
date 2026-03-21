#!/usr/bin/env bash
# Build Song Chest.app
# Usage: bash build.sh
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo ""
echo "  🎵  Building Song Chest.app"
echo ""

# Ensure we're in a venv with dependencies
if [ ! -d "venv" ]; then
    echo "  Creating virtualenv..."
    python3 -m venv venv
fi
source venv/bin/activate

echo "  Installing / updating dependencies..."
pip install -q -r requirements.txt
pip install -q pyinstaller

echo "  Cleaning previous build..."
rm -rf build dist

echo "  Running PyInstaller..."
pyinstaller song-chest.spec --noconfirm

echo ""
echo "  ✓  Done!"
echo ""
echo "  App:  dist/Song Chest.app"
echo "  Size: $(du -sh "dist/Song Chest.app" | cut -f1)"
echo ""
echo "  To install: drag  dist/Song Chest.app  to your Applications folder."
echo ""
