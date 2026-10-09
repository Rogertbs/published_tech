# Published Tech

Portal editorial em português sobre IA, software e infraestrutura, com motor de geração assistida por IA e publicação aprovada por humano.

## Language

**Fonte (source instance)**:
Instância configurável de origem de dados (inicialmente GitHub e Hugging Face) que o administrador cadastra, edita, desativa ou exclui.
_Avoid_: Origem, provider, feed

**Conector (connector)**:
Adaptador de código que sabe consultar um *tipo* de fonte e normalizar seus registros. Um tipo novo de fonte exige um conector novo.
_Avoid_: Plugin, integração, driver

**Registro normalizado**:
Dado de uma fonte convertido para o modelo interno comum, antes de virar candidato.
_Avoid_: Item bruto, payload

**Candidato**:
Registro normalizado selecionado por uma execução como possível conteúdo editorial.
_Avoid_: Sugestão, escolhido

**Evidência**:
Referência verificável (URL, metadado datado, trecho) que sustenta uma afirmação do texto.
_Avoid_: Fonte citada, referência

**Conteúdo**:
Agregado editorial publicável. É o objeto que tem versões, aprovação e publicação.
_Avoid_: Post, artigo, peça

**Matéria**:
Conteúdo do tipo `artigo` — análise comentada de um acontecimento ou ferramenta.
_Avoid_: Post, reportagem

**Curadoria**:
Conteúdo do tipo `lista` — seleção periódica de itens (repositórios no GitHub, modelos no Hugging Face) com análise própria.
_Avoid_: Ranking, destaque, radar, edição de ranking

**Item**:
Entrada dentro de uma Curadoria: um repositório (GitHub) ou um modelo (Hugging Face).
_Avoid_: Entrada, destaque

**Versão**:
Snapshot imutável do corpo e metadados de um Conteúdo.
_Avoid_: Revisão, rascunho (rascunho é um estado, não uma versão)

**Versão publicada**:
A versão apontada como ativa no site público de um Conteúdo.
_Avoid_: Versão atual, no ar

**Versão em edição**:
Versão de um Conteúdo que ainda não substituiu a versão publicada (em rascunho ou aprovada e ainda não publicada).
_Avoid_: Rascunho, pendente

**Aprovação**:
Registro de que uma versão exata foi autorizada a publicar, com origem (`humano`/`automatico`), responsável e regras avaliadas.
_Avoid_: Ok, liberação, revisão

**Publicação**:
Efeito de tornar uma versão aprovada visível no site público.
_Avoid_: Publish, deploy

**Execução (run)**:
Uma passagem do motor pelo pipeline para produzir conteúdo, com snapshot de configuração.
_Avoid_: Job, processamento, ciclo

**Tarefa (job)**:
Unidade de trabalho persistida na fila PostgreSQL e reservada por um worker.
_Avoid_: Task, mensagem

**Agendamento**:
Regra recorrente que cria tarefas sem duplicá-las entre instâncias.
_Avoid_: Cron, schedule

**ReservaOrcamento**:
Reserva conservadora de gasto feita antes de uma chamada paga, conciliada após a resposta.
_Avoid_: Saldo, crédito

**Orçamento**:
Limite configurável de gasto (diário/mensal) que bloqueia novas chamadas pagas.
_Avoid_: Cota, verba

**Conciliar**:
Encerrar uma ReservaOrcamento ligando-a à chamada que a consumiu (ou, se o custo for incerto, mantendo o valor estimado conservador).
_Avoid_: Fechar, liquidar

**EventoOrcamento**:
Registro imutável de um bloqueio de gasto por orçamento excedido.
_Avoid_: Log de orçamento

**AuditoriaAdministrativa**:
Registro imutável de ação administrativa (autor, ação, entidade, antes/depois, timestamp).
_Avoid_: Log de auditoria

**Curadoria (seção Destaques GitHub)**:
A seção pública cujo nome de trabalho é *Destaques*; o nome deve indicar curadoria própria, nunca ranking oficial do GitHub.
_Avoid_: GitHub Trending

**Radar (seção Hugging Face)**:
A seção pública de modelos do Hugging Face.
_Avoid_: Ranking oficial, trending
