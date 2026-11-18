# ADR-0004: Persistência com SQLAlchemy (MySQL via Docker e Fallback SQLite)

- **Status:** Aceito
- **Data:** 2026-11-17

---

## Contexto

O sistema precisa persistir:
1. Os 3.000 registros normalizados (`registros`).
2. O histórico de cada execução do pipeline com seus pesos, limiar e estatísticas (`execucoes`), os pares candidatos pontuados (`pares_candidatos`) e os grupos gerados (`grupos` e `grupo_membros`) para suportar a futura tela de revisão, aprovação/rejeição e desfazer fusão.
3. A amostra estratificada de 100 registros (`gabarito_amostra`) e os rótulos marcados manualmente (`gabarito_rotulos`).

A arquitetura alvo utiliza **MySQL 8.4** com **SQLAlchemy 2.0**, mas desenvolvedores e avaliadores podem rodar o projeto em máquinas sem Docker instalado no momento da execução.

## Decisão

1. Modelamos todas as tabelas usando o ORM declarativo do **SQLAlchemy 2.0** em [`src/storage/models.py`](../../src/storage/models.py), usando tipos portáveis (`Integer`, `Float`, `String`, `Boolean`, `DateTime`, `JSON`).
2. Fornecemos [`docker-compose.yml`](../../docker-compose.yml) com MySQL 8.4 configurado em `utf8mb4` e [`.env.example`](../../.env.example) com `DATABASE_URL=mysql+pymysql://dedup:dedup123@localhost:3306/dedup_clientes?charset=utf8mb4`.
3. Em [`src/storage/db.py`](../../src/storage/db.py), `get_engine()` lê `DATABASE_URL` do ambiente/arquivo `.env` e, caso não esteja definida, utiliza automaticamente `sqlite:///data/dedup.db`.

## Consequências

- Zero fricção para rodar o pipeline, a API FastAPI e o frontend React/Tailwind imediatamente (`sqlite:///data/dedup.db`), bastando criar o `.env` e subir `docker compose up -d` para apontar para o MySQL sem mudar uma linha de código.
