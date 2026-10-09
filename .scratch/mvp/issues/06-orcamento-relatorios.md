# 06: Orçamento bloqueante + ReservaOrcamento + relatórios

**What to build:** Orçamento diário **US$ 5** e mensal **US$ 30** (configurável); reserva conservadora antes da chamada paga e conciliação depois; bloquear **novas chamadas pagas** ao estourar; relatórios filtráveis (data, conteúdo, versão, seção, agente/etapa, provedor, modelo, status, tentativa) com drill-down até a chamada e exportação CSV. Histórico financeiro separado dos logs operacionais.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] Estouro de orçamento bloqueia novas chamadas pagas e é registrado.
- [ ] Reserva + conciliação sem dupla contagem (estimado/informado/reconciliado não somam como três).
- [ ] CSV exporta; relatório de período antigo sobrevive à expiração dos logs operacionais.
- [ ] Publicar manualmente conteúdo já pronto, sem novo gasto, **não** é bloqueado por orçamento.
