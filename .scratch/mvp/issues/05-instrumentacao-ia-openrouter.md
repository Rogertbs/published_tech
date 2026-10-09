# 05: Camada de instrumentação de IA + provedor OpenRouter free (texto)

**What to build:** Uma interface única de IA por onde passa toda chamada, com registro por chamada correlacionado a execução/etapa/conteúdo; provedor/modelo, tokens de entrada/saída/cache, duração, status, request id externo quando houver e origem do custo. Consumo desconhecido não é zero. No dev, provedor de texto via **OpenRouter** usando apenas modelos **full free**.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Chamada de texto via OpenRouter free é registrada com todos os campos mínimos.
- [ ] Falha, timeout e resultado incerto são registrados com status próprio.
- [ ] Consumo desconhecido é marcado como desconhecido (nunca zero).
- [ ] Nenhuma credencial aparece em logs ou no frontend.
