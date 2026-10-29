#!/usr/bin/env bash
# Configura o repositório no GitHub para o fluxo de governança, usando a CLI `gh`:
# rótulos da RFC, proteção da main, environments com revisores e variáveis/segredos.
#
#   gh auth login
#   bash scripts/configurar_github.sh <owner>/<repo>
#
# Revisores obrigatórios em environments estão disponíveis em repositórios PÚBLICOS em
# qualquer plano; em repositórios privados, dependem do plano da conta.
set -euo pipefail

REPO="${1:?uso: bash scripts/configurar_github.sh <owner>/<repo>}"
EU=$(gh api user --jq .login)
MEU_ID=$(gh api user --jq .id)
REVISOR="${REVISOR:-$EU}"                     # quem aprova a promoção
REVISOR_ID=$(gh api "users/$REVISOR" --jq .id)
echo "Repositório: $REPO | revisor de produção: $REVISOR"

echo "== Rótulos do ciclo da RFC"
criar_rotulo() { gh label create "$1" -R "$REPO" --color "$2" --description "$3" --force; }
criar_rotulo "rfc"              "5319e7" "Solicitação de mudança de modelo"
criar_rotulo "rfc:em-avaliacao" "fbca04" "Aguardando CAB / gestor de mudança"
criar_rotulo "rfc:aprovada"     "0e8a16" "Aprovada: o workflow de promoção pode rodar"
criar_rotulo "rfc:implementada" "1d76db" "Promovida para @champion"
criar_rotulo "rfc:revertida"    "b60205" "Rollback executado"

echo "== Proteção da main (PR obrigatório + CI verde)"
gh api -X PUT "repos/$REPO/branches/main/protection" --input - <<'EOF'
{
  "required_status_checks": {"strict": true, "contexts": ["testes"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 0, "require_code_owner_reviews": false},
  "restrictions": null
}
EOF

echo "== Environments"
ambiente() {  # nome, json-dos-revisores
  gh api -X PUT "repos/$REPO/environments/$1" --input - <<EOF
{
  "wait_timer": 0,
  "prevent_self_review": ${PREVENIR_AUTOAPROVACAO:-false},
  "reviewers": $2,
  "deployment_branch_policy": {"protected_branches": true, "custom_branch_policies": false}
}
EOF
  echo "  - $1"
}
ambiente mlflow-treino              '[]'
ambiente producao-modelos           "[{\"type\": \"User\", \"id\": $REVISOR_ID}]"
ambiente producao-modelos-rollback  '[]'
ambiente mlflow-admin               "[{\"type\": \"User\", \"id\": $MEU_ID}]"

echo "== Servidor MLflow"
read -rp "MLFLOW_TRACKING_URI (ex. http://localhost:5000; vazio = só CI): " URI
if [ -n "$URI" ]; then
  gh variable set MLFLOW_TRACKING_URI -R "$REPO" --body "$URI"
  read -rp "Runner (vazio = ubuntu-latest; 'self-hosted' para o runner local): " RUNNER
  [ -n "$RUNNER" ] && gh variable set RUNNER -R "$REPO" --body "$RUNNER"
  read -rsp "Senha da conta svc-mlflow-prod: " SENHA_SVC; echo
  for env in mlflow-treino producao-modelos producao-modelos-rollback; do
    gh secret set MLFLOW_TRACKING_USERNAME -R "$REPO" --env "$env" --body "svc-mlflow-prod"
    gh secret set MLFLOW_TRACKING_PASSWORD -R "$REPO" --env "$env" --body "$SENHA_SVC"
  done
  read -rsp "Senha do admin do MLflow: " SENHA_ADMIN; echo
  gh secret set MLFLOW_ADMIN_USERNAME -R "$REPO" --env mlflow-admin --body "admin"
  gh secret set MLFLOW_ADMIN_PASSWORD -R "$REPO" --env mlflow-admin --body "$SENHA_ADMIN"
fi
echo "Pronto. Próximo passo: docs/configuracao-github.md, seção 'Primeira mudança'."
