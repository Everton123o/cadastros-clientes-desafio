# AGENTS.md — Diretrizes de Engenharia e Arquitetura

Este documento é a referência central para agentes de IA e desenvolvedores que atuam no projeto de **Deduplicação de Cadastros de Clientes** (`cadastros-clientes-desafio`).

---

## 1. Contexto e Objetivo do Sistema

O arquivo [`data/clientes.csv`](data/clientes.csv) reúne **3.000 cadastros** vindos de três sistemas legados (`site`, `loja` e `televendas`):
- A mesma pessoa aparece grafada como `"José da Silva"`, `"JOSE SILVA"`, `"José d. Silva"`, com erros de digitação (`"Manoel aBrros"`, `"BeneditoDias"`) ou iniciais abreviadas (`"Eduardo Q. R. Barbosa"`).
- Telefones aparecem com e sem DDD (`(82) 98431-2819`, `82984312819`, `98431-2819`).
- **35,5%** dos registros não têm CPF (`1.064`), **39,7%** não têm e-mail (`1.192`), **17,0%** não têm data de nascimento (`510`) e **40 CPFs** preenchidos têm dígito verificador inválido (erro de digitação em 1 dígito).
- Há **homônimos reais** (ex.: dois `"LUCAS VIEIRA"` em Recife com CPFs e datas de nascimento distintas) e **pais/filhos/netos** que compartilham telefone fixo/familiar (`"FERNANDO LOPES"` x `"FERNANDO LOPES FILHO"`).

**Política de decisão da equipe:** é melhor errar deixando duplicatas passarem (**falso negativo**) do que fundir duas pessoas diferentes (**falso positivo**). Por isso otimizamos precisão e $F_{0.5}$.

---

## 2. Estrutura do Projeto

```
cadastros-clientes-desafio/
├── AGENTS.md                  # Regras e contexto para agentes e engenheiros
├── README.md                  # Guia rápido de execução e resumo de resultados
├── docker-compose.yml         # Banco MySQL 8.4 (UTF-8)
├── .env.example               # Exemplo de configuração de DATABASE_URL
├── requirements.txt           # Dependências Python
├── data/
│   ├── clientes.csv           # 3.000 registros brutos de entrada
│   └── gabarito_provisorio.csv# Gabarito revisado na amostra estratificada de 100 registros
├── src/
│   ├── api/
│   │   └── main.py            # Backend REST FastAPI (/api/pipeline, /api/gabarito)
│   ├── dedup/
│   │   ├── normalize.py       # Normalização de nomes, CPF (módulo 11), datas, telefones
│   │   ├── blocking.py        # Blocking multichave (4,5M -> 14.947 pares, -99,67%)
│   │   ├── scoring.py         # Modelo aditivo de evidências + curva logística (0..100%)
│   │   ├── clustering.py      # Union-Find guloso com restrições (veto de conflitos)
│   │   ├── sampling.py        # Amostragem estratificada por vizinhanças (100 registros)
│   │   ├── evaluate.py        # Cálculo de VP, FP, FN, VN, Precisão, Revocação, F1, F0.5
│   │   └── pipeline.py        # CLI: rodar, amostra, importar-gabarito, avaliar
│   └── storage/
│       ├── models.py          # Tabelas SQLAlchemy (MySQL / SQLite)
│       └── db.py              # Persistência de execuções, grupos e gabarito
├── frontend/
│   ├── index.html             # HTML base do frontend
│   ├── package.json           # Configuração React + Vite + Tailwind CSS
│   ├── src/
│   │   └── App.jsx            # Tela React + Tailwind (marcação cega, amostra, métricas, pipeline)
│   └── dist/                  # Bundle pronto servido pelo FastAPI em http://localhost:8000
├── tests/
│   └── test_dedup.py          # Testes automatizados do pipeline e endpoints FastAPI
└── docs/
    ├── adr/                   # Architecture Decision Records (ADRs 0001 a 0004)
    ├── specs/                 # Especificações de critérios, pesos, amostra e métricas
    ├── architecture/          # Fluxo e arquitetura do pipeline
    └── rules/                 # Regras de engenharia e invariantes de domínio
```

---

## 3. Regras Inegociáveis para Agentes

1. **Campos vazios são neutros (0 ponto):** Nunca penalize um par porque um dos lados não tem CPF, data de nascimento ou e-mail.
2. **Não remover sufixos geracionais unilaterais:** `"FILHO"`, `"NETO"`, `"JUNIOR"` e `"SOBRINHO"` distinguem pais e filhos que moram na mesma cidade e compartilham telefone.
3. **Proibido transitividade cega:** O agrupamento (`clustering.py`) nunca deve unir dois subgrupos que possuam CPFs distintos (distância OSA > 1), datas de nascimento incompatíveis ou par com pontuação negativa.
4. **Marcação cega do gabarito:** O endpoint `GET /api/gabarito/amostra` ([`src/api/main.py`](src/api/main.py)) e a tela React ([`frontend/src/App.jsx`](frontend/src/App.jsx)) não devem exibir a pontuação nem a sugestão do algoritmo durante a rotulagem para não enviesar o avaliador humano.
5. **Banco de dados agnóstico via SQLAlchemy:** Todo acesso a dados passa por `src/storage/db.py` e funciona tanto em SQLite local (padrão sem `.env`) quanto em MySQL (`DATABASE_URL` no `.env`).

---

## 4. Mapa da Documentação (`docs/`)

- **ADRs (`docs/adr/`):**
  - [ADR-0001: Estratégia de Blocking Multichave](docs/adr/0001-blocking-multichave.md)
  - [ADR-0002: Modelo de Pontuação por Evidência Aditiva](docs/adr/0002-pontuacao-evidencia-aditiva.md)
  - [ADR-0003: Agrupamento com Restrições e Escolha de Limiar](docs/adr/0003-agrupamento-com-restricoes-e-limiar.md)
  - [ADR-0004: Persistência Híbrida MySQL / SQLite com SQLAlchemy](docs/adr/0004-persistencia-mysql-sqlalchemy.md)
- **Specs (`docs/specs/`):**
  - [SPEC-01: Normalização, Critérios de Comparação e Pesos](docs/specs/spec-01-normalizacao-e-criterios.md)
  - [SPEC-02: Amostragem Estratificada, Gabarito e Métricas](docs/specs/spec-02-amostragem-gabarito-e-metricas.md)
- **Arquitetura e Regras:**
  - [Arquitetura do Pipeline de Deduplicação](docs/architecture/pipeline-deduplicacao.md)
  - [Regras de Negócio e Engenharia](docs/rules/regras-de-negocio-e-engenharia.md)
