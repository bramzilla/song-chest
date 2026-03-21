"""
Song Chest — packaged app entry point.

This is the script PyInstaller uses as the entry point for the .app bundle.
It starts the Flask server then opens the user's default browser.
Running from source: use server.py directly (or start.sh).
"""

import sys
import threading
import webbrowser
import time
import socket


def _find_port(start: int = 5000, tries: int = 10) -> int:
    """Return the first free TCP port starting at `start`."""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start  # fall back; app.run will surface the error


def _open_browser(port: int) -> None:
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    import server

    port = _find_port()

    t = threading.Thread(target=_open_browser, args=(port,), daemon=True)
    t.start()

    print(f"\n  🎵  Song Chest v{server.APP_VERSION}")
    print(f"  → http://127.0.0.1:{port}\n")

    server.app.run(
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
    )
