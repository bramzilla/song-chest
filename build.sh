#!/usr/bin/env bash
# Build Song Chest.app and package it as a drag-to-install DMG.
# Usage: bash build.sh
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VERSION=$(python3 -c "import re; print(re.search(r'APP_VERSION\s*=\s*\"(.+?)\"', open('server.py').read()).group(1))")

echo ""
echo "  🎵  Building Song Chest v${VERSION}"
echo ""

# ── 1. Virtualenv + dependencies ──────────────────────────────
if [ ! -d "venv" ]; then
    echo "  Creating virtualenv..."
    python3 -m venv venv
fi
source venv/bin/activate

echo "  Installing / updating dependencies..."
pip install -q -r requirements.txt
pip install -q pyinstaller

# ── 2. PyInstaller .app ───────────────────────────────────────
echo "  Cleaning previous build..."
rm -rf build dist

echo "  Running PyInstaller..."
pyinstaller song-chest.spec --noconfirm

APP="dist/Song Chest.app"
echo "  ✓  App built  ($(du -sh "$APP" | cut -f1))"

# ── 3. DMG ────────────────────────────────────────────────────
echo "  Building DMG..."

DMG_DIR="dist/dmg-staging"
DMG_OUT="dist/Song Chest ${VERSION}.dmg"

rm -rf "$DMG_DIR"
mkdir -p "$DMG_DIR"

# Copy the app and add an Applications shortcut
cp -r "$APP" "$DMG_DIR/"
ln -sf /Applications "$DMG_DIR/Applications"

# Create the DMG (UDZO = compressed)
hdiutil create \
    -volname "Song Chest ${VERSION}" \
    -srcfolder "$DMG_DIR" \
    -ov \
    -format UDZO \
    "$DMG_OUT"

rm -rf "$DMG_DIR"

echo ""
echo "  ✓  Done!"
echo ""
echo "  DMG:  $DMG_OUT"
echo "  Size: $(du -sh "$DMG_OUT" | cut -f1)"
echo ""
echo "  Share this file. Users open it and drag Song Chest to Applications."
echo ""
