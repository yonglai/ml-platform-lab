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

## 2026-11-05 - Step 3, train and register on the cluster

Ran `app/train.py` twice against the in-cluster MLflow (`MLFLOW_TRACKING_URI=http://localhost:5000` through `kubectl port-forward svc/mlflow 5000:5000` on g1). Metadata goes to Postgres, model files go to the artifacts PVC through the server (`--serve-artifacts`).

**Results**

| Version | Params | roc_auc | Run time | Alias |
|---|---|---|---|---|
| v1 | n_estimators=50, max_depth=4 | 0.9068 | 1.2 s | none |
| v2 | n_estimators=200, max_depth=8 | 0.9575 | 2.1 s | `candidate` |

- The metrics are identical to the earlier local sqlite run (0.9068 and 0.9575): same data and seed give the same result on the cluster.
- Setting an alias on a new version moves it: `candidate` went to v2 and v1 lost it.
- Files on the volume: `/mlartifacts/1/models/m-<id>/artifacts`, one directory per logged model (experiment id 1). MLflow 3.x stores a model as its own entity under `models/`, not inside the run folder.
- My machine never mounted the PVC: it uploaded the model over HTTP and the server wrote it to `/mlartifacts`.
- Persistence test: `kubectl delete pod` on the MLflow pod. After the new pod came up, v1, v2, the alias `candidate -> v2` and both model directories were all still there. The records live in Postgres and the files on the PVC, neither of which is inside the pod.

**Predictions vs results**

- Where do the model files live, and how did my machine upload them without mounting the PVC? Predicted: ___. Actual: on the PVC under `/mlartifacts`, uploaded over HTTP through the server.
- Which version gets `candidate`, and what happens to v1? Predicted: ___. Actual: v2 gets it and v1 loses it.
- Do versions and files survive deleting the MLflow pod? Predicted: ___. Actual: yes, everything survived.

**What went wrong**

1. My first registry query printed nothing and logged "Creating initial MLflow database tables". `MLFLOW_TRACKING_URI` was unset in that terminal, so MLflow silently created a local DB and found no versions. Environment variables are per shell.
2. `search_model_versions` returned `aliases=[]` for every version, even though `candidate -> v2` was set. That call does not fill in aliases. Use `get_registered_model(name).aliases` (a map of alias to version) or `get_model_version`.
3. The UI seemed to have no model versions: the default GenAI view of an experiment does not show them. The **Model training** toggle (top left of the sidebar) has Models.
4. Reaching the UI from my Mac: `localhost:5000` is also used by AirPlay Receiver (`ControlCe` listening on `*:5000`). While my `ssh -L` tunnel was up, the browser reached MLflow; when the tunnel closed, `localhost:5000` fell through to AirPlay and looked like MLflow was down. `lsof -nP -iTCP:5000 -sTCP:LISTEN` showed who owned the port. VS Code's Ports tab only had 8888 ("Statically Forwarded"), so VS Code was not forwarding 5000.

**Lessons**

1. Check `echo $MLFLOW_TRACKING_URI` before trusting an empty result; an unset tracking URI fails silently instead of loudly.
2. Aliases are a model-level map, and a list call may not populate them. Read them from the registered model.
3. A tunnel from the Mac lives only as long as its ssh session. Use a free local port and keep-alives: `ssh -N -o ServerAliveInterval=30 -L 5050:localhost:5000 alienware`, then open `localhost:5050`.
4. Three hops (browser, ssh tunnel, `kubectl port-forward`, pod) mean three places for the UI to break. Test each from the far end: `curl localhost:5000/health` on g1 first, then on the Mac.
5. Reproducible training (fixed seed and data) gives identical metrics across environments, which is what makes a promotion gate meaningful.

**Done**: two versions registered through the cluster, `candidate` on v2, and everything survived deleting the MLflow pod.

## 2026-11-05 - Step 4, promotion gate

Ran `app/promote.py` against the cluster registry (`MLFLOW_TRACKING_URI=http://localhost:5000`). The gate compares the `roc_auc` of the version with alias `candidate` to the current `prod` and moves `prod` only if the candidate is at least as good; otherwise it exits 1. `app/show_registry.py` (new) prints each version with its aliases.

**What happened, in order**

| Action | Output | Registry afterwards |
|---|---|---|
| `promote.py` with no `prod` | `no prod yet: promoting v2 (roc_auc=0.9575)`, exit 0 | v2: candidate, prod |
| `train.py --n-estimators 3 --max-depth 2` | v3, roc_auc 0.8433 | v3 gets `candidate` |
| `promote.py` | `REJECTED: v3 (0.8433) does not beat prod v2 (0.9575) by 0.0`, exit 1 | v2: prod; v3: candidate |
| `train.py --n-estimators 300 --max-depth 10` | v4, roc_auc 0.9676 | v4 gets `candidate` |
| `promote.py` | `promoting v4 (0.9676) over prod v2 (0.9575)`, exit 0 | v4: candidate, prod; v1-v3 no aliases |

