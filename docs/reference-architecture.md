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
*SLO and error budget (numbers from smoke.py baseline). Alerts. What is NOT observable today (request metrics) and the plan.*

## 6. Security
*Authn/authz (RBAC roles and what they allow), secrets handling, network isolation, audit logging, PHI/PII considerations if the platform serves healthcare data (HIPAA/PHIPA) and what controls that implies.*

## 7. Cost
*What costs money at scale: GPU idle time, storage, egress. Two levers you would pull first.*

## 8. Roadmap
*Quarter by quarter: Q1 ..., Q2 ..., Q3 .... Tie each to a product or business outcome and to a team that must adopt it.*

## 9. Risks and open questions
*Top 3 risks and how you would find out early.*
