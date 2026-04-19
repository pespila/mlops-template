-- Bootstraps additional databases used by the platform.
-- The main POSTGRES_DB is created by the official postgres image itself.

CREATE DATABASE mlflow;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO platform;
