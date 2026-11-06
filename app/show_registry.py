"""Print every version of the model with its aliases and roc_auc.

Usage:  uv run python app/show_registry.py

Reads MLFLOW_TRACKING_URI. A fresh shell may not have it set, in which case MLflow
silently uses a local database, so this script prints the URI it is reading from.
"""

import mlflow
from common import MODEL_NAME, TRACKING_URI
from mlflow import MlflowClient


def main() -> None:
    mlflow.set_tracking_uri(TRACKING_URI)
    client = MlflowClient()
    print(f"tracking uri: {TRACKING_URI}")

    # search_model_versions() does not fill in aliases; the registered model has the map.
    alias_map = client.get_registered_model(MODEL_NAME).aliases  # {"prod": "2", ...}
    versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    for v in sorted(versions, key=lambda v: int(v.version)):
        aliases = sorted(a for a, ver in alias_map.items() if ver == v.version)
        auc = client.get_run(v.run_id).data.metrics.get("roc_auc")
        print(f"v{v.version}  aliases={aliases}  roc_auc={auc:.4f}")


if __name__ == "__main__":
    main()
