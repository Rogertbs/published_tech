# Render-once-and-cache para o site público

O site público é **estático com cache persistente**: a página é gerada uma única vez (Astro sob demanda lendo a API Django) e o HTML resultante é guardado no Redis/arquivo **sem TTL**. Ele só é descartado quando o conteúdo muda — publicar, editar, trocar a versão publicada, retirar ou (re)gerar uma lista. Primeiras requisições após uma invalidação regeneram a página; as demais são servidas do cache. Escolhemos isso porque o conteúdo muda por ação editorial, não por relógio, e um rebuild estático a cada publicação seria caro e lento.

**Alternativas consideradas:** rebuild estático a cada publicação (rejeitado: rebuild integral e lento); SSR a cada requisição sem cache persistente (rejeitado: trabalho repetido sem ganho, já que o conteúdo é estável até um update).

**Consequências:** a invalidação é o ponto crítico — deve alcançar somente as páginas afetadas e também caches HTTP, e conteúdo privado (rascunho/prévia) nunca entra no cache. O corretor de TTL não existe por design; a consistência é orientada a eventos de publicação/edição/retirada.
