# Runbook de rollback

**Quando acionar:** métrica de negócio ou de qualidade fora do limite, erro na API que
consome o modelo, ou decisão do dono do modelo.

**Tempo-alvo:** minutos. O rollback não passa por janela nem por revisor obrigatório.

## Passos

1. **Confirmar o estado atual**

    ```bash
    python src/auditar.py --formato markdown | head -20
    ```

    Anote a versão em `@champion` e o valor de `substitui_versao`, que será o destino.

2. **Registrar o motivo.** Use a issue da RFC que promoveu a versão, ou abra uma issue de
   incidente.

3. **Executar** em **Actions > Rollback de produção**:
    - `motivo`: descrição curta do problema;
    - `rfc_issue`: número da issue (ou 0);
    - `para`: vazio, para voltar à versão substituída, ou uma versão específica.

4. **Verificar**
    - `@champion` aponta para a versão de destino (resumo do job ou `auditar.py`);
    - a API que consome o modelo responde normalmente;
    - a métrica que motivou o rollback voltou ao normal.

5. **Recarregar consumidores.** Serviços que carregam `models:/unicorn-ridge@champion` só
   na inicialização precisam ser reiniciados ou ter o cache invalidado.

6. **Fechar o ciclo**
    - a versão revertida fica com `validacao=revertido`, `rollback_em`, `rollback_rfc`;
    - a versão restaurada fica com `restaurada_em`;
    - o comentário com a evidência foi publicado na issue;
    - abra um registro de problema (ITIL Problem) para a causa raiz antes de uma nova
      promoção da versão revertida.

## Sem acesso ao GitHub (contingência)

A conta de serviço pode executar o rollback de qualquer máquina com acesso ao MLflow:

```bash
export MLFLOW_TRACKING_URI=... MLFLOW_TRACKING_USERNAME=svc-mlflow-prod MLFLOW_TRACKING_PASSWORD=...
python src/promover.py rollback --rfc INC-<número> --executor svc-mlflow-prod
```

Registre a execução manual no incidente: ela não gera artefato de workflow.