Rollback check: moved `prod` from v4 back to v2 with `set_registered_model_alias`. Afterwards `show_registry.py` showed v2: `prod` and v4: `candidate` (v4, roc_auc 0.9676, is better than v2, 0.9575), and the serving pod later resolved v2. I have not moved `prod` forward again yet; that is the next promotion.

**Predictions vs results**

- First `promote.py` with no `prod`: which version becomes `prod`? Predicted: v2. Actual: right.
- Worse model (3 trees, depth 2): message, exit code, which version is `prod`? Predicted: REJECTED, exit 1, `prod` stays v2. Actual: right.
- After the rejection, where does `candidate` point, and is that good design? Predicted: still v2, good design. Actual: wrong. `candidate` pointed at v3, the rejected model. `train.py` moves `candidate` to every new version it registers, and `promote.py` never changes it.
- Does promotion change anything on the PVC? Predicted: database only, not `/mlartifacts`. Actual: not measured yet; compare `find /mlartifacts` before and after a `promote.py` run.

**What went wrong**

1. In a new shell, `show_registry.py` printed `tracking uri: sqlite:///mlflow-local.db` and showed v1 with `candidate` and `prod`. `MLFLOW_TRACKING_URI` was unset, so it read the local file from my pre-flight sanity check, not the cluster. I had not run `promote.py` yet, so nothing was changed there. After `export MLFLOW_TRACKING_URI=http://localhost:5000` it showed the real v1 and v2. Second time this variable bit me.
2. Pasting a heredoc with two leading spaces left the shell at a `>` prompt: the closing `EOF` must start at column 0. Ctrl+C cancels it; a one-line `python -c '...'` avoids the problem.

**Lessons**

