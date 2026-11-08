# ML Platform Reference Architecture

Audience: engineering leadership deciding on a multi-quarter roadmap for an ML platform. Evidence for every number is in `LOG.md`; a working thin slice of everything below runs in this repo on a single k3s node.

## 1. Context and goals

**Users.** Data scientists and ML engineers who train and register models; product and engineering teams who call predictions from their applications; and the engineer on call who keeps it running. What they share: they need to ship a model change without breaking the product, know what is running, and undo a change quickly.

**Why a platform.** Without one, a model reaches production by hand: nobody can say which version is serving, a bad model is hard to roll back, and nobody can show who changed what. In healthcare software, where predictions feed clinical and operational decisions, each of those is a safety and audit problem, not just an outage.

**Goals: what users can count on**
1. **Predictions are fast.** Objective: p99 under 50 ms. Measured from inside the cluster: p50 about 17.5 ms, p99 at most 20 ms; the model itself is about 11 ms of that.
2. **A release or a rollback does not drop requests.** 0 failed requests out of 1,100+ during a rolling update, because the old pod stays until the new one is Ready; a rollback (move the alias, restart) takes 51 s.
3. **Failures are caught and bounded.** An alert fires about 2 minutes after serving goes down; one 6-minute outage cost 372 failed requests, 5.7% of the monthly error budget.

**Non-goals (for now)**
1. **Multi-node high availability.** One node, and planned downtime is accepted (the host is shut down nightly); outages are measured against the error budget instead of prevented.
2. **Building the models.** The platform ships, serves and watches models; model quality belongs to the data scientists. The small synthetic model here only exercises the platform.
3. **Cloud parity.** The lab runs on k3s. Managed options (Azure ML and others) are compared in section 3 and tried in a later phase, not rebuilt.

**Not covered yet, and said plainly:** monitoring of model quality and data drift (planned), a feature store, and compliance controls beyond access control, network isolation and audit logging.

## 2. Architecture

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
                           │  Prober ─▶ Prometheus ─▶ Grafana (SLO, 1 alert)    │
                           │  RBAC: ml-reader / ml-deployer; NetworkPolicy      │
                           └────────────────────────────────────────────────────┘
