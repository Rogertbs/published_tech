# 11: Frontend do site (layout e componentes)

**What to build:** Identidade **provisória** e o site público do spec 10.6/10.7, com **layout de referência no estilo do CNN** (estrutura de grade editorial; sem copiar marca/assets): Header com navegação de seções; Home com hero/manchete + grade de 3 colunas + blocos por seção + rail "Mais lidas"; seção/categoria com manchete + grade paginada; artigo (título grande, metadados/transparência, imagem lead, citação destacada, evidências, relacionados); curadoria + item derivado; Sobre/Transparência; 404. Componentes Astro (layouts, Header/Footer, `Hero`, `PostCard`, `ItemCard`, `Badge`/`Kicker`, `EvidenceList`, `Figure`+legenda, `Pagination`, `Prose`, `TransparencyBanner`, `EmptyState`, `ErrorState`, `SEOHead`). Responsividade mobile-first, acessibilidade AA, metadados/canonical/OpenGraph, sitemap. Reutiliza render-once-and-cache.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Todas as páginas navegáveis com conteúdo publicado, incluindo item derivado e 404.
- [ ] Home no estilo editorial de referência (hero + grade 3 colunas + blocos por seção).
- [ ] Layout responsivo; foco visível; contraste AA; `alt` nas imagens.
- [ ] `title`/`description`/canonical/OpenGraph por página e sitemap gerados.
- [ ] Selo "conteúdo assistido por IA, revisado por humano" presente no artigo.
- [ ] No dev, as imagens usam **uma única imagem de placeholder** (tool de geração mocada) com legenda de IA.
- [ ] Publicar/editar/retirar refletem no site via invalidação de cache.
