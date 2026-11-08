# ML Platform Reference Architecture (draft)

*Replace every italic prompt with your own text. Aim for 2 pages. Write it as if the audience is engineering leadership who must approve a multi-quarter roadmap.*

## 1. Context and goals
*Draft: rewrite each sentence in your own words.*

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
*Paste the diagram from README and explain the path of one model from training to production traffic.*

## 3. Components and build-vs-buy
| Capability | What this lab uses | Managed alternative | Why this choice | When I would switch |
|---|---|---|---|---|
| Experiment tracking + registry | MLflow | SageMaker / Azure ML / Databricks | *...* | *...* |
| Serving | plain Deployment + `mlflow models serve` | KServe, SageMaker endpoints, vLLM for LLMs | *...* | *...* |
| Orchestration | scripts / GitHub Actions | Kubeflow Pipelines, Argo Workflows, Airflow, Step Functions | *...* | *...* |
| Feature store | none (out of scope) | Feast, SageMaker Feature Store, Databricks | *...* | *...* |
| Distributed compute | none | Ray, Spark/Databricks | *...* | *...* |
| Artifact store | PVC | S3 / Blob (via `--serve-artifacts`) | *...* | *...* |

## 4. Standards
*Model naming, alias semantics (`candidate`, `prod`), who may promote, required metadata (metrics, data version, owner), rollback procedure, versioning of the platform itself.*

## 5. Reliability and observability
*Draft from Step 6: edit this in your own words.*

**What is measured.** `mlflow models serve` exposes no request metrics, so an in-cluster prober (`app/prober.py`) sends one prediction request per second to the `serving` Service and records latency and success. Prometheus scrapes it; Grafana shows it (`k8s/dashboards/ml-platform.json`).

**Service level objectives** (over 30 days, counting only time the platform is running):

| SLI (what is measured) | Objective |
|---|---|
| Availability: requests answered with HTTP 200 / all requests | 99.5% |
| Latency: successful requests answered in 50 ms or less / all successful requests | 99% (the same as p99 under 50 ms) |

**Error budget.** At one request per second for 12 hours a day, 30 days is about 1.3 million requests. The availability budget (0.5%) is about 6,500 failed requests, equal to about 108 minutes of complete outage. The latency budget (1%) is about 13,000 requests slower than 50 ms. A one-minute p99 spike uses a few dozen requests, a tiny part of that.

**Evidence for the targets.** In-cluster p50 about 17.5 ms and p99 at most 20 ms (limited by histogram buckets); worst minute seen about 78 ms; 0 failed requests during a rolling update (the old pod stays until the new one is Ready); about 11 ms of the 17.5 ms is the model itself.

**Alert.** `ServingUnavailable`: no serving pod Ready for 2 minutes. Alertmanager is not installed, so today it only shows on the Prometheus Alerts page.

**Not observable today.** Real client traffic (the prober is synthetic and sends one fixed row), latency per model version, errors inside the server, and the host being off at night (the lab machine is shut down every night, so these numbers cover running time only). Plan: an inference server with native metrics (KServe or Triton), or a small proxy in front of the model, plus Alertmanager and a burn-rate alert on the budget above.

## 6. Security
*Authn/authz (RBAC roles and what they allow), secrets handling, network isolation, audit logging, PHI/PII considerations if the platform serves healthcare data (HIPAA/PHIPA) and what controls that implies.*

## 7. Cost
*What costs money at scale: GPU idle time, storage, egress. Two levers you would pull first.*

## 8. Roadmap
*Quarter by quarter: Q1 ..., Q2 ..., Q3 .... Tie each to a product or business outcome and to a team that must adopt it.*

## 9. Risks and open questions
*Top 3 risks and how you would find out early.*
