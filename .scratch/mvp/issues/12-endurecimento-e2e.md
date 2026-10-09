# 12: Endurecimento E2E e robustez

**What to build:** Os testes dos cenários críticos e o fluxo de ponta a ponta completo.

**Blocked by:** 06, 08, 09, 10, 11

**Status:** ready-for-agent

- [ ] Concorrência/idempotência da reserva de tarefas e da publicação.
- [ ] Queda de worker: lease expirado + `reserva_token` recuperam a tarefa sem efeito duplicado.
- [ ] Orçamento estourado bloqueia novas chamadas pagas.
- [ ] Redis indisponível: site serve da fonte de verdade e regrava o cache.
- [ ] Fonte indisponível: execução marcada como `falhou_parcial`.
- [ ] Isolamento de rascunhos: nunca aparecem no público nem no cache.
- [ ] E2E: coletar → selecionar → gerar → revisar → publicar → ver → editar → conferir cache → retirar → conferir indisponibilidade → consultar logs e custos.
