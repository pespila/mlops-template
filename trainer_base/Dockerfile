FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m trainer

WORKDIR /app

COPY pyproject.toml ./
# Install the base trainer plus the forecasting (sktime/statsmodels) and
# recommender (scikit-surprise/implicit) extras so every catalog family
# runs in this one image. AutoGluon remains a separate image (Dockerfile.autogluon)
# because its pinned xgboost/lightgbm collide with ours.
RUN pip install --upgrade pip && pip install '.[forecasting,recommender]'

COPY platform_trainer ./platform_trainer

USER trainer

ENTRYPOINT ["python", "-m", "platform_trainer"]