```

**The path of one model, from training to production traffic**
1. `train.py` trains a model, logs its parameters, its metric (ROC AUC), its input signature and an example, and the exact library versions (from `uv.lock`), then registers it in MLflow as a new version with the alias `candidate`.
2. `promote.py` is the gate. It compares the candidate's ROC AUC with the model currently aliased `prod`. If the candidate is not at least as good (plus a minimum gain), it prints `REJECTED` and exits with code 1, which fails the CI job. Otherwise it moves the alias `prod` to the candidate. CI also has a test that a deliberately worse model is rejected.
3. The `serving` Deployment looks up which version `prod` points to **once, at pod start**, logs `resolved propensity-model@prod -> vN`, and serves that fixed version. A running pod never switches by itself.
4. Rolling out a promoted model is `kubectl rollout restart deploy/serving`. The old pod keeps answering until the new one passes its readiness check, so no requests fail.
5. A prober inside the cluster sends one request per second to the Service. Prometheus scrapes it (plus pod metrics and Kubernetes state); Grafana shows latency, errors, restarts and memory; an alert fires when no serving pod is available for 2 minutes.
6. **Rollback** is the same path in reverse: move `prod` back to the previous version and restart serving (51 s measured).

## 3. Components and build-vs-buy

| Capability | What this lab uses | Managed alternative | Why this choice | When I would switch |
|---|---|---|---|---|
| Experiment tracking + registry | MLflow on Postgres | SageMaker / Azure ML / Databricks | Open source, one API for tracking and registry; aliases give promote and rollback without code changes; runs anywhere. Azure ML and Databricks both accept MLflow tracking, so code and models move with little change. | When the company already standardizes on a cloud (for example Azure ML), or when per-model access control, lineage and governance matter more than running Postgres and storage ourselves. |
| Serving | plain Deployment + `mlflow models serve` | KServe, SageMaker or Azure ML endpoints, vLLM for LLMs | The simplest thing that serves a registered model; every moving part is visible. Known limits: no request metrics of its own, one process, 50 s start because dependencies install at start. | With more than a few models, or when autoscaling, canary releases, batching, GPUs or request-level metrics are needed. |
| Orchestration | scripts / GitHub Actions | Kubeflow Pipelines, Argo Workflows, Airflow, Step Functions | Enough for one small model trained in CI. | When training needs data preparation, retries, schedules or many teams' pipelines. |
| Feature store | none (out of scope) | Feast, SageMaker Feature Store, Databricks | One synthetic model with no shared features. | When two or more models share features, or training and serving features drift apart. |
| Distributed compute | none | Ray, Spark/Databricks | The model trains in seconds on one CPU. | When data no longer fits on one node or training takes hours. |
| Artifact store | PVC | S3 / Blob (via `--serve-artifacts`) | A 5 Gi volume on one node is simple; `--serve-artifacts` means clients never touch the volume, so the store can change underneath them. | Before a second node or any production use: object storage for durability, versioning and access from any node. |

## 4. Standards

- **Model naming:** one registered model per use case, named for the use case (`propensity-model`). A new training run creates a new version; versions are never edited.
- **Aliases:** `candidate` is the newest version, set by training. `prod` is what serving runs, moved only by the promotion gate or by a person rolling back. Applications and manifests refer to aliases, never to version numbers.
- **Who may promote:** the CI gate, on measured improvement. A person with the `ml-deployer` role restarts serving to pick up a new `prod`; `ml-reader` can only look.
- **Required metadata on every version:** parameters, the evaluation metric, the input signature and an example, and the pinned library list. Not yet required, and should be: the data version used for training and an owner.
- **Rollback procedure:** move `prod` to the previous version, restart serving, confirm the `resolved ... -> vN` line in the pod log. Measured at 51 s.
- **Versioning the platform:** all manifests, dashboards and alert rules live in git. Library versions are pinned. Planned: build a container image from the lockfile and tag it, so two pods started on different days run the same code.

## 5. Reliability and observability

**What is measured.** `mlflow models serve` exposes no request metrics, so an in-cluster prober (`app/prober.py`) sends one prediction request per second to the `serving` Service and records latency and success. Prometheus scrapes it; Grafana shows it (`k8s/dashboards/ml-platform.json`).

**Service level objectives** (over 30 days, counting only time the platform is running):

| SLI (what is measured) | Objective |
|---|---|
| Availability: requests answered with HTTP 200 / all requests | 99.5% |
| Latency: successful requests answered in 50 ms or less / all successful requests | 99% (the same as p99 under 50 ms) |

**Error budget.** At one request per second for 12 hours a day, 30 days is about 1.3 million requests. The availability budget (0.5%) is about 6,500 failed requests, equal to about 108 minutes of complete outage. The latency budget (1%) is about 13,000 requests slower than 50 ms. A one-minute p99 spike uses a few dozen requests, a tiny part of that.

**Evidence for the targets.** In-cluster p50 about 17.5 ms and p99 at most 20 ms (limited by histogram buckets); worst minute seen about 78 ms; 0 failed requests during a rolling update (the old pod stays until the new one is Ready); about 11 ms of the 17.5 ms is the model itself. One deliberate outage (scale to zero) was detected by the alert in about 2 minutes and used 5.7% of the monthly budget.

**Alert.** `ServingUnavailable`: no serving pod Ready for 2 minutes. Alertmanager is not installed, so today it only shows on the Prometheus Alerts page.

**Not observable today.** Real client traffic (the prober is synthetic and sends one fixed row), latency per model version, errors inside the server, model quality and data drift, and the host being off at night (the numbers cover running time only). Also not covered: an alert on slow budget burn (for example 10% of requests failing for an hour would not trigger the current alert) and automated remediation beyond Kubernetes restarting pods. Plan: an inference server with native metrics (KServe or similar) or a small proxy in front of the model, Alertmanager, a burn-rate alert, a drift metric, and an automatic rollback when the objective is breached after a promotion.

## 6. Security

**What exists and was tested**
- **Authorization:** two ServiceAccounts in the namespace, `ml-reader` (get, list and watch pods, services and deployments) and `ml-deployer` (the same, plus patch and update deployments). Tested with `kubectl auth can-i`: reader cannot delete or patch, deployer cannot delete pods or read Secrets, neither can read pods in another namespace. Reading logs is a separate permission (`pods/log`) and is not granted to the reader. A refusal returns 403 Forbidden.
- **Network isolation:** a NetworkPolicy lets only MLflow pods reach Postgres on port 5432; the prober and any other pod are refused immediately. Verified from both sides (blocked and allowed).
- **Audit logging:** the Kubernetes API server records who did what. Secrets are logged at metadata level, so the log shows who read a Secret but never its content (the password text appears 0 times in the log). Impersonated requests record both identities. Logs rotate (7 days, 3 files, 50 MB).

**Known gaps (said plainly)**
- The MLflow server has **no authentication**; anyone who can reach it can register or promote models.
- No TLS between components; traffic inside the cluster is plain HTTP.
- Secrets are only base64 in the cluster, and the lab password is in a manifest in git. A real setup would use a secrets manager (Vault or a cloud one) with the External Secrets Operator, or sealed secrets, plus encryption at rest.
- The cluster administrator account (`system:admin`) bypasses RBAC entirely; the audit log is the only control over it, and it sits on the same machine it protects. Real setups ship audit logs off the host.
- No multi-factor authentication (it belongs to the identity provider, for example Entra ID or Okta, in front of the cluster and MLflow) and no compliance scanning (image scanning, policy-as-code).

**If the platform serves healthcare data (HIPAA in the US, PHIPA in Ontario)** this implies, at least: encryption in transit and at rest; authentication on every component and least-privilege access (the first steps exist); an audit trail of access that is retained and protected; no patient data in logs, metric labels or experiment artifacts (note that MLflow stores an input example with every model, which must be synthetic or de-identified); data residency in the required region; agreements with any cloud or SaaS vendor that touches the data; and a defined process for incidents. Most of these are not built here; the point of this section is the list, not a claim of compliance.

## 7. Cost

**What costs money at scale:** idle GPU time (the largest line for LLM serving), storage that is never cleaned up (artifacts and logs), data movement between regions and out of the cloud, and one pod per model each holding its own memory. In the lab, measured memory: MLflow 657 MiB, serving 464 MiB, Prometheus + Grafana about 625 MiB together; monitoring costs as much memory as the registry.

**Two levers to pull first**
1. **Right-size from measurements.** Requests and limits should come from Prometheus data, not guesses (the MLflow memory limit started too low and was OOM-killed, then was raised after measuring). Compare requested versus used per pod and reclaim the difference.
2. **Share and scale to demand.** Run several low-traffic models in one serving process, or scale idle ones to zero, instead of one always-on pod per model. For GPU workloads, utilization and batching matter more than any other setting.

Not computed yet: cost per 1,000 predictions (planned: CPU and memory seconds times the cloud unit price, divided by requests).

## 8. Roadmap

| Quarter | Outcome | Work | Who must adopt it |
|---|---|---|---|
| Q1 | A model can go to production safely, by anyone on the first two teams | Container image built from the lockfile with an image scan in CI; authentication and TLS on MLflow; a reusable "serve a model" chart so a second model onboards in minutes; reference doc reviewed | The first two product teams' ML engineers; security review |
| Q2 | Models are trained and watched without hand-run scripts | Pipeline orchestration (Kubeflow Pipelines) for train, evaluate, register, promote; feature store pilot; drift monitoring; automatic rollback when the objective is breached after a promotion | Data science teams; on-call engineers |
| Q3 | The platform meets enterprise requirements and shows its cost | Azure ML (or the company's cloud) as a registry and endpoint option; autoscaling and cost per 1,000 predictions; audit logs shipped off the host; a secrets manager; policy-as-code | Security and compliance; finance and operations |

## 9. Risks and open questions

1. **A model degrades or changes silently.** Today the platform sees outages, not wrong answers. How to find out early: add a drift metric on input features and prediction distribution, compare it with the training data, and alert on it; run the promotion gate on fresh data, not only the training split.
2. **Sensitive data or credentials leak.** MLflow has no login, secrets are in git, and every model stores an input example. How to find out early: review what lands in artifacts, logs and metric labels; scan the repo and images for secrets in CI; put authentication in front of MLflow before any real data touches it.
3. **The platform itself is a single point of failure and not fully reproducible.** One replica on one node, and each pod installs its libraries at start (slow and slightly different on different days; MLflow already warned about version mismatches). How to find out early: run two replicas and kill one on purpose; build the image from the lockfile and compare start time and library lists.
