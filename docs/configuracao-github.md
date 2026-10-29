# Configuração no GitHub, passo a passo

O workflow **CI** funciona sem nada disto: ele sobe o próprio MLflow dentro do job. Os
passos abaixo ligam o fluxo **real** (treino, promoção, rollback) a um servidor MLflow
persistente.

## 1. Publicar o repositório

```bash
cd mlflow-governanca
git init -b main && git add . && git commit -m "Governança de modelos com MLflow"
gh repo create mlflow-governanca --public --source . --push
```

Troque `OWNER` pelo seu usuário em `README.md` (badge) e `.github/CODEOWNERS`.

## 2. Subir o servidor MLflow

```bash
# troque admin_password em config/basic_auth.ini antes de subir
docker compose up -d --build
```

Crie os usuários e aplique a matriz de acesso (as senhas vêm de variáveis de ambiente):

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
export MLFLOW_TRACKING_USERNAME=admin MLFLOW_TRACKING_PASSWORD='<senha do admin>'
export MLFLOW_SENHA_SVC_MLFLOW_PROD='<senha forte>'
export MLFLOW_SENHA_ANA_DADOS='...' MLFLOW_SENHA_MARIA_MUDANCAS='...' MLFLOW_SENHA_CARLOS_AUDITORIA='...'
python src/permissoes.py --criar-usuarios
```

## 3. Runner self-hosted (recomendado para o laboratório)

Os runners do GitHub ficam na internet e não alcançam o `localhost:5000` do seu
computador. A forma gratuita de resolver é registrar um runner na mesma máquina do
`docker compose`:

1. No repositório: **Settings > Actions > Runners > New self-hosted runner** (Linux) e
   siga os comandos exibidos.
2. Na máquina do runner, instale `python3`, `gh` e `jq`.
3. No passo 4, informe `self-hosted` quando o script perguntar o runner. Isso grava a
   variável `RUNNER`, usada pelos jobs que falam com o MLflow. O CI de pull request
   continua no runner do GitHub.

Segurança: em repositório público, um runner self-hosted não deve executar código de
pull requests de terceiros. Aqui, os jobs que usam o runner só rodam na `main` ou por
disparo manual. Mantenha também **Settings > Actions > General > Fork pull request
workflows > Require approval for all external contributors**.

Alternativa: um servidor MLflow público (VM na nuvem) com TLS e `--allowed-hosts`
configurado para o domínio. Nesse caso, não é preciso runner self-hosted.

## 4. Configurar o repositório

```bash
gh auth login
bash scripts/configurar_github.sh <owner>/mlflow-governanca
# para um revisor diferente de você:  REVISOR=<login> bash scripts/configurar_github.sh ...
```

O script cria:

| Item | Configuração |
| --- | --- |
| Rótulos | `rfc`, `rfc:em-avaliacao`, `rfc:aprovada`, `rfc:implementada`, `rfc:revertida` |
| Proteção da `main` | PR obrigatório e CI (`testes`) verde |
| Environment `mlflow-treino` | Segredos da conta de serviço; só a partir de branch protegida |
| Environment `producao-modelos` | Revisor obrigatório + segredos da conta de serviço |
| Environment `producao-modelos-rollback` | Sem revisor (rollback rápido) + segredos |
| Environment `mlflow-admin` | Revisor obrigatório + segredos do admin (matriz de acesso) |
| Variáveis | `MLFLOW_TRACKING_URI` e, opcionalmente, `RUNNER` |

## 5. Primeira mudança (versão 1)

1. **Actions > Treino e gate > Run workflow** com `dados/unicorn-2026-09.csv`. A versão 1
   vira `@challenger` e passa no gate (é a primeira, não há champion).
2. **Issues > New issue > RFC — mudança de modelo**. Preencha e crie. Como CAB, aplique o
   rótulo `rfc:aprovada`.
3. **Actions > Promoção para produção > Run workflow** com o número da issue. Fora da
   janela (seg a sex, 19h às 23h), preencha a justificativa emergencial.
4. O job para em **Waiting for review**. Aprove o environment `producao-modelos`.
5. O `@champion` aponta para a versão 1, a evidência aparece como comentário na RFC e a
   issue recebe `rfc:implementada`.

## 6. Segunda mudança e rollback

1. Faça qualquer PR que altere `src/`, `dados/` ou `governanca.yml` e faça o merge (ou rode
   **Treino e gate** manualmente). O treino usa o arquivo padrão, `unicorn-2026-10.csv`: a
   versão 2 vira `@challenger` e o gate a compara com a versão 1 no mesmo holdout.
2. Repita a RFC e a promoção: o `@champion` vai para a versão 2 com
   `substitui_versao=1`.
3. **Actions > Rollback de produção** com um motivo e o número da issue. O `@champion`
   volta para a versão 1, a versão 2 fica com `validacao=revertido` e a issue recebe
   `rfc:revertida`.

## 7. Projeto individual e segregação de funções

`governanca.yml` traz `exigir_segregacao: true`: quem disparou o treino não pode aprovar a
promoção. Sozinho, você é as duas pessoas, e a promoção será recusada. Há duas saídas:

- **Mais realista:** crie uma segunda conta no GitHub, adicione-a como colaboradora e use
  `REVISOR=<login>` no `configurar_github.sh`. Ela aprova o environment.
- **Mais simples:** abra um PR mudando para `exigir_segregacao: false`, com a
  justificativa "laboratório individual". A evidência de cada versão grava o
  `gate_politica_sha`, que mostra qual política estava em vigor. Isso também é governança.

## 8. Telas para o README

Capturas que valorizam o portfólio:

- Execução do CI com o resumo do gate e a evidência.
- Job de promoção em **Waiting for review** no environment `producao-modelos`.
- Comentário de evidência publicado automaticamente na RFC.
- Model Registry no MLflow com versões, aliases e tags (`rfc`, `aprovado_por`,
  `substitui_versao`).
- Execução recusada: fora da janela ou por segregação, mostrando a mensagem da regra.
