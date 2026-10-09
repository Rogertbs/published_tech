# 08: Pipeline editorial LangGraph (rascunho, texto)

**What to build:** Fluxo explícito coleta → seleção → evidências → redação → revisão → **rascunho**, com afirmações vinculadas a evidências e revisão que **retém com motivos**; sem ciclos automáticos de reescrita. Falhas tratadas: fonte indisponível, evidência insuficiente, fato contraditório, geração parcial, timeout e orçamento estourado. Imagem ausente não é substituída por material de terceiro.

**Blocked by:** 03, 05, 07

**Status:** ready-for-agent

- [ ] Uma execução produz rascunho em `aguardando_revisao` com evidências vinculadas.
- [ ] Afirmação sem evidência retém o conteúdo com motivo registrado.
- [ ] Contradição factual **não** é resolvida automaticamente (vai para revisão humana).
- [ ] Execução retomável por checkpoint sem repetir etapas internas concluídas.
- [ ] Falha de imagem gera rascunho sem imagem e segue as regras normais de aprovação.
- [ ] No dev, a tool de geração de imagem é **mocada** (stub) e devolve **uma única imagem de placeholder** com legenda "Ilustração gerada por IA (simulada)".
