# Fluxo de criação do grafo

Este documento resume a fronteira operacional da abordagem `ontology-based`.

```mermaid
flowchart LR
    A[Receber e validar texto] --> B[Carregar prompts few-shot]
    B --> C[Descobrir ferramentas MCP permitidas]
    C --> D[Ollama decide chamadas de ferramenta]
    D --> E[Buscar itens e hierarquia na Wikidata]
    E --> D
    D --> F[Gerar RDF/Turtle]
    F --> G{RDF válido?}
    G -- sim --> H[Retornar RDF e auditoria MCP]
    G -- não, com tentativas --> D
    G -- não, sem tentativas --> I[Retornar HTTP 422]
```

## Fronteira da ablação

- O texto não passa por uma etapa local de extração de menções.
- O modelo escolhe quando e com quais argumentos consultar as ferramentas.
- A aplicação permite somente busca de itens e hierarquia de instância/subclasse.
- Declarações genéricas, relações diretas e SPARQL não fazem parte do perfil padrão.
- A aplicação executa o transporte MCP, registra a auditoria e valida o RDF.

O diagrama detalhado da interação está em `docs/seq/analyze.puml`.
