FROM python:3.12-slim

RUN pip install --no-cache-dir "mlflow[auth]==3.17.2" psycopg2-binary boto3

EXPOSE 5000
# Configuração de autenticação montada pelo docker-compose
ENV MLFLOW_AUTH_CONFIG_PATH=/etc/mlflow/basic_auth.ini

CMD ["sh", "-c", "mlflow server --app-name basic-auth \
  --backend-store-uri postgresql://mlflow:mlflow@postgres:5432/mlflow \
  --artifacts-destination s3://mlflow-artefatos \
  --host 0.0.0.0 --port 5000"]
