FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m serving

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY platform_serving ./platform_serving

USER serving

EXPOSE 8000

CMD ["uvicorn", "platform_serving.main:app", "--host", "0.0.0.0", "--port", "8000"]
