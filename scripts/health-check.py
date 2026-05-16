#!/usr/bin/env python3
"""Health check for all services."""
import sys, urllib.request, json

SERVICES = [
    ("DSL", "http://127.0.0.1:18800/api/v1/status"),
    ("n8n-lite", "http://127.0.0.1:5678/"),
]

all_ok = True
for name, url in SERVICES:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            d = json.loads(r.read().decode())
            ok = d.get("ok", False)
            print(f"{'OK' if ok else 'FAIL'} {name} at {url}")
            all_ok = all_ok and ok
    except Exception as e:
        print(f"FAIL {name} at {url}: {e}")
        all_ok = False

sys.exit(0 if all_ok else 1)
