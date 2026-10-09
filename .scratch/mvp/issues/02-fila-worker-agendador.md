# 02: Fila PostgreSQL, worker e agendador

**What to build:** Uma fila persistente em PostgreSQL com reserva atômica (`SELECT ... FOR UPDATE SKIP LOCKED`) e `reserva_token`/lease; retry limitado com backoff; recuperação de tarefas abandonadas; agendador idempotente por chave de ocorrência; pausa, cancelamento de pendentes e interrupção cooperativa. Worker e agendador rodam **dentro do container `backend`** (dev).

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Enfileirar e executar uma tarefa trivial, com log por execução.
- [ ] Dois workers não reservam a mesma tarefa; gravação de efeito com `reserva_token` inválido é rejeitada.
- [ ] Lease expirado devolve a tarefa para `pendente` com novo token; retry respeita o limite.
- [ ] Agendador não duplica ocorrência mesmo com múltiplas instâncias; pausa/cancelamento funcionam.
- [ ] Ação "**Executar agora**" (e `POST /api/execucoes`) dispara **uma** execução **independente do flag `automatico`**, com chave de idempotência (duplo clique não duplica) e recusa quando o motor está pausado.
