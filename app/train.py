"""Train a small classifier, log it to MLflow, register it, and tag the new version `candidate`.

Usage:  uv run python app/train.py [--n-estimators 100] [--max-depth 6] [--seed 0]
Run it twice with different hyperparameters to get two registered versions.
"""
import argparse

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from common import EXPERIMENT, MODEL_NAME, TRACKING_URI


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-estimators", type=int, default=100)
    ap.add_argument("--max-depth", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)

    # Synthetic stand-in for "will this customer accept an offer" propensity.
    X, y = make_classification(n_samples=5000, n_features=12, n_informative=6, random_state=42)
    X = pd.DataFrame(X, columns=[f"f{i}" for i in range(X.shape[1])])
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    params = {"n_estimators": args.n_estimators, "max_depth": args.max_depth, "random_state": args.seed}
    with mlflow.start_run() as run:
        model = RandomForestClassifier(**params).fit(X_tr, y_tr)
        auc = roc_auc_score(y_te, model.predict_proba(X_te)[:, 1])
        mlflow.log_params(params)
        mlflow.log_metric("roc_auc", auc)
        mlflow.sklearn.log_model(
            model,
            name="model",
            signature=infer_signature(X_te, model.predict(X_te)),
            input_example=X_te.head(3),
            # MLflow >= 3.x saves sklearn models with skops, which refuses unknown types on load.
            # We trained this model ourselves, so trusting the tree node type is appropriate.
            skops_trusted_types=["sklearn.tree._tree.Tree"],
        )
        run_id = run.info.run_id

    client = MlflowClient()
    mv = mlflow.register_model(f"runs:/{run_id}/model", MODEL_NAME)
    client.set_registered_model_alias(MODEL_NAME, "candidate", mv.version)
    print(f"run={run_id} version={mv.version} roc_auc={auc:.4f} -> alias 'candidate'")


if __name__ == "__main__":
    main()
