# 04: Reforma de usabilidade do Django Admin

**What to build:** Tornar o Django Admin usável, em português e visualmente agradável, com o
fluxo editorial à mão. Hoje os nomes aparecem errados/em inglês, as ações de aprovar/publicar
estão espalhadas e em massa (checkbox + dropdown no topo), faltam filtros/atalhos e o **CSS
padrão é ruim**. Continua sendo **Django Admin** (DEC-18); painel próprio segue como evolução
(EVO-02).

**Blocked by:** None (can start immediately)

**Status:** needs-triage

## Problemas identificados (análise)

- **Nomes**: apps sem `verbose_name` (aparecem *Ai, Jobs, Content, Sources, Finance, Pipeline*);
  modelos sem `verbose_name` → plural cru (*Conteudos, Versaos, Execucaos, Chamada IAs,
  Preco Modelos*); campos com rótulo automático (*"versao em edicao", "reserva token"*).
- **Fluxo escondido**: aprovar em *Versões*, publicar/retirar em *Conteúdos*, ambos em massa;
  sem botão na página do objeto; sem filtro "aguardando revisão".
- **Navegação**: modelos técnicos (ChamadaIA, EtapaExecucao, EventoTarefa, RegistroNormalizado)
  misturados com os editoriais; sem agrupamento por área.
- **Listas**: faltam `search_fields`, `date_hierarchy`, ordenação e paginação explícitas.
- **Aparência (CSS)**: o tema padrão do Django Admin é denso, com tipografia pequena, baixo
  contraste nos botões/ações e sem identidade — visualmente ruim e cansativo de operar.

## Escopo

- [ ] `verbose_name`/`verbose_name_plural` em todos os `AppConfig` e `Meta`; `verbose_name`
      nos campos; admin 100% em português.
- [ ] Agrupar o menu por área: **Editorial** (Conteúdos/Versões/Publicações), **Fontes**,
      **Motor & Fila** (Tarefas/Execuções/Agendamentos), **Custos** (Chamadas/Preços/Orçamento),
      **Configuração** (Config/Prompts), **Observabilidade** (Auditoria/Logs).
- [ ] **Botões na página do conteúdo**: "Aprovar e publicar", "Republicar versão aprovada",
      "Retirar" (template + view de admin).
- [ ] **Filtro "aguardando revisão"** e visão de rascunhos.
- [ ] Ação consolidada "Aprovar e publicar"; confirmar ações destrutivas.
- [ ] Melhorar listas (`search_fields`, `date_hierarchy`, `list_select_related`, `list_per_page`).
- [ ] **Dashboard** inicial com atalhos: produzir notícia/curadoria, revisar pendentes,
      relatórios de custo.
- [ ] Esconder/colapsar modelos técnicos (read-only).
- [ ] **Melhorar o CSS/tema do admin**: overrides próprios (via `admin/base_site.html` +
      CSS em `static/admin/`) usando a paleta do site (`#0F172A`/`#2563EB`/`#14B8A6`),
      tipografia e espaçamento legíveis, botões e estados com contraste adequado (AA),
      formulários mais claros e layout responsivo. Avaliar tema pronto
      (ex.: `django-jazzmin`/`django-admin-interface`) versus CSS customizado, preferindo
      o de menor manutenção.

## Notas

- Alinhado à spec 7.1 (personalização mínima do admin) e 7.2 (telas).
- Não troca a stack; a troca por painel próprio é EVO-02.

## Comments

- Implementado em `eed9d1c`. Nomes em PT (apps/modelos/campos); agrupamento por área
  (Editorial, Fontes, Motor e fila, Custos, Configuração, Observabilidade) com modelos técnicos
  ocultos do menu; botões Aprovar e publicar / Publicar versão aprovada / Retirar na página do
  conteúdo; filtro "fila de revisão"; ação em massa "Aprovar e publicar"; dashboard com atalhos;
  CSS próprio (`backend/static/admin/css/painel.css`).
