# 01: Esqueleto de ponta a ponta (walking skeleton)

**What to build:** Subir a solução local em **3 containers** (`db` PostgreSQL, `backend` Django com worker/agendador/Redis internos, `frontend` Astro) e provar o caminho completo com conteúdo manual, sem IA nem fontes reais: criar um Conteúdo e uma Versão, aprovar (origem humana) e publicar; a home e o artigo são servidos pelo Astro lendo a API Django com **render-once-and-cache** (sem TTL) e invalidação ao publicar/retirar.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `docker compose up` sobe os 3 containers; migrações e criação segura do administrador rodam.
- [ ] É possível criar Conteúdo/Versão no admin, aprovar e publicar.
- [ ] Home e artigo renderizam a **versão publicada**; retirar remove o conteúdo do público.
- [ ] O HTML público é cacheado sem TTL e invalidado por evento; rascunho/prévia nunca entram no cache.
- [ ] URLs públicas estáveis; estado vazio e 404 funcionam.
