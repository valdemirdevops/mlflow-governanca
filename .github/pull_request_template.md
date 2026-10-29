## O que muda

<!-- código de treino, dados, política (governanca.yml) ou acessos (config/acessos.yml) -->

## Impacto na governança

- [ ] Muda o critério do gate (`governanca.yml`) — exige revisão do dono do modelo
- [ ] Muda permissões (`config/acessos.yml`) — exige revisão do administrador
- [ ] Muda dados de treino — o `digest` do dataset vai mudar na próxima versão
- [ ] Nenhum dos anteriores

## Evidência

O workflow **CI** roda o ciclo completo (treino, gate, promoção, rollback, auditoria)
e publica a evidência no resumo do job.
