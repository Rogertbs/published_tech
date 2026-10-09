# Aprovação humana obrigatória para publicar no MVP

O motor pode executar todo o pipeline de forma automática (coleta, seleção, evidências, redação, revisão e ilustração) e produzir rascunhos, mas **nada é publicado sem aprovação humana de uma versão exata**. O flag `automatico` controla apenas a execução do pipeline, nunca a publicação. Decidimos isso porque conteúdo gerado por IA pode conter erro factual ou risco editorial/jurídico, e a publicação é um efeito público difícil de reverter.

**Alternativas consideradas:** publicação automática por `automatico = true` (rejeitada no MVP; tratada como evolução); revisão por segundo modelo como autorização (rejeitada: concordância de modelo não comprova fatos — a revisão usa evidências, e a decisão de publicar é humana).

**Consequências:** o modelo registra origem da aprovação (`humano`/`automatico`) e as regras avaliadas, preparando a evolução sem alterar o comportamento inicial. Dispensar a aprovação humana exige novo ADR.
