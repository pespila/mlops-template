FROM python:3.11-slim

# psycopg2-binary is what MLflow's SQLAlchemy models were designed against;
# psycopg3 causes experiment_id type-cast mismatches on create_run.
RUN pip install --no-cache-dir \
    "mlflow==2.17.0" \
    "psycopg2-binary==2.9.9" \
    "boto3==1.35.0"

EXPOSE 5000
