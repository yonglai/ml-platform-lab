"""Promotion gate: move alias `candidate` -> `prod` only if it beats the current prod on roc_auc.

Exit code 0 = promoted (or nothing to do), 1 = rejected. CI uses the exit code.
Usage:  uv run python app/promote.py [--min-gain 0.0]
"""

import argparse
import sys

import mlflow
from common import MODEL_NAME, TRACKING_URI
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

METRIC = "roc_auc"


def auc_of(client: MlflowClient, version) -> float:
    return client.get_run(version.run_id).data.metrics[METRIC]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--min-gain",
        type=float,
        default=0.0,
        help="required roc_auc improvement over prod",
    )
    args = ap.parse_args()

    mlflow.set_tracking_uri(TRACKING_URI)
    client = MlflowClient()

    try:
        cand = client.get_model_version_by_alias(MODEL_NAME, "candidate")
    except MlflowException:
        print("no 'candidate' alias; nothing to promote")
        return 1
    cand_auc = auc_of(client, cand)

    try:
        prod = client.get_model_version_by_alias(MODEL_NAME, "prod")
        prod_auc = auc_of(client, prod)
    except MlflowException:
        prod = None
        prod_auc = None

    if prod is None:
        print(f"no prod yet: promoting v{cand.version} (roc_auc={cand_auc:.4f})")
    elif cand_auc >= prod_auc + args.min_gain:
        print(
            f"promoting v{cand.version} ({cand_auc:.4f}) over prod v{prod.version} ({prod_auc:.4f})"
        )
    else:
        print(
            f"REJECTED: v{cand.version} ({cand_auc:.4f}) does not beat prod v{prod.version} ({prod_auc:.4f}) by {args.min_gain}"
        )
        return 1

    client.set_registered_model_alias(MODEL_NAME, "prod", cand.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
