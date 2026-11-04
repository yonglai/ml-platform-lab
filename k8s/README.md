# k8s manifests

Hand-write these (same approach as `inference-track/vllm-k8s`). Suggested files, in order:

- `00-namespace.yaml` (done)
- `10-postgres.yaml`: Secret, StatefulSet (volumeClaimTemplates), Service
- `20-mlflow.yaml`: PVC (artifacts), Deployment, Service
- `30-serving.yaml`: Deployment + Service for `propensity-model@prod`
- `40-monitoring/`: Prometheus + Grafana
- `50-rbac.yaml`: ServiceAccounts, Roles, RoleBindings
