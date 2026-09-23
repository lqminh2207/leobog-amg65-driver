#!/usr/bin/env python3
"""Desktop entry point: runs the local server in a thread and shows the UI in a native window."""
import socket
import sys
import threading
import time

import webview

import server


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(port, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


class Api:
    """Exposed to the page as window.pywebview.api; WKWebView ignores <a download>."""

    def __init__(self):
        self.window = None

    def save_text(self, filename, text):
        result = self.window.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename)
        if not result:
            return None
        path = result if isinstance(result, str) else result[0]
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path


def main():
    server.PORT = free_port()
    threading.Thread(target=server.main, daemon=True).start()
    if not wait_for_server(server.PORT):
        sys.exit("Khong khoi dong duoc server noi bo")

    api = Api()
    api.window = webview.create_window(
        "LEOBOG AMG65 Studio",
        f"http://127.0.0.1:{server.PORT}",
        js_api=api,
        width=1280,
        height=900,
        min_size=(1024, 700),
    )
    api.window.events.closed += lambda: server.shutdown()
    webview.start()
    sys.exit(0)


if __name__ == "__main__":
    main()
