# ADR-0004: Persistência MySQL com SQLAlchemy

- **Status:** Aceito
- **Data:** 2026-11-17

---

## Contexto

O sistema precisa persistir:
1. Os 3.000 registros normalizados (`registros`).
2. O histórico de cada execução do pipeline com seus pesos, limiar e estatísticas (`execucoes`), os pares candidatos pontuados (`pares_candidatos`) e os grupos gerados (`grupos` e `grupo_membros`) para suportar a futura tela de revisão, aprovação/rejeição e desfazer fusão.
3. A amostra estratificada de 100 registros (`gabarito_amostra`) e os rótulos marcados manualmente (`gabarito_rotulos`).

A persistência do sistema usa **MySQL 8.4** com **SQLAlchemy 2.0**, iniciado localmente pelo Docker Compose.

## Decisão

1. Modelamos todas as tabelas usando o ORM declarativo do **SQLAlchemy 2.0** em [`src/storage/models.py`](../../src/storage/models.py), usando tipos portáveis (`Integer`, `Float`, `String`, `Boolean`, `DateTime`, `JSON`).
2. Fornecemos [`docker-compose.yml`](../../docker-compose.yml) com MySQL 8.4 configurado em `utf8mb4` e [`.env.example`](../../.env.example) com `DATABASE_URL=mysql+pymysql://dedup:dedup123@localhost:3306/dedup_clientes?charset=utf8mb4`.
3. Em [`src/storage/db.py`](../../src/storage/db.py), `get_engine()` lê `DATABASE_URL` do ambiente/arquivo `.env`. A configuração é obrigatória e deve usar um driver MySQL; sem ela, ou se for uma URL de outro banco, a aplicação falha com uma mensagem clara.

## Consequências

- É necessário ter Docker disponível, criar `.env` a partir de `.env.example` e iniciar `docker compose up -d` antes de executar o pipeline ou a API.
- O volume nomeado `mysql_data` mantém os dados entre reinicializações e recriações do container.
