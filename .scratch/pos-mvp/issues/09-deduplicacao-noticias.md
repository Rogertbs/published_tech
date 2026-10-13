# 09: Evitar notícias/curadorias duplicadas (mesmo item de origem)

**What to build:** Hoje o pipeline sempre pega os candidatos do topo; rodar de novo escolhe o
mesmo item de origem e cria **outra** notícia com o mesmo conteúdo (duplicado). Adicionar
checagem para não repetir o mesmo conteúdo, **permitindo conteúdo relacionado/continuação**
(mesmo tema/família) desde que não seja idêntico.

**Blocked by:** None (can start immediately)

**Status:** needs-triage

## Problema

- `RegistroNormalizado` é deduplicado por `(fonte, chave_externa)`, mas a **seleção** não
  considera se aquele registro já virou conteúdo.
- Cada execução cria um `Conteudo` novo (`slug = <secao>-<execucao_id>`), então repetir a
  geração produz uma notícia com o **mesmo texto/fonte**.
- A idempotência de `chave_idempotencia` só cobre a mesma chamada, não a repetição em runs
  diferentes.

## Escopo

- [ ] Marcar/rastrear itens de origem já usados em conteúdo (vínculo do `RegistroNormalizado`
      à `Versao`/`Item`/`Evidencia`, com estado publicado/rascunho).
- [ ] Na seleção, **excluir** candidatos cujo item de origem já foi usado (janela configurável).
- [ ] Checagem de **duplicidade de conteúdo** (ex.: hash do texto e/ou da chave de origem)
      antes de salvar o rascunho; se idêntico, não criar novo.
- [ ] Permitir **relacionado/continuação**: item de origem diferente, mesmo tema → novo conteúdo.
- [ ] Configurável (ligar/desligar, janela) e registrado em auditoria.

## Critérios de aceitação

- [ ] Rodar a mesma notícia duas vezes com a mesma fonte **não** cria duplicata.
- [ ] Um item de origem novo cria uma notícia nova normalmente.
- [ ] Conteúdo relacionado (mesmo tema, origem diferente) é permitido.
- [ ] O comportamento é configurável e fica registrado.

## Notas

- Relaciona-se à spec 4.1.1 (detectar mudanças relevantes sem repetir), 6 (idempotência) e ao
  requisito de não duplicar efeitos (RN-04/RN-26).
