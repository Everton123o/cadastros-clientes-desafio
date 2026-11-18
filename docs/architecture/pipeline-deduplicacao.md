# Arquitetura do Pipeline de Deduplicação

Este documento apresenta o fluxo de dados e componentes da Fase 1 (Pipeline de Deduplicação, Persistência e Avaliação por Gabarito).

---

## Diagrama do Fluxo do Pipeline

```mermaid
flowchart LR
    CSV["data/clientes.csv\n(3.000 registros)"] --> NORM["1. Normalização\nsrc/dedup/normalize.py\nNomes, CPF (mód. 11),\nDatas ISO, Fone8"]
    NORM --> BLOCK["2. Blocking Multichave\nsrc/dedup/blocking.py\n4.498.500 -> 14.947 pares\n(-99,67%)"]
    BLOCK --> SCORE["3. Pontuação (RapidFuzz)\nsrc/dedup/scoring.py\nEvidência aditiva + logística\n(pontos e confiança 0..100%)"]
    SCORE --> CLUST["4. Agrupamento Restrito\nsrc/dedup/clustering.py\nUnion-Find guloso com\nveto de CPF e nascimento"]
    CLUST --> DB[("MySQL 8.4 via Docker\nsrc/storage/models.py\nregistros, execucoes,\npares_candidatos, grupos")]
    SCORE --> SAMP["5. Amostra Estratificada\nsrc/dedup/sampling.py\n100 registros (49 vizinhanças)"]
    SAMP --> API["6. API REST FastAPI\nsrc/api/main.py\n/api/gabarito & /api/pipeline"]
    API <--> UI["7. Frontend Separado\nfrontend/ (React + HTML + Tailwind)\nMarcação cega e painel de métricas"]
    API --> DB
    DB --> EVAL["8. Avaliação de Limiares\nsrc/dedup/evaluate.py\nVP, FP, FN, Precisão,\nRevocação, F1 e F0.5"]
```

---

## Modelo de Dados (`src/storage/models.py`)

```mermaid
erDiagram
    REGISTROS ||--o{ PARES_CANDIDATOS : "id_a / id_b"
    EXECUCOES ||--o{ PARES_CANDIDATOS : "contém"
    EXECUCOES ||--o{ GRUPOS : "gera"
    GRUPOS ||--o{ GRUPO_MEMBROS : "possui"
    REGISTROS ||--o{ GRUPO_MEMBROS : "participa"
    REGISTROS ||--o| GABARITO_AMOSTRA : "sorteado em"
    REGISTROS ||--o| GABARITO_ROTULOS : "rotulado em"
```
