"""Shared settings. Everything is overridable by environment variable."""

import os

MODEL_NAME = os.environ.get("MODEL_NAME", "propensity-model")
# In-cluster use: http://mlflow.ml-platform.svc:5000. From your laptop: kubectl port-forward, then http://localhost:5000.
# Default is a local sqlite file so the scripts and CI work with no cluster at all.
TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow-local.db")
EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT", "propensity-model")
