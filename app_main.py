#!/usr/bin/env python3
"""Desktop entry point: runs the local server in a thread and shows the UI in a native window."""
import socket
import sys
import threading

import webview

import server


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    server.PORT = free_port()
    threading.Thread(target=server.main, daemon=True).start()

    window = webview.create_window(
        "LEOBOG AMG65 Studio",
        f"http://127.0.0.1:{server.PORT}",
        width=1280,
        height=900,
        min_size=(1024, 700),
    )
    window.events.closed += lambda: server.shutdown()
    webview.start()
    sys.exit(0)


if __name__ == "__main__":
    main()
