# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Song Chest macOS .app bundle
# Build with:  pyinstaller song-chest.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

block_cipher = None

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundle index.html so the server can serve it from sys._MEIPASS
        (str(ROOT / "index.html"), "."),
    ],
    hiddenimports=[
        # Flask + Werkzeug internals that PyInstaller may miss
        "flask",
        "flask.json",
        "werkzeug",
        "werkzeug.serving",
        "werkzeug.debug",
        "werkzeug.routing",
        "jinja2",
        "jinja2.ext",
        "click",
        "itsdangerous",
        # Standard lib modules used by server.py
        "hashlib",
        "re",
        "shutil",
        "uuid",
        "time",
        "threading",
        "webbrowser",
        "socket",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused heavy packages
        "tkinter",
        "unittest",
        "xmlrpc",
        "pydoc",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Song Chest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,         # UPX can cause false-positive AV flags on macOS
    console=False,     # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=True,   # Lets macOS pass file-open events to the app
    target_arch=None,      # None = current arch; use 'universal2' for fat binary
    codesign_identity=None,
    entitlements_file=None,
    icon=None,         # Replace with 'assets/icon.icns' once you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Song Chest",
)

app_bundle = BUNDLE(
    coll,
    name="Song Chest.app",
    icon=None,          # Replace with 'assets/icon.icns' once you have one
    bundle_identifier="com.songchest.app",
    info_plist={
        "CFBundleName":              "Song Chest",
        "CFBundleDisplayName":       "Song Chest",
        "CFBundleShortVersionString": "0.9.0",
        "CFBundleVersion":           "0.9.0",
        "NSPrincipalClass":          "NSApplication",
        "NSHighResolutionCapable":   True,
        "NSHumanReadableCopyright":  "Song Chest",
        # Allows network connections to localhost
        "NSAppTransportSecurity": {
            "NSAllowsLocalNetworking": True,
        },
    },
)
