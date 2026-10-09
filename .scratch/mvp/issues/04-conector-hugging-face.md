# 04: Conector Hugging Face

**What to build:** Fonte Hugging Face usando a API do Hub (`sort=trendingScore`/`createdAt`, janela semanal, filtros por tarefa), com classificação nas quatro categorias, agrupamento de variantes por família (`base_model`) e os campos exigidos do domínio. Separar metadado coletado de informação verificada.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] Coleta HF produz candidatos com os campos do domínio.
- [ ] Variantes da mesma família são agrupadas em um único item.
- [ ] Cada item recebe uma das quatro categorias; dado ausente é marcado como **desconhecido**.
- [ ] Data de criação do repositório não é usada como comprovação de lançamento.
