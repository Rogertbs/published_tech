# 07: Configuração e prompts versionados + precedência

**What to build:** Versionar configurações e prompts com comparação, restauração e teste em **prévia privada** (custos separados e contabilizados); precedência em que regras obrigatórias do sistema são protegidas e seção/agente podem sobrescrever padrões gerais apenas em campos permitidos; snapshot da configuração por execução; texto de fonte tratado como dado não confiável; auditoria das alterações.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] Criar/editar versão de prompt e testar em prévia privada sem publicar.
- [ ] Alterar config não modifica histórico; cada execução registra a versão efetiva usada.
- [ ] Campo protegido (evidência, bloqueios, orçamento) não é sobrescrito; campo permitido é.
- [ ] Prompt vazio é rejeitado; texto de fonte não é interpretado como instrução.
