# Published Tech

Portal editorial (PT-BR) sobre IA, software e infraestrutura. Motor de geração
assistida por IA com **publicação aprovada por humano**. Especificação em
`docs/especificacao-published-tech.md`; tickets em `.scratch/mvp/issues/`.

Este repositório contém o **ticket 01 — esqueleto de ponta a ponta** e o **ticket 02 — fila, worker e agendador**.

## Estrutura

- `backend/` — Django (API pública + admin + fila/worker/agendador + fontes). No dev, o
  mesmo container também roda Redis (cache).
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

## Fontes e coleta (GitHub e Hugging Face)

Fontes são instâncias configuráveis no admin (`Fonte`): tipo, nome, credencial por
**referência** (nome de uma variável de ambiente, ex.: `GITHUB_TOKEN`), parâmetros e
ativo/inativo. Desabilitar interrompe novas coletas sem apagar o histórico.

- A tarefa de fila `coletar` (via `run_worker` ou "Executar agora") roda
  `coletar_todas`: só fontes habilitadas; uma falha de fonte não derruba as demais
  (marca `falhou_parcial`).
- O conector GitHub usa a Search API com qualificadores datados (`stars:>=`, `pushed:>=`,
  `language:`, `topic:`), respeita o limite de taxa com backoff e normaliza os
  registros (id, nome, URL, linguagem, licença, métricas, datas).
- O conector Hugging Face usa a Hub API (`sort=trendingScore&direction=-1&full=true`),
  agrupa variantes da mesma família (por `base_model` ou variante do id) em um único
  item e classifica cada item em uma das quatro categorias (`lancamento_confirmado`,
  `nova_variante`, `modelo_antigo_atencao`, `atualizacao_repositorio`). Sem um anúncio
  verificado, **não** marca lançamento confirmado nem usa a data de criação como prova
  de lançamento; campos ausentes ficam `Desconhecido`.
- Registros são deduplicados por `(fonte, chave_externa)`.
- `selecionar_candidatos` ordena por pontuação (estrelas) e limita a seleção
  (`parametros.selecao`, padrão 5), registrando o `Candidato` e o motivo.

Parâmetros úteis de `Fonte.parametros`: `janela_dias`, `min_estrelas`, `limite`,
`language`, `topic`, `selecao`.

## IA e instrumentação

Toda chamada de modelo passa pela camada única `ai.instrumentation.executar_texto`,
que registra uma `ChamadaIA` (provedor, modelo, finalidade, etapa, correlação,
timestamps, duração, status, tentativa, request id, tokens, moeda, preço, custo e
origem do custo).

- Provedor substituível via `AI_PROVIDER`: `mock` (padrão, simulado, sem custo) e
  `openrouter` (exige `OPENROUTER_API_KEY`; **sem fallback silencioso** se faltar).
- Dev usa modelos **full free** da OpenRouter (`AI_MODELO_PADRAO`).
- Custo: **informado** pelo provedor, senão **estimado** por `PrecoModelo` (USD), senão
  **desconhecido**. Consumo desconhecido **nunca** é gravado como zero.
- Falha, timeout e resultado incerto recebem status próprio (`erro`, `timeout`,
  `incerto`).
- Credenciais nunca são registradas na chamada nem expostas.

## Orçamento e relatórios

- Limites diário/mensal configuráveis (`ConfiguracaoOrcamento`; padrão **US$ 5/dia** e
  **US$ 30/mês**), com fuso de fechamento `America/Sao_Paulo` (armazenamento UTC).
- Antes de cada chamada paga, registra-se uma `ReservaOrcamento` (conservadora) e, após
  a resposta, ela é **conciliada** com a chamada — sem dupla contagem (reserva ativa +
  chamada conciliada). Ao estourar, a chamada é **bloqueada** e um `EventoOrcamento` é
  registrado. Mock (gratuito) não reserva.
