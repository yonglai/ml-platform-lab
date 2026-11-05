# ml-platform-lab LOG

Same format as inference-track: predictions first, then results, then lessons.

## 2026-11-03 — Scaffold

Repo created. `app/train.py`, `app/promote.py`, `app/smoke.py` tested locally against sqlite MLflow 3.18 (no cluster).

**Results**

- First train → promote: no prod yet, so v1 promoted.
- Better challenger (roc_auc 0.9575 vs 0.9068): promoted.
- Worse challenger (0.8433): REJECTED, exit code 1.
- `mlflow models serve -m models:/propensity-model@prod` served locally; smoke test p50 5.1 ms, p95 6.5 ms, p99 37.0 ms (n=100, local, 1 request at a time).

**Lessons**

1. MLflow 3.x saves sklearn models with skops, which refuses untrusted types on load. Random forests need `skops_trusted_types=["sklearn.tree._tree.Tree"]` in `log_model`, otherwise `log_model` itself fails when it validates the saved file.

## 2026-11-04 - Step 1, Postgres

Built `k8s/10-postgres.yaml`: Secret, headless Service, StatefulSet with a 5Gi PVC (local-path).

**Predictions vs results**

- PVC Bound or Pending after apply? Predicted: Pending. Actual: right. StorageClass mode is WaitForFirstConsumer. Events: WaitForFirstConsumer -> Provisioning -> ProvisioningSucceeded; by the time I ran `get`, it was Bound.
- Delete the pod: data survives, what brings it back? Predicted: yes, Kubernetes recreates it. Actual: yes. Row survived, same name postgres-0, Ready in 6 s. The StatefulSet controller reconciles to replicas=1 (this is not autoscaling).
- Delete the StatefulSet: PVC stays? Predicted: yes. Actual: PVC stays Bound.

**Lessons**

1. EndpointSlice is empty until the pod is Ready; an empty one on a Ready pod would mean a selector typo.
2. The StorageClass reclaim policy is Delete: deleting the PVC deletes the data. Deleting the pod or StatefulSet does not.
3. POSTGRES_USER becomes the superuser, so MLflow would run with admin rights. Use a limited role in a real deployment.

**Done**: row survived `kubectl delete pod postgres-0`: yes.

## 2026-11-04 - Step 2, MLflow server

Built `k8s/20-mlflow.yaml`: PVC for artifacts, Deployment (`python:3.12-slim`, `pip install mlflow==3.18.0 psycopg2-binary` at container start, then `mlflow server` with `--serve-artifacts --artifacts-destination /mlartifacts` and `--allowed-hosts`), ClusterIP Service on 5000. Metadata goes to the Postgres from Step 1.

**What went wrong, in order**

1. `CrashLoopBackOff` right away. Logs (`--previous`): `ModuleNotFoundError: No module named 'psycopg'`. A bare `postgresql://` URL lets SQLAlchemy choose the driver, and SQLAlchemy 2.1.x now defaults to `psycopg` (v3), not `psycopg2`. Checked locally: `postgresql://` -> `psycopg`, `postgresql+psycopg2://` -> `psycopg2`. Fix: name the driver in the URL.
2. Next crash: `OOMKilled` after the pod had been Ready, restart loop with growing back-off. Raising the limit from 2Gi to 3Gi (requests 768Mi) stopped the kills but idle memory was still 2125Mi, which is too much for a tracking server.
3. Where the memory went: `kubectl top` 2125Mi; cgroup `memory.stat` anon 2018 MiB, file 836 MiB (almost all inactive, reclaimable). Reading `/proc/<pid>/status` (the slim image has no `ps`): 8 Python processes at about 270 MB RSS each, five of them the job runner and `huey` consumers from MLflow 3.x job execution, which this lab does not use.
4. Fix: `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false` (value must be the quoted string `"false"`). Idle memory 2125Mi -> 637Mi, Ready in 50 s, `RESTARTS 0`.
5. From a second pod, `curl http://mlflow:5000/health` first gave `Connection refused` while the pod was crash-looping: a Service with no Ready endpoints refuses connections.

**Predictions vs results**

- Process count after disabling job execution: predicted 4. Actual: 3 heavy processes (parent + 2 uvicorn workers, about 280 MB RSS each) plus 2 small helpers (uvicorn supervisor 28 MB, resource tracker 13 MB). The answer depends on what you count.
- Memory after disabling: predicted about 1Gi. Actual: 637Mi. The RSS values sum to about 876 MB but `top` says 637Mi, because RSS counts shared pages once per process. Use `top` or cgroup `anon` for sizing.
- Bad Host header: predicted 403. Actual: 403 on `/api/2.0/mlflow/experiments/get?experiment_id=0` with `Host: evil.example`; good host `mlflow:5000` returned 200. (`/health` and `/version` are exempt from Host validation, so the first test on `/health` returned 200 for any host and proved nothing.)
- Time to Ready on first start, and what happens when Postgres is down: no prediction written. Ready took about 50-60 s each start (pip install repeats on every restart).

**Lessons**

1. Name the database driver in the URL (`postgresql+psycopg2://`); do not rely on a library default that can change between versions.
2. `CrashLoopBackOff` is the symptom; the cause is in `describe` (Reason) and `logs --previous`.
3. OOMKilled means the container went over its memory limit. Memory has no throttling like CPU: it is killed.
4. Each Python process holds its own copy of the imported libraries, so memory scales with process count. Measure before sizing: `kubectl top`, cgroup `anon` vs `file`, per-process RSS.
5. Disabling an unused background feature cut memory by about 70%.
6. `Connection refused` to a Service means no Ready endpoints (or nothing listening); a timeout means the path is blocked; a 403 means you reached the server and it rejected you.
7. Test a security control on a path that enforces it, not on a health endpoint.
8. `pip install` at container start turns every restart into a one-minute outage. A real setup builds the image once.

**Done**: from a pod in the cluster, `http://mlflow:5000` answers with 200 on a non-exempt API path and rejects a bad Host with 403; the pod stays at `RESTARTS 0` at 637Mi.

<!-- New entries go ABOVE this line, newest last. Keep it chronological. -->
