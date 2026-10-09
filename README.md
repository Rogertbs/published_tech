# Published Tech

Portal editorial (PT-BR) sobre IA, software e infraestrutura. Motor de geração
assistida por IA com **publicação aprovada por humano**. Especificação em
`docs/especificacao-published-tech.md`; tickets em `.scratch/mvp/issues/`.

Este repositório contém o **ticket 01 — esqueleto de ponta a ponta**.

## Estrutura

- `backend/` — Django (API pública + admin). No dev, o mesmo container também roda
  Redis (cache). Worker/agendador entram no ticket 02.
- `frontend/` — Astro (SSR) consumindo a API Django, com middleware de cache.
- `docker-compose.yml` — **3 containers**: `db` (PostgreSQL), `backend`, `frontend`.

## Rodar com Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- Site: http://localhost:4321
- Admin: http://localhost:8010/admin (usuário/senha do `.env`)

## Rodar localmente (sem Docker)

Backend (usa SQLite por padrão; Postgres se `POSTGRES_DB` estiver setado):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8010
```

Frontend:

```bash
cd frontend
npm install
API_BASE_URL=http://127.0.0.1:8010 npm run build
API_BASE_URL=http://127.0.0.1:8010 node dist/server/entry.mjs
```

## Testes

```bash
cd backend
python manage.py test
```

## Cache (render-once-and-cache)

O HTML público é gerado uma vez e guardado no Redis **sem TTL**; só sai por
invalidação em publicar/editar/retirar (ADR-0003). A API Django também cacheia
suas respostas sem TTL. Sem `CACHE_URL`/`REDIS_URL`, o backend usa cache local em
memória e o frontend renderiza sem cache.
