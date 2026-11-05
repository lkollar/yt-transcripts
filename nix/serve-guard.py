"""Reject destructive Serve updates before and after calling Tailscale."""
import json
import sys


def check(before, host, port, after=None):
    proxy = {"Proxy": f"http://127.0.0.1:{port}"}
    https_port = host.rsplit(":", 1)[1]
    tcp = before.get("TCP", {}).get(https_port)
    if tcp is not None and tcp != {"HTTPS": True}:
        raise ValueError("Existing port configuration conflicts; left untouched")
    handlers = before.get("Web", {}).get(host, {}).get("Handlers", {})
    if any(path != "/" or value != proxy for path, value in handlers.items()):
        raise ValueError("Existing route conflicts; left untouched")
    if before.get("AllowFunnel", {}).get(host, False):
        raise ValueError("Existing port has Funnel enabled; app must remain private")
    if after is None:
        return
    for name, web in before.get("Web", {}).items():
        for path, value in web.get("Handlers", {}).items():
            if after.get("Web", {}).get(name, {}).get("Handlers", {}).get(path) != value:
                raise ValueError("Existing route changed")
    for key in ("TCP", "AllowFunnel"):
        for name, value in before.get(key, {}).items():
            if after.get(key, {}).get(name) != value:
                raise ValueError("Existing serve setting changed")
    if after.get("Web", {}).get(host, {}).get("Handlers", {}).get("/") != proxy:
        raise ValueError("Expected private route missing")
    if after.get("AllowFunnel", {}).get(host, False):
        raise ValueError("App route must remain private")


if __name__ == "__main__":
    try:
        before = json.load(open(sys.argv[1]))
        after = json.load(open(sys.argv[4])) if len(sys.argv) == 5 else None
        check(before, sys.argv[2], sys.argv[3], after)
    except ValueError as error:
        raise SystemExit(str(error))
