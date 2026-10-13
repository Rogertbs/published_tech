# 01: Modelo editorial de notícias (spec 4.3)

**What to build:** O caminho de notícia (`secao=noticias`, `POST /api/noticias`) hoje reusa o prompt genérico e só valida o encanamento. Implantar o modelo editorial da spec 4.3: estrutura **contexto breve → análise → consequências práticas → limitações → fontes**, distinção explícita entre **fato / alegação do fornecedor / estimativa / opinião**, e transparência (identidade editorial + responsável humano + aviso de automação).

**Blocked by:** None (can start immediately)

**Status:** needs-triage

- [ ] Prompt/config de notícias dedicado (por seção), versionado.
- [ ] Texto marca o que é fato, alegação, estimativa e opinião.
- [ ] Cada notícia traz o **link da fonte** e a estrutura de 5 partes.
- [ ] Rodapé/transparência com automação + responsável; nunca assinado como opinião pessoal.
- [ ] Não reutiliza o enquadramento de "curadoria própria".