1. A script that prints which registry it is connected to turns a silent mistake into a visible one on the first line.
2. `candidate` means "the most recently trained version". Training moves it; the gate only reads it. A rejected model therefore stays labeled `candidate` and nothing records that it failed.
3. Aliases are labels in the database. Promotion and rollback only move a label; the model files stay on the PVC, so rolling back to v2 is one `set_registered_model_alias` call.
4. The gate's exit code (0 promoted, 1 rejected) is what CI uses. Added a step to `.github/workflows/model-ci.yml` that trains a worse model and fails the job if `promote.py` accepts it. Simulated the same sequence locally on a fresh sqlite registry (baseline promoted, challenger promoted, worse model rejected). Not run on GitHub yet.
5. Training with fixed seeds is deterministic: v3 scored 0.8433 on the cluster, exactly as in the local test.
6. Two warnings in the training log: "has no artifacts at artifact path 'model', registering model based on models:/m-..." (MLflow 3.x stores a model as its own logged-model entity and the registration falls back to it; harmless, but `train.py` could register the URI that `log_model` returns), and "Exported 91 dependencies via uv" (the model's recorded requirements are my whole `uv.lock`). The second matters for Step 5: the serving pod must install a scikit-learn version compatible with the one the model was trained with.

**Open question for the reference architecture doc:** what should happen to a rejected candidate? Options: tag the version `gate=rejected` with the reason and both `roc_auc` values; remove the `candidate` alias on rejection; or leave it and document the meaning.

**Done**: the gate behaved correctly in both directions on the cluster (promote on improvement, reject on regression with exit 1), and `prod` ended on v4.

## 2026-11-06 - Step 5, serving from @prod

Built `k8s/30-serving.yaml`: a Deployment and a ClusterIP Service (port 5001) that serve the model behind the `prod` alias. Image `python:3.12-slim`; at start the container runs `pip install` with the versions pinned from `uv.lock` (mlflow 3.18.0, scikit-learn 1.9.1, pandas 3.1.0, numpy 2.5.4, scipy 1.18.1, skops 0.16.0), asks the registry which version `prod` is, prints `resolved propensity-model@prod -> v<N>`, then serves that exact version with `mlflow models serve` (1 worker, `--env-manager local`).

**Design decisions**

- Resolve the alias once, then serve a fixed version number. The log line always says which version the pod serves, and a running pod never switches versions when someone moves the alias.
- Pin the libraries to the versions the model was trained with. The training run recorded my whole `uv.lock` (91 packages) as the model's requirements, and a model saved with one scikit-learn version may fail under another.
- `RollingUpdate` with `maxSurge: 1` and `maxUnavailable: 0`: the old pod stays until the new one is Ready.
- Probes on `/ping`: `startupProbe` (up to 5 minutes), `readinessProbe`, `livenessProbe`. Requests 512Mi / limit 1536Mi (set high on purpose after the Step 2 OOM kills; to be sized from measurements).

**Predictions vs results**

- How long until Ready, what takes the time, and which probe protects the pod? Predicted: downloading the model and preparing it for serving; the `startupProbe`. Actual: 50 s to `1/1`. What dominated: not measured; my guess is the `pip install`, as in Step 2.
- Promote a different version while the pod runs: does the running pod change, and what picks up the change? Predicted: no, the change is picked up when a new pod starts. Actual: confirmed in the rollout test below. Related observation: `prod` was on v2 at that moment (I had moved it back by hand in Step 4), and the new pod resolved v2.
- Memory of the serving pod (one worker)? Predicted: about 900Mi, roughly 300 Mi per worker. Actual: 454Mi (`kubectl top pod`; at the same time mlflow 666Mi, postgres 76Mi). Too high a guess: per heavy process it is about 225Mi, not 300.
- Will the Host header check allow the model fetch from `mlflow:5000`? Predicted: yes. Actual: yes. No 403 in the serving log; the model downloaded from `mlflow:5000` and Uvicorn started.

**Baseline latency** (`app/smoke.py -n 200` through `kubectl port-forward svc/serving 5001:5001`): p50 15.9 ms, p95 17.5 ms, p99 25.5 ms (mean 16.1 ms). This overstates in-cluster latency: the same script against a local server gave about 5 ms, so `kubectl port-forward` adds roughly 10 ms. Redo from a pod inside the cluster before using it as the SLO baseline.

**What went wrong**: nothing failed; the first `kubectl apply` came up Ready.

**Lessons**

1. Memory is roughly the number of heavy Python processes times about 225Mi each: mlflow 666Mi / 3 processes (parent + 2 workers), serving 454Mi / 2 (parent + 1 worker). The model itself is a few MB, so the imported libraries dominate; for an LLM the weights would dominate instead. (The process count for serving is my expectation, not yet checked with the `/proc` listing.)
2. `kubectl port-forward` is not a valid latency baseline: it tunnels through the API server and adds latency.
3. The pod serves the version `prod` pointed to when it started (v2), and the log line `resolved propensity-model@prod -> v2` records it.
4. `mlflow` (3 restarts) and `postgres-0` (4 restarts) both show their last restart about 8 hours ago, at the same time. Probably a host event (sleep, reboot or k3s restart); not confirmed. Both recovered on their own, and Postgres kept its data.

**Open questions for the reference architecture doc**

- The alias is resolved only when a pod starts, so rolling out a new `prod` needs a restart, and a pod that crashes and restarts can silently pick up a newer version. Alternatives: pin the version number in the manifest and promote by changing it in Git (GitOps), or a serving layer such as KServe that watches the registry.
- `pip install` at container start makes every restart slow and depends on the network; a real setup builds an image once and pushes it to a registry.
- One replica means no redundancy: a rollout is the only time two pods exist.

**To verify next (done, see Rollout test)**: promote a version, run `kubectl -n ml-platform rollout restart deploy/serving`, and check there are no failed requests during the rollout. Test it with a request loop run from a pod inside the cluster against `http://serving:5001/ping`, not through `kubectl port-forward`, which attaches to one pod and breaks when that pod is replaced.

**Done**: the serving pod is Ready (50 s), serves `prod` (v2) behind the `serving` Service, and returns predictions. The rollout test passed (see below).

**Rollout test** (2026-11-06)

Setup: a `loadgen` pod ran a request loop against `http://serving:5001` from inside the cluster, printing success and failure counters. Then I moved `prod` to v4 (roc_auc 0.9676) and ran `kubectl rollout restart deploy/serving`.

Predictions vs results (all four correct):

- The running pod keeps serving its old version until it is replaced. Correct.
- A new pod resolves `prod` at start and serves the new version. Correct (v4).
- The old pod stays until the new pod is Ready (`maxUnavailable: 0`), so no requests fail. Correct: **0 failures in 1,100+ requests**.
- The new pod takes about as long as the first start. Correct: **50 s from creation to Ready**.

Rollback: set `prod` back to v2, then `time (kubectl rollout restart ... && kubectl rollout status ...)`. Result: **51.0 s** total. The pod log shows `resolved propensity-model@prod -> v2`, and `show_registry.py` shows `prod` on v2 and `candidate` still on v4. Rolling back is two steps: move the alias, restart the pods. It takes about a minute, so it is not instant.

Timeline from `kubectl get events` (rollback rollout): new pod started at T; startup probe failed (`connection refused`) at T+40 s because `pip install` was still running; old pod killed at T+50 s. The old pod is only stopped after the new one passes its probe.

Lessons:

1. `kubectl logs -l <selector>` shows only the last 10 lines per pod unless `--tail=-1` is set. My first `grep resolved` came back empty for that reason, not because the line was missing.
2. A `connection refused` startup-probe warning during startup is normal; the startup probe tolerates up to 300 s of them.
3. Zero-downtime depends on the old pod staying until the new one is Ready. With a single replica, a rollout is the only time two pods exist.

Open questions:

- The old pod ended in status `Error` (non-zero exit) after SIGTERM instead of `Completed`. Is `mlflow models serve` exiting with a non-zero code on shutdown? Check `kubectl describe pod` Last State and the exit code on the next rollout.
- Graceful shutdown under higher load: would in-flight requests be dropped when the old pod stops? Test with a faster loop and a `preStop` sleep.
- Where do the 50 s go: `pip install`, model download, or server start? Add timestamps to the startup log.

**Done**: promote, restart and rollback all work through the alias. Step 5 is complete.

<!-- New entries go ABOVE this line, newest last. Keep it chronological. -->
