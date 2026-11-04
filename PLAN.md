# Weekend plan: Saturday = registry + promotion, Sunday = serving + operations

Method (same as the vLLM weeks): **write a prediction in LOG.md before every run**, hand-write the manifests, diff what happened against what you predicted. About 12 focused hours; expect Kubernetes debugging to eat 30-40% of it. If you fall behind, cut stretch items, not the reference doc (step 8).

## Step 0: Pre-flight (do this before Saturday, 20 min, on the Alienware)
- [ ] `kubectl get nodes` shows Ready; `kubectl get sc` shows `local-path` as default
- [ ] `helm version` works (needed for Grafana/Prometheus)
- [ ] `docker pull python:3.12-slim` and `docker pull postgres:16` succeed
- [ ] `uv sync` in this repo, then run the no-cluster commands in README to confirm the scripts work on that machine
- [ ] Stop the vLLM pod if it is holding GPU/RAM you need: `kubectl -n vllm scale deploy/vllm-qwen --replicas=0` (this project is CPU-only)
- [ ] Artifact store decision: **PVC, not MinIO.** MLflow's `--serve-artifacts` proxies uploads over HTTP, so clients never mount the volume. Upgrade path to S3 goes in the reference doc.

## Saturday

### Step 1: Namespace + Postgres (45 min)
Write `k8s/10-postgres.yaml`: Secret (user/password/db), StatefulSet with `volumeClaimTemplates`, headless or ClusterIP Service.
- **Predict:** if you delete the Postgres pod, is the data still there? Why does a StatefulSet matter here, versus a Deployment with a PVC?
- **Done when:** `kubectl -n ml-platform exec -it postgres-0 -- psql -U mlflow -c '\l'` lists the DB, and the data survives `kubectl delete pod postgres-0`.

### Step 2: MLflow server (90 min)
Write `k8s/20-mlflow.yaml`: PVC for artifacts, Deployment, Service (port 5000), readiness/liveness on `/health`.
Server command shape:
`mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri postgresql://USER:PASS@postgres:5432/DB --serve-artifacts --artifacts-destination /mlartifacts`
- **Traps to predict first:** (a) the stock `ghcr.io/mlflow/mlflow` image may not include the Postgres driver (`psycopg2-binary`); (b) newer MLflow versions can reject requests with an unrecognized Host header (look at `mlflow server --help` for allowed-hosts options if you see 403 "Invalid Host header" through the Service); (c) `local-path` volumes are owned by root, so check pod user permissions; (d) credentials from the Secret via `secretKeyRef`, not literals in the Deployment.
- **Done when:** `kubectl -n ml-platform port-forward svc/mlflow 5000:5000` and the UI loads at localhost:5000.

### Step 3: Train and register against the cluster (60 min)
```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
uv run python app/train.py --n-estimators 50 --max-depth 4
uv run python app/train.py --n-estimators 200 --max-depth 8
```
- **Predict:** where do the model files physically live, and how did your laptop upload them without mounting the PVC?
- **Done when:** two versions in the registry UI, `candidate` alias on v2, and `kubectl exec` into the MLflow pod shows the files under `/mlartifacts`. Delete the MLflow pod: do versions and artifacts survive?

### Step 4: Promotion gate and model CI (60 min)
- [ ] `uv run python app/promote.py` against the cluster: v2 becomes `prod`
- [ ] Train a deliberately worse model (`--n-estimators 3 --max-depth 2`), confirm the gate exits 1
- [ ] Push this repo to GitHub and watch `.github/workflows/model-ci.yml` pass (it uses a local sqlite MLflow, no cluster). Then add a failing case: what should CI do when the challenger is worse? Decide and write down why.
- **Interview point:** CI/CD for models = train → evaluate → register → gate → promote by alias, with the registry as the source of truth.

## Sunday

### Step 5: Serving from `@prod` (2.5 h)
Write `k8s/30-serving.yaml`: Deployment + Service. Start from `python:3.12-slim`, `pip install mlflow scikit-learn` at container start, then
`mlflow models serve -m models:/propensity-model@prod -h 0.0.0.0 -p 5001 --env-manager local` with `MLFLOW_TRACKING_URI=http://mlflow.ml-platform.svc:5000`.
- **Predict:** how long until Ready? You hit this with vLLM: you need a `startupProbe` (use `/ping`), then readiness. What happens to traffic during a rollout with no readiness probe?
- Strategy: `RollingUpdate` is fine here (CPU pod, unlike the single-GPU vLLM case). Check `maxUnavailable`.
- Deploy flow: promote new version → `kubectl -n ml-platform rollout restart deploy/serving` → new pod resolves `@prod` at startup. Discuss in the reference doc why this is simple but not ideal (restart-coupled; alternatives: pin the version number in a GitOps repo, KServe).
- **Done when:** `app/smoke.py --url http://localhost:5001` (via port-forward) prints p50/p95/p99, and after promoting a new version and restarting, the served version changes with zero failed requests (run smoke in a loop during the rollout).

### Step 6: Prometheus + Grafana + SLO (2 h)
Install with Helm (`prometheus-community/prometheus`, `grafana/grafana`) in a `monitoring` namespace with small resource requests; avoid the full kube-prometheus-stack on one node.
- Scrape pod CPU/memory/restarts (cAdvisor/kube-state-metrics) and anything MLflow exposes (check whether your MLflow version supports a Prometheus metrics flag).
- One dashboard: request latency from `smoke.py` runs written down as a baseline, pod readiness, restarts.
- Write the SLO in the reference doc: e.g. "p99 < 100 ms, 99.5% of requests succeed over 30 days", the error budget in minutes, and one alert rule (pod not ready for 2 min).
- **Honest scope:** `mlflow models serve` does not expose request-latency metrics; say so, and note what you would add (a sidecar or an inference server with native metrics) in the doc.

### Step 7: RBAC (90 min; audit log is stretch)
Write `k8s/50-rbac.yaml`: ServiceAccounts `ml-reader` (get/list/watch on pods, deployments, services) and `ml-deployer` (adds patch/update on deployments, create on rollouts) via Role + RoleBinding in `ml-platform`.
- **Verify:** `kubectl auth can-i delete pods -n ml-platform --as=system:serviceaccount:ml-platform:ml-reader` (expect no) and the same for `ml-deployer` on `patch deployments` (expect yes).
- **Stretch:** API server audit logging on k3s (audit policy file + apiserver args, then restart k3s). Note it in LOG.md either way.
- Also write down: Secrets handling, NetworkPolicy to restrict who reaches Postgres (k3s default flannel does not enforce NetworkPolicy unless the controller is enabled; check before claiming it works).

### Step 8: Reference architecture doc (2 h, do not skip)
Fill in `docs/reference-architecture.md`. This is the artifact that answers "define the reference architectures and standards," and the thing to walk through in an interview.

## Not in this weekend
Kubeflow, Ray, Feast, Java, Azure ML/Databricks. Write one paragraph each in the doc on when you would adopt them and why not here.
