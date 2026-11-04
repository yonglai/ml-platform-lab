"""Send N requests to the served model and print p50/p95/p99 latency. These numbers feed your SLO.

Usage:  uv run python app/smoke.py --url http://localhost:5001 -n 200
"""
import argparse
import statistics
import time

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:5001")
ap.add_argument("-n", type=int, default=200)
args = ap.parse_args()

row = {f"f{i}": 0.1 * i for i in range(12)}
payload = {"dataframe_records": [row]}

lat = []
for _ in range(args.n):
    t = time.perf_counter()
    r = requests.post(f"{args.url}/invocations", json=payload, timeout=10)
    r.raise_for_status()
    lat.append((time.perf_counter() - t) * 1000)

lat.sort()
q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))]
print(f"last response: {r.json()}")
print(f"n={args.n}  p50={q(.50):.1f} ms  p95={q(.95):.1f} ms  p99={q(.99):.1f} ms  mean={statistics.mean(lat):.1f} ms")
