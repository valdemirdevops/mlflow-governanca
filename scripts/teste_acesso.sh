#!/usr/bin/env bash
# Teste de ponta a ponta do controle de acesso e do ciclo de mudança, contra um
# servidor MLflow REAL com basic-auth (SQLite, porta 5055). Usado no CI e localmente:
#
#   bash scripts/teste_acesso.sh
#
# Prova que: a conta de serviço treina, passa no gate e promove; a cientista de dados
# NÃO consegue mover o @champion; o auditor lê a evidência; o rollback funciona.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
PORTA=5055
export MLFLOW_DISABLE_AGENT_HINT=1 MLFLOW_HTTP_REQUEST_MAX_RETRIES=0
export MLFLOW_AUTH_CONFIG_PATH="$TMP/auth.ini" MLFLOW_FLASK_SERVER_SECRET_KEY="lab-$RANDOM"

cat > "$TMP/auth.ini" <<EOF
[mlflow]
default_permission = READ
database_uri = sqlite:///$TMP/auth.db
admin_username = admin
admin_password = Admin-lab-2026!
EOF

mlflow server --app-name basic-auth --backend-store-uri "sqlite:///$TMP/mlflow.db" \
  --artifacts-destination "$TMP/artefatos" --host 127.0.0.1 --port $PORTA \
  > "$TMP/server.log" 2>&1 &
SERVIDOR=$!
trap 'kill $SERVIDOR 2>/dev/null || true; rm -rf "$TMP"' EXIT

for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$PORTA/health" >/dev/null && break
  kill -0 $SERVIDOR 2>/dev/null || { cat "$TMP/server.log"; exit 1; }
  sleep 1
done
echo "Servidor MLflow com basic-auth no ar."

export MLFLOW_TRACKING_URI="http://127.0.0.1:$PORTA"
como() { MLFLOW_TRACKING_USERNAME="$1" MLFLOW_TRACKING_PASSWORD="$2" "${@:3}"; }
ADMIN=(admin 'Admin-lab-2026!'); SVC=(svc-mlflow-prod 'Svc-lab-2026!')
ANA=(ana-dados 'Ana-lab-2026!'); CARLOS=(carlos-auditoria 'Carlos-lab-2026!')
export MLFLOW_SENHA_SVC_MLFLOW_PROD="${SVC[1]}" MLFLOW_SENHA_ANA_DADOS="${ANA[1]}"
export MLFLOW_SENHA_MARIA_MUDANCAS='Maria-lab-2026!' MLFLOW_SENHA_CARLOS_AUDITORIA="${CARLOS[1]}"

# Contexto de CI simulado (o treino foi disparado por ana-dados)
export GITHUB_ACTIONS=true GITHUB_SERVER_URL=https://github.com GITHUB_REPOSITORY=exemplo/mlflow-governanca
export GITHUB_SHA=0a1b2c3d GITHUB_REF_NAME=main GITHUB_ACTOR=ana-dados

cd "$TMP"
echo "== 1. Admin aplica config/acessos.yml"
como "${ADMIN[@]}" python "$RAIZ/src/permissoes.py" --criar-usuarios

echo "== 2. Conta de serviço: treino v1 -> gate -> promoção"
export GITHUB_RUN_ID=1
como "${SVC[@]}" python "$RAIZ/src/train.py" --dados "$RAIZ/dados/unicorn-2026-09.csv" > /dev/null
como "${SVC[@]}" python "$RAIZ/src/promover.py" challenger --run-id "$(cat run_id.txt)"
como "${SVC[@]}" python "$RAIZ/src/promover.py" gate
como "${SVC[@]}" python "$RAIZ/src/promover.py" promover --rfc RFC-LAB-1 \
  --aprovador maria-mudancas --executor svc-mlflow-prod --emergencial "carga inicial do laboratório"

echo "== 3. Admin reaplica acessos (agora o modelo existe)"
como "${ADMIN[@]}" python "$RAIZ/src/permissoes.py"

echo "== 4. Cientista de dados tenta mover o @champion (deve ser recusado)"
como "${ANA[@]}" python - <<'EOF'
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
c = MlflowClient()
print("leitura permitida: champion =", c.get_model_version_by_alias("unicorn-ridge", "champion").version)
try:
    c.set_registered_model_alias("unicorn-ridge", "champion", "1")
except MlflowException as e:
    print("escrita RECUSADA, como esperado:", e.error_code)
else:
    raise SystemExit("FALHA: ana-dados conseguiu mover o @champion")
EOF

echo "== 5. Conta de serviço: treino v2 -> gate -> promoção -> rollback"
export GITHUB_RUN_ID=2 GITHUB_SHA=9f8e7d6c
como "${SVC[@]}" python "$RAIZ/src/train.py" --dados "$RAIZ/dados/unicorn-2026-10.csv" > /dev/null
como "${SVC[@]}" python "$RAIZ/src/promover.py" challenger --run-id "$(cat run_id.txt)"
como "${SVC[@]}" python "$RAIZ/src/promover.py" gate
como "${SVC[@]}" python "$RAIZ/src/promover.py" promover --rfc RFC-LAB-2 \
  --aprovador maria-mudancas --executor svc-mlflow-prod --emergencial "teste automatizado"
como "${SVC[@]}" python "$RAIZ/src/promover.py" rollback --rfc RFC-LAB-3 --executor svc-mlflow-prod

echo "== 6. Auditor lê a evidência"
SAIDA="${EVIDENCIA_SAIDA:-$TMP/evidencia}"
como "${CARLOS[@]}" python "$RAIZ/src/auditar.py" --formato markdown --saida "$SAIDA.md" > /dev/null
como "${CARLOS[@]}" python "$RAIZ/src/auditar.py" --formato json --saida "$SAIDA.json" > /dev/null
cat "$SAIDA.md"
echo "OK: controle de acesso e ciclo de mudança validados."
