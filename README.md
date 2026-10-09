# Published Tech

Portal editorial (PT-BR) sobre IA, software e infraestrutura. Motor de geração
assistida por IA com **publicação aprovada por humano**. Especificação em
`docs/especificacao-published-tech.md`; tickets em `.scratch/mvp/issues/`.

Este repositório contém o **ticket 01 — esqueleto de ponta a ponta** e o **ticket 02 — fila, worker e agendador**.

## Estrutura

- `backend/` — Django (API pública + admin + fila/worker/agendador). No dev, o mesmo
  container também roda Redis (cache).
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

## Fila, worker e agendador

O container `backend` inicia, por padrão, um worker e um agendador em loop
(`START_JOBS=true`). Para rodar manualmente:

```bash
cd backend
python manage.py run_worker          # processa uma tarefa e sai
python manage.py run_worker --loop   # loop contínuo
python manage.py run_scheduler       # cria tarefas devidas e sai
python manage.py run_scheduler --loop
```

Execução avulsa por HTTP (independente do flag de automação; recusada se o motor
estiver pausado):

```bash
curl -X POST localhost:8010/api/execucoes \
  -H 'content-type: application/json' \
  -d '{"tipo":"eco","chave_idempotencia":"manual-1"}'
curl localhost:8010/api/execucoes/1
```

- A fila fica no PostgreSQL, com reserva atômica (`SELECT ... FOR UPDATE SKIP LOCKED`)
  e `reserva_token`/lease. Sem Postgres, há um fallback seguro por update condicional.
- Falhas técnicas têm retry com backoff (limite configurável por tarefa); lease expirado
  devolve a tarefa à fila (a gravação do worker antigo é rejeitada pelo token).
- O agendador só cria tarefas quando `automatico` estiver ligado e o motor não estiver
  pausado. Pausar cancela pendentes automáticas e sinaliza interrupção das em execução;
  "Executar agora" continua funcionando (independente do flag) e é recusado se pausado.
- Se `INTERNAL_API_TOKEN` estiver definido, `POST/GET /api/execucoes` exige o header
  `X-Internal-Token`.

## Cache (render-once-and-cache)

O HTML público é gerado uma vez e guardado no Redis **sem TTL**; só sai por
invalidação em publicar/editar/retirar (ADR-0003). A API Django também cacheia
suas respostas sem TTL. Sem `CACHE_URL`/`REDIS_URL`, o backend usa cache local em
memória e o frontend renderiza sem cache.
