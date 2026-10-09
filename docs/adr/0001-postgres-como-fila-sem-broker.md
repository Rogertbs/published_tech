# PostgreSQL como fila, sem broker ou Celery

A fila de tarefas, o agendamento e o histórico vivem no próprio PostgreSQL, com reserva atômica via `SELECT ... FOR UPDATE SKIP LOCKED` e lease com `reserva_token`; os executores são workers Python próprios. Decidimos não usar Celery nem broker externo (RabbitMQ, Redis como fila) porque o PostgreSQL já é a fonte de verdade e um broker adicionaria infraestrutura, operação e um segundo modelo de consistência sem necessidade demonstrada. O Redis permanece exclusivamente como cache do site.

**Alternativas consideradas:** Celery + Redis/RabbitMQ (rejeitado: infraestrutura e complexidade desnecessárias para o volume esperado); fila em Redis (rejeitado: Redis não é fonte de verdade e perderia coordenação transacional com o conteúdo).

**Consequências:** exige atenção a transações curtas, lease/liveness, idempotência e recuperação de tarefas abandonadas, e não promete execução *exactly once*. Reintroduzir broker/Celery exige novo ADR.
