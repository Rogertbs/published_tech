# 10: Ciclo editorial endurecido

**What to build:** Aprovação por **versão exata** com origem (`humano`/`automatico`), regras avaliadas e auditoria imutável; edição de conteúdo publicado via estado `publicado_em_edicao` mantendo a **versão pública** no ar; concorrência entre edição e publicação; publicação idempotente por `conteudo_id`+`versao_id`.

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] Aprovar v1; editar gera v2 que **não** é publicável sem nova aprovação.
- [ ] Editar conteúdo publicado mantém a versão pública; publicar a nova troca o ponteiro; retirar cessa a exposição.
- [ ] Publicar o mesmo par duas vezes não duplica a publicação.
- [ ] Toda aprovação e ação administrativa registram origem, responsável, regras avaliadas e timestamp.