- Publicar manualmente conteúdo já pronto **não** passa pelo orçamento.
- Relatórios em `GET /api/relatorios/custos` (JSON) e `GET /api/relatorios/custos.csv`
  (detalhe até a chamada), com filtros por período, provedor, modelo, finalidade,
  status, tentativa, conteúdo e tarefa. O histórico financeiro (`ChamadaIA`) é
  independente dos logs operacionais (`EventoTarefa`), que podem expirar sem afetar os
  relatórios (`jobs.services.expirar_eventos`).

## Configuração e prompts

- Configurações e prompts são **versionados** (`Configuracao` + `VersaoConfiguracao`):
  criar, comparar, restaurar e ativar sem alterar o histórico. Alterar a config **não**
  muda versões antigas.
- **Precedência**: `sistema` define as regras obrigatórias (campos **protegidos**:
  `exigir_evidencia`, `bloqueios_publicacao`, `orcamento_obrigatorio`, `texto_fonte_e_dado`);
  `geral`, `secao` e `agente` só sobrescrevem os **campos permitidos**. Campo protegido
  não pode ser definido fora do escopo `sistema`.
- Cada execução (tarefa do worker) registra um **snapshot**
  (`configuracao.services.capturar_snapshot`) com os campos resolvidos e as versões
  efetivas usadas; alterações posteriores não o afetam.
- Suporta **comparar** (`comparar`), **restaurar** (`restaurar`, cria nova versão) e
  **presets** (`criar_versao_de_preset`). Alterações geram registro em
  `AuditoriaAdministrativa`.
- Prompt vazio é rejeitado; config de agente exige `prompt`; **texto de fonte** é sempre
  tratado como dado (`montar_prompt_com_fonte`; `executar_texto(..., fonte_texto=...)`),
  nunca como instrução.
- `testar_prompt` gera **prévia privada** (finalidade `teste_prompt`), sem publicar, com
  custo contabilizado separadamente nos relatórios.

## Pipeline editorial (LangGraph)

A tarefa de fila `pipeline` (ou `executar_pipeline`) roda um grafo LangGraph com etapas
explícitas: `selecionar` → `evidencias` → `redigir` → `revisar` → `ilustrar` → `salvar`.

- Cada etapa é **idempotente e persistida** (`EtapaExecucao`): retomar a mesma `Execucao`
  não repete etapas concluídas nem gasta IA de novo.
- **Evidências** (`Evidencia`) são vinculadas à versão; a **revisão** retém o conteúdo
  com motivos (`sem_afirmacoes`, `afirmacao_sem_evidencia`, `contradicao_factual`) sem
  ciclos de reescrita.
- Rascunho vai para `aguardando_revisao` quando a revisão passa; caso contrário fica em
  `rascunho` com os motivos.
- A **ilustração é mocada** no dev (uma imagem de placeholder); falha de imagem gera
  rascunho sem imagem e segue as regras normais de aprovação.
- `Execucao` registra estado, snapshot de configuração e erro; `ChamadaIA` fica ligada à
  execução.

## Ciclo editorial

- **Aprovação é por versão exata** (origem, responsável, regras avaliadas, timestamp);
  editar invalida a aprovação anterior.
- **Editar conteúdo publicado** (`content.services.editar`) cria nova versão e mantém a
  **versão pública no ar** (`estado=publicado_em_edicao`) até a nova ser aprovada e
  publicada — quando o ponteiro troca. **Retirar** cessa a exposição.
- **Publicação idempotente** por `conteudo`+`versao` (não duplica; a anterior é
  encerrada) e só para versão aprovada.
- Toda ação (aprovar/editar/publicar/retirar) e alteração de config gera registro em
  `AuditoriaAdministrativa` (`auditoria` app).

## Cache (render-once-and-cache)

O HTML público é gerado uma vez e guardado no Redis **sem TTL**; só sai por
invalidação em publicar/editar/retirar (ADR-0003). A API Django também cacheia
suas respostas sem TTL. Sem `CACHE_URL`/`REDIS_URL`, o backend usa cache local em
memória e o frontend renderiza sem cache.
