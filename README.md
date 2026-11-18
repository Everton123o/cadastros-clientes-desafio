# Deduplicação de Cadastros de Clientes

Pipeline de deduplicação probabilística para os **3.000 registros** de [`data/clientes.csv`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/data/clientes.csv) (consolidados de `site`, `loja` e `televendas`), construído com **pandas**, **RapidFuzz**, **FastAPI**, **SQLAlchemy (MySQL / SQLite)**, **pytest** e frontend separado em **React + HTML + Tailwind CSS**.

---

## Resumo das Respostas à Pergunta Central

1. **Redução do espaço de busca (Blocking):**
   - Comparar todos contra todos gera $\binom{3000}{2} = 4.498.500$ pares.
   - Com **5 chaves de blocking em união** (`cpf`, `fone8`, `email`, `primeiro_nome + cidade`, `ultimo_sobrenome + cidade`), avaliamos apenas **14.947 pares** (**redução de 99,67%**), mantendo **100% de revocação do blocking** na amostra de gabarito (51/51 pares verdadeiros gerados) em **~0,8 segundo**.
2. **Critérios e Pesos (Evidência Aditiva):**
   - Campos vazios valem `0` (neutros).
   - **CPF:** `+40` (igual), `+10` (1 dígito trocado/transposto via OSA), `-40` (dois CPFs válidos diferentes), `-15` (diferente com um inválido).
   - **Nome (RapidFuzz `token_sort_ratio` + comparador estruturado com suporte a iniciais):** de `-25` a `+25` pontos.
   - **Telefone (8 últimos dígitos):** `+20` (igual), `+5` (DDD conflitante), `-5` (diferente).
   - **E-mail:** `+20` (igual), `+10` (mesmo usuário antes do `@`), `-5` (diferente).
   - **Data de nascimento:** `+15` (igual), `+5` (dia/mês invertidos ou 1 dígito), `-20` (diferente).
   - **Localização:** `+3` (mesma cidade), `-3` (cidade diferente), `-10` (UF diferente).
3. **Limiar escolhido e efeito em FP / FN (política: *melhor deixar duplicata passar*):**
   - **Limiar recomendado: `25,0` pontos** (`50%` de confiança na curva logística), que exige **pelo menos um identificador corroborando o nome** quando o telefone diverge:
     - **Falsos Positivos (FP): `0` (Precisão = `100,00%`)**
     - **Falsos Negativos (FN): `7` (Revocação = `86,27%`, $F_1 = 92,63\%$, $F_{0.5} = 96,92\%$)**
   - Abaixo de `25` pontos (ex.: `23` pontos, onde apenas `nome + cidade` coincidem e o telefone é diferente), a revocação vai a `100%`, mas surgem **falsos positivos de homônimos** (`Precisão = 98,08%`).
   - Se a equipe preferir um corte ainda mais conservador (`35,0` pontos / `80,7%` de confiança), mantém **0 FP (`100%` de precisão)** com **12 FN (`76,47%` de revocação)**.

---

## Como Executar

### 1. Ambiente Python
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Banco de Dados (SQLite por padrão ou MySQL via Docker)
Sem arquivo `.env`, o sistema usa automaticamente SQLite em `data/dedup.db`. Para usar o MySQL via Docker:
```powershell
docker compose up -d
Copy-Item .env.example .env
```

### 3. Comandos do Pipeline
```powershell
# 1. Rodar normalização, blocking, pontuação e agrupamento nos 3.000 registros
python -m src.dedup.pipeline rodar --limiar 25

# 2. Sortear a amostra estratificada de 100 registros (49 vizinhanças)
python -m src.dedup.pipeline amostra

# 3. Subir a API FastAPI + Frontend React/Tailwind (http://localhost:8000)
uvicorn src.api.main:app --reload --port 8000

# (Opcional) Rodar o servidor de desenvolvimento Vite do frontend em http://localhost:5173
cd frontend && npm install && npm run dev

# 4. Avaliar precisão, revocação, FP e FN em múltiplos limiares via CLI
python -m src.dedup.pipeline avaliar --limiar 25

# 5. Rodar testes automatizados (pipeline + endpoints FastAPI)
pytest
```

---

## Documentação Completa

- [`AGENTS.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/AGENTS.md) — Diretrizes e regras para agentes e desenvolvedores
- [`docs/adr/0001-blocking-multichave.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/adr/0001-blocking-multichave.md)
- [`docs/adr/0002-pontuacao-evidencia-aditiva.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/adr/0002-pontuacao-evidencia-aditiva.md)
- [`docs/adr/0003-agrupamento-com-restricoes-e-limiar.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/adr/0003-agrupamento-com-restricoes-e-limiar.md)
- [`docs/adr/0004-persistencia-mysql-sqlalchemy.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/adr/0004-persistencia-mysql-sqlalchemy.md)
- [`docs/specs/spec-01-normalizacao-e-criterios.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/specs/spec-01-normalizacao-e-criterios.md)
- [`docs/specs/spec-02-amostragem-gabarito-e-metricas.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/specs/spec-02-amostragem-gabarito-e-metricas.md)
- [`docs/architecture/pipeline-deduplicacao.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/architecture/pipeline-deduplicacao.md)
- [`docs/rules/regras-de-negocio-e-engenharia.md`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/docs/rules/regras-de-negocio-e-engenharia.md)
