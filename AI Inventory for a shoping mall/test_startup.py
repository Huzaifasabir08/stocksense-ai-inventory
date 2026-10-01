"""Exercise startup and read-only API flows against the local app."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:" + os.environ.get("STOCKSENSE_PORT", "8765")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
    try:
        with opener.open(req, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def launch():
    result = subprocess.run([sys.executable, str(ROOT / "launch.py"), "--no-browser"],
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    before = hashlib.sha256((ROOT / "stocksense.db").read_bytes()).hexdigest()
    launch()
    pid = request("/healthz")[1]["pid"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda _: launch(), range(3)))
    assert request("/healthz")[1]["pid"] == pid, "Duplicate launch replaced server"
    print("PASS: repeat and simultaneous launches reuse one server")

    assert request("/api/dashboard")[0] == 401
    assert request("/api/login", {"email": "manager@stocksense.local", "password": "wrong"})[0] == 401
    for role, password in [("manager", "manager123"), ("staff", "staff123")]:
        status, login = request("/api/login", {"email": role + "@stocksense.local", "password": password})
        assert status == 200 and login["user"]["role"] == role
        token = login["token"]
        assert request("/api/dashboard", token=token)[0] == 200
        status, products = request("/api/products", token=token)
        assert status == 200 and products
        assert request("/api/history", token=token)[0] == 200
        if role == "staff":
            assert "cost_price" not in products[0]
            assert request("/api/reports", token=token)[0] == 403
            assert request("/api/users", token=token)[0] == 403
        else:
            assert request("/api/reports", token=token)[0] == 200
            assert request("/api/users", token=token)[0] == 200
        assert request("/api/logout", {}, token)[0] == 200
        assert request("/api/dashboard", token=token)[0] == 401
    print("PASS: manager/staff login, dashboard, API, permissions, and logout")

    with socket.socket() as conflict:
        conflict.bind(("127.0.0.1", 0))
        conflict.listen()
        env = dict(os.environ, STOCKSENSE_PORT=str(conflict.getsockname()[1]))
        result = subprocess.run([sys.executable, str(ROOT / "launch.py"), "--no-browser"],
                                env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and "occupied" in result.stderr
        assert conflict.fileno() != -1
    print("PASS: conflicting service is reported and left running")

    # Only stop the PID returned by this project's health endpoint.
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            status, health = request("/healthz")
            if status == 200 and health["pid"] != pid:
                break
        except OSError:
            pass
        time.sleep(0.25)
    else:
        raise AssertionError("Supervisor did not recover the server")
    print("PASS: server automatically recovers after an unexpected exit")
    assert hashlib.sha256((ROOT / "stocksense.db").read_bytes()).hexdigest() == before
    print("PASS: existing SQLite database unchanged")
