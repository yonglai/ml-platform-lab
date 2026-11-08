# ml-platform-lab

A thin-slice ML platform on a single-node k3s cluster, built to practice the pieces a Principal ML Platform Engineer is expected to own: model registry, gated promotion (CI/CD for models), serving, observability/SLOs, and access control. Not a product; a lab with receipts.

```
                  ┌────────── GitHub Actions (model-ci) ──────────┐
                  │ train → register(candidate) → promote gate     │
                  └───────────────────────┬────────────────────────┘
                                          │ same scripts, run by hand against the cluster
 laptop ── port-forward ─▶ ┌──────────── k3s, namespace ml-platform ────────────┐
                           │  MLflow server ──▶ Postgres (metadata)             │
                           │       │  └──────▶ PVC (artifacts)                  │
                           │       ▼ alias `prod`                               │
                           │  Serving Deployment  ◀── rollout restart on promote│
                           │  Prometheus ─▶ Grafana (SLO dashboard, 1 alert)    │
                           │  RBAC: ml-reader / ml-deployer                     │
                           └────────────────────────────────────────────────────┘
```

## Status
| Step | What | State |
|---|---|---|
| 0 | Pre-flight checks | done |
| 1 | Namespace + Postgres | done |
| 2 | MLflow server | done |
| 3 | Train + register against cluster | done |
| 4 | Promotion gate + model CI | done (gate rejects a worse model; CI check committed) |
| 5 | Serving from `@prod` | done (rolling update and rollback tested, 0 failed requests) |
| 6 | Prometheus + Grafana + SLO | done (prober, dashboard, SLO draft, alert tested) |
| 7 | RBAC, NetworkPolicy, API audit log | done (roles tested, Postgres locked to mlflow, audit records verified) |
| 8 | Reference architecture doc | first full draft in `docs/reference-architecture.md` (to be reviewed and edited) |

The hour-by-hour plan is in [PLAN.md](PLAN.md). The lab notebook is [LOG.md](LOG.md).

## Run the scripts with no cluster
```bash
uv sync
uv run python app/train.py --n-estimators 50 --max-depth 4
uv run python app/promote.py          # first model becomes prod
uv run python app/train.py --n-estimators 200 --max-depth 8
uv run python app/promote.py          # promoted only if roc_auc is higher; exit 1 otherwise
```
Against the cluster, set `MLFLOW_TRACKING_URI=http://localhost:5000` while `kubectl port-forward` is running.

## Inspect the registry
```bash
export MLFLOW_TRACKING_URI=http://localhost:5000   # per shell; unset means a silent local database
uv run python app/show_registry.py                 # versions, aliases, roc_auc
```
