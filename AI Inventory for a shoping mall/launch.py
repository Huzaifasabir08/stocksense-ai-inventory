"""Start/reuse the local app, wait for readiness, and supervise crashes."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("STOCKSENSE_PORT", "8765"))
URL = f"http://127.0.0.1:{PORT}"
STATE = ROOT / ".runtime"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def healthy():
    try:
        with OPENER.open(URL + "/healthz", timeout=1) as response:
            data = json.load(response)
        return data.get("service") == "stocksense" and Path(data.get("project", "")).resolve() == ROOT
    except (OSError, ValueError):
        return False


def occupied():
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", PORT)) == 0


def supervise():
    STATE.mkdir(exist_ok=True)
    lock = STATE / f"supervisor-{PORT}.lock"
    # Windows releases this lock on exit, including a crash; stale files are safe.
    import msvcrt
    with lock.open("a+b") as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        failures = 0
        while failures < 5:
            if occupied():
                return  # Never terminate or adopt another project's process.
            with (STATE / "server.log").open("a", encoding="utf-8") as log:
                child = subprocess.Popen([sys.executable, "-u", str(ROOT / "app.py")], cwd=ROOT,
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                started = time.monotonic()
                child.wait()
            failures = 1 if time.monotonic() - started > 60 else failures + 1
            time.sleep(min(failures * 2, 10))


def launch(open_browser=True):
    if not healthy():
        if occupied():
            raise RuntimeError(f"Port {PORT} is occupied by another or outdated service. No process was stopped.")
        STATE.mkdir(exist_ok=True)
        with (STATE / "launcher.log").open("a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--supervise"], cwd=ROOT,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if healthy():
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f"Server did not become ready. See {STATE / 'server.log'} and launcher.log.")
    print(f"StockSense ready: {URL}")
    if open_browser:
        webbrowser.open(URL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--supervise", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()
    try:
        supervise() if options.supervise else launch(not options.no_browser)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"StockSense startup failed: {error}", file=sys.stderr)
        sys.exit(1)
