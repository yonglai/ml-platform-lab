# ML Platform Reference Architecture (draft)

*Replace every italic prompt with your own text. Aim for 2 pages. Write it as if the audience is engineering leadership who must approve a multi-quarter roadmap.*

## 1. Context and goals
*Who are the users (data scientists, app teams)? What must the platform guarantee? Three bullet goals, three non-goals.*

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
