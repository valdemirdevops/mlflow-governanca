# Checklist da mudança de modelo e critérios para mudança padrão

## Checklist de cada promoção

- [ ] IC completo: `dono`, `classificacao` e `dados_pessoais` no modelo registrado (o gate verifica)
- [ ] Se `dados_pessoais=sim`: tag `ripd` preenchida e validada pelo DPO (o gate verifica)
- [ ] Versão criada pelo pipeline, com `git_commit`, `pipeline_url` e dataset (o gate verifica)
- [ ] Gate aprovado no holdout fixo, contra o champion atual (a promoção verifica)
- [ ] RFC aberta, com o formulário preenchido e o rótulo `rfc:aprovada` (o workflow verifica)
- [ ] Environment `producao-modelos` aprovado por revisor (o GitHub exige)
- [ ] Aprovador diferente de quem disparou o treino (a promoção verifica)
- [ ] Dentro da janela, ou com justificativa emergencial (a promoção verifica)
- [ ] Evidência publicada na RFC e guardada como artefato (o workflow faz)
- [ ] Verificação pós-mudança feita pelo dono do modelo
- [ ] Rollback testado pelo menos uma vez no ambiente

## Quando o CAB pode tornar a mudança "padrão" (pré-aprovada)

Uma mudança padrão é aprovada uma vez, como tipo, e as próximas seguem sem passar pelo
CAB. Para este modelo, os critérios sugeridos são:

| Critério | Como comprovar |
| --- | --- |
| Gate com critério objetivo e versionado | `governanca.yml` no Git, com histórico de PRs |
| Últimas N promoções sem incidente | Histórico em `auditar.py` + registros de incidente |
| Rollback testado e com tempo conhecido | Execuções do workflow de rollback |
| Evidência automática completa | Comentários de evidência nas RFCs anteriores |
| Impacto baixo em decisões sobre pessoas | Avaliação do dono do modelo e do DPO |

Modelos que decidem crédito, saúde, emprego ou acesso a serviços costumam continuar como
mudança **normal**, mesmo com o processo automatizado, por causa do impacto sobre os
titulares de dados.
