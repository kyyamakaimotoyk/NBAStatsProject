"""Public read-only API for the NBA predictions website.

This package is the *serve* half of the batch/serve split. It reads predictions
and accuracy from MySQL (RDS in prod) and returns JSON. It NEVER loads a model,
imports torch/sklearn, or runs inference — all of that happens in the batch
pipeline (modeling/batch_predict_today.py), which writes to model_predictions.

Keep this package's dependency surface tiny (see api/requirements.txt): fastapi,
uvicorn, sqlalchemy, pymysql, pydantic. That keeps the Docker image small and
cold-starts fast.
"""
