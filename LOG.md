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

<!-- New entries go ABOVE this line, newest last. Keep it chronological. -->
