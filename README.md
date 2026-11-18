# Deduplicação de Cadastros de Clientes

Pipeline de deduplicação probabilística para os **3.000 registros** de [`data/clientes.csv`](data/clientes.csv) (consolidados de `site`, `loja` e `televendas`), construído com **pandas**, **RapidFuzz**, **FastAPI**, **SQLAlchemy + MySQL**, **pytest** e frontend separado em **React + HTML + Tailwind CSS**.

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

### Pré-requisitos
- **Python 3.11+**
- **Docker + Docker Compose** (obrigatório para iniciar o MySQL)
- **Node.js 18+** *(opcional — apenas se quiser rodar o servidor de desenvolvimento Vite do frontend; o FastAPI já serve o bundle pronto em `frontend/dist/`)*

---

### 1. Criar e ativar o ambiente virtual Python

#### macOS e Linux (Terminal / bash / zsh)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Windows — PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
*(Se o PowerShell bloquear a execução de scripts, rode `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` antes de ativar.)*

#### Windows — Git Bash (MINGW64)
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

---

### 2. Configurar e iniciar o MySQL via Docker

#### macOS e Linux / Windows (Git Bash)
```bash
cp .env.example .env
docker compose up -d
```

#### Windows — PowerShell
```powershell
Copy-Item .env.example .env
docker compose up -d
```

O Compose cria o container `dedup-mysql` com MySQL 8.4, cria o banco e o usuário definidos no `.env`, publica a porta `3306` para a aplicação local e mantém os dados no volume nomeado `mysql_data`. O healthcheck aguarda o servidor MySQL responder. A aplicação Python roda fora do container e conecta em `localhost:3306` usando `DATABASE_URL`.

---

### 3. Rodar o Sistema (Pipeline, API FastAPI, Frontend e Testes)

Com o ambiente virtual `.venv` ativado, os comandos são iguais no **macOS**, **Linux** e **Windows**:

```bash
# 1. Rodar normalização, blocking, pontuação e agrupamento nos 3.000 registros
python -m src.dedup.pipeline rodar --limiar 25

# 2. Sortear a amostra estratificada de 100 registros (49 vizinhanças)
python -m src.dedup.pipeline amostra

# 3. Subir a API FastAPI + Frontend React/Tailwind
uvicorn src.api.main:app --reload --port 8000
```

Após subir o servidor, acesse no navegador:
- **Tela Web (React + Tailwind):** http://127.0.0.1:8000
- **Documentação interativa da API (Swagger):** http://127.0.0.1:8000/docs

*(Opcional)* Para rodar o servidor de desenvolvimento Vite do frontend separadamente em `http://localhost:5173`:
```bash
cd frontend
npm install
npm run dev
```

#### Avaliação por linha de comando e Testes
```bash
# Avaliar precisão, revocação, FP e FN em múltiplos limiares via CLI
python -m src.dedup.pipeline avaliar --limiar 25

# Rodar todos os testes automatizados (pipeline + endpoints FastAPI)
pytest
```

---

## Documentação Completa

- [`AGENTS.md`](AGENTS.md) — Diretrizes e regras para agentes e desenvolvedores
- [`docs/adr/0001-blocking-multichave.md`](docs/adr/0001-blocking-multichave.md)
- [`docs/adr/0002-pontuacao-evidencia-aditiva.md`](docs/adr/0002-pontuacao-evidencia-aditiva.md)
- [`docs/adr/0003-agrupamento-com-restricoes-e-limiar.md`](docs/adr/0003-agrupamento-com-restricoes-e-limiar.md)
- [`docs/adr/0004-persistencia-mysql-sqlalchemy.md`](docs/adr/0004-persistencia-mysql-sqlalchemy.md)
- [`docs/specs/spec-01-normalizacao-e-criterios.md`](docs/specs/spec-01-normalizacao-e-criterios.md)
- [`docs/specs/spec-02-amostragem-gabarito-e-metricas.md`](docs/specs/spec-02-amostragem-gabarito-e-metricas.md)
- [`docs/architecture/pipeline-deduplicacao.md`](docs/architecture/pipeline-deduplicacao.md)
- [`docs/rules/regras-de-negocio-e-engenharia.md`](docs/rules/regras-de-negocio-e-engenharia.md)
