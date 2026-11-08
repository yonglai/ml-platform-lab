# Roadmap: from thin slice to a full MLOps portfolio project

Goal: cover the main points of a Senior ML Systems Engineer posting (platform, pipelines, CI/CD for models, registry, feature store, observability, security, cloud, Docker/Kubernetes, Java) with measured evidence, and publish a few posts. Status of the lab: Steps 0-7 done (see README); Step 8, the reference architecture doc, is next.

## Coverage map

| Requirement | Covered today | Gap | Close it with |
|---|---|---|---|
| Reusable platform capabilities | Reference doc skeleton | One model hard-coded | Parameterized "serve a model" Helm chart or kustomize base; onboard a second model |
| Data and ML pipelines | CI scripts only | No orchestrated pipeline | Kubeflow Pipelines on k3s: prep, train, evaluate, register, promote |
| CI/CD for models, registry, tracking | Done | None | Add image build and scan to CI |
| Feature store | None | Gap | Feast with Postgres or sqlite online store |
| Observability, alerting | Latency, errors, restarts, SLO | No drift or model-quality monitoring | Drift metric in Prometheus (Evidently or PSI) |
| Automated remediation | Kubernetes restarts | No SLO-driven action | Auto-rollback: SLO breach after promotion moves the alias back |
| Authentication, RBAC, audit, compliance | RBAC, audit log, NetworkPolicy | MLflow has no login; no compliance scan | MLflow auth; Trivy in CI; Kyverno policies; MFA note (identity provider) |
| Secure communication | Internal Services only | No TLS; secrets in git | Traefik ingress with TLS (cert-manager); sealed or external secrets |
| Cost, performance, scale | Latency measured | No autoscaling or cost figure | HPA + load test; cost per 1,000 predictions; right-sizing |
| Python and Java | Python | No Java | Small Java client or gateway (Spring Boot or Quarkus, Micrometer) |
| MLflow, Kubeflow, Ray, serving frameworks | MLflow, `mlflow models serve` | Kubeflow, Ray, KServe | Kubeflow Pipelines; Ray Serve vs `mlflow models serve` |
| Cloud (Azure first, then AWS, GCP) | k3s only | Azure | Azure ML workspace as MLflow tracking server and registry; short managed endpoint test then delete; mapping table |
| Docker and Kubernetes optimization | Kubernetes covered | `pip install` at pod start | Multi-stage image from `uv.lock`, non-root, scanned, pushed to ghcr.io; compare start time (50 s today) |
| Azure ML, Databricks serverless (preferred) | None | Gap | Azure ML as above; Databricks Free Edition (check availability) |
| LLM serving (preferred) | Separate `inference-track` repo | Not linked | Link it; one reference-doc section on LLM serving |

## Plan (about 45 hours)

| Phase | Items | Hours |
|---|---|---|
| 1 | Step 8 reference doc (with compliance section); real image + CI build + Trivy; MLflow auth; TLS ingress | 10 |
| 2 | Kubeflow Pipelines training pipeline; Feast | 10 |
| 3 | Azure ML (tracking, registry, short endpoint); Databricks Free Edition | 8 |
| 4 | Drift monitor + auto-rollback; HPA + load test + cost per 1,000 predictions; Java client | 12 |
| 5 | Ray Serve comparison; Kyverno | 7 |

Rules: prediction first, then a measurement, then a LOG.md entry. Depth over breadth; cut Phase 5 before the reference doc. Azure items use free tiers or a short endpoint that is deleted afterwards.

## Posts (each tied to a measurement)

1. After Phase 1: "I built an ML platform on one machine and measured it" (gate, 51 s rollback, SLO, a 6-minute outage costs 5.7% of the monthly budget).
2. "Where do the 17 ms go?" (model 11 ms vs everything else; fewer trees, batching, runtime).
3. After Phases 2-3: "The same model on MLflow, Azure ML and Databricks".
4. After Phase 4: "Auto-rollback for ML models: SLO breach to alias flip in N seconds".
