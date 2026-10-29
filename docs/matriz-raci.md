# Matriz RACI — mudança de modelo

R = executa · A = responde pela decisão · C = consultado · I = informado

| Atividade | Cientista de dados | Dono do modelo | Gestor de mudança / CAB | Conta de serviço (pipeline) | DPO | Auditoria |
| --- | --- | --- | --- | --- | --- | --- |
| Alterar código de treino ou dados | R | A | I | — | C se houver dados pessoais | — |
| Alterar a política do gate (`governanca.yml`) | C | A/R | C | — | C | I |
| Alterar a matriz de acesso (`config/acessos.yml`) | — | C | A | — | C | I |
| Treinar e registrar versão | I | I | — | R | — | — |
| Executar o gate | I | I | I | R | — | — |
| Classificar dados pessoais e RIPD | C | R | I | — | A | I |
| Abrir a RFC | R | A | I | — | — | — |
| Aprovar a RFC (`rfc:aprovada`) | I | C | A/R | — | C se houver dados pessoais | — |
| Aprovar o environment de produção | — | R | A | — | — | — |
| Mover o `@champion` | I | I | I | R | — | — |
| Decidir pelo rollback | C | A/R | R | — | — | I |
| Executar o rollback | — | R | I | R | — | I |
| Revisar evidências e histórico | — | C | C | — | C | A/R |

**Princípio:** pessoas decidem e aprovam; só a conta de serviço, dentro de um job com
aprovação registrada, escreve no modelo de produção.
