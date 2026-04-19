"""AutoGluon zero-config adapter.

The user selects "AutoGluon" in the UI and provides only an optional time_limit
and presets. This adapter:

    1. Loads the dataset from MinIO.
    2. Applies the user's TransformConfig (or runs AutoGluon's own feature
       engineering when TransformConfig is empty).
    3. Fits a TabularPredictor across the full family of AutoGluon models.
    4. Logs every model in the leaderboard as nested MLflow runs.
    5. Promotes the winning ensemble as the registered ModelVersion.

Real implementation lands in the next commit.
"""
