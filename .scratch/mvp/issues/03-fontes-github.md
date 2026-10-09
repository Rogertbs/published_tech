# 03: Fontes configuráveis + conector GitHub

**What to build:** CRUD de fontes (tipo GitHub) no admin — cadastrar, editar, desativar, excluir — com credencial por referência; coleta via Search API com qualificadores datados; normalização, deduplicação e seleção de candidatos; respeito a limites de taxa. Só coletar de fontes **ativas**.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Cadastrar/editar/desativar/excluir uma fonte; desativar interrompe novas coletas sem apagar histórico.
- [ ] Coleta gera registros normalizados e candidatos selecionados.
- [ ] Limite de taxa tratado com backoff, sem derrubar a execução.
- [ ] Falha de uma fonte não derruba as demais (execução marcada como `falhou_parcial`).
