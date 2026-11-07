"""In-cluster prober: one request per second to the model, exposed as Prometheus metrics.

mlflow models serve has no request metrics, so we measure from outside, the way a client sees it.
Metrics on :8000/metrics
  prober_request_duration_seconds   histogram of request latency (successful requests only)
  prober_requests_total{result}     counter, result="ok" or "error"

Usage:  python app/prober.py --url http://serving:5001 --interval 1
"""

import argparse
import http.client
import json
import time
import urllib.request

from prometheus_client import Counter, Histogram, start_http_server

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://serving:5001")
ap.add_argument("--interval", type=float, default=1.0)
ap.add_argument("--timeout", type=float, default=2.0)
ap.add_argument("--port", type=int, default=8000)
args = ap.parse_args()

# Bucket edges include 0.1 s so an SLO of "p99 < 100 ms" can be read straight from the histogram.
LATENCY = Histogram(
    "prober_request_duration_seconds",
    "Latency of successful prediction requests",
    buckets=(0.005, 0.01, 0.015, 0.02, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)
REQUESTS = Counter("prober_requests_total", "Prediction requests by result", ["result"])
REQUESTS.labels("ok")
REQUESTS.labels(
    "error"
)  # create both series at 0 so rate() works before the first failure

row = {f"f{i}": 0.1 * i for i in range(12)}
body = json.dumps({"dataframe_records": [row]}).encode()

start_http_server(args.port)
print(
    f"probing {args.url} every {args.interval}s, metrics on :{args.port}/metrics",
    flush=True,
)

while True:
    t = time.perf_counter()
    try:
        req = urllib.request.Request(
            f"{args.url}/invocations",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=args.timeout) as r:
            r.read()
            ok = r.status == 200
    except (
        OSError,
        http.client.HTTPException,
    ) as e:  # refused, timeout, HTTP error, bad response
        ok = False
        print(f"error: {e}", flush=True)
    elapsed = time.perf_counter() - t
    if ok:
        LATENCY.observe(elapsed)
        REQUESTS.labels("ok").inc()
    else:
        REQUESTS.labels("error").inc()
    time.sleep(max(0.0, args.interval - elapsed))
