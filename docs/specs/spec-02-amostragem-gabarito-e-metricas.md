# SPEC-02: Amostragem Estratificada, Gabarito e Métricas de Avaliação

Esta especificação documenta o desenho da amostra de 100 registros ([`src/dedup/sampling.py`](../../src/dedup/sampling.py)), a API FastAPI ([`src/api/main.py`](../../src/api/main.py)), o frontend em React + HTML + Tailwind CSS ([`frontend/src/App.jsx`](../../frontend/src/App.jsx)) e o cálculo de precisão e revocação ([`src/dedup/evaluate.py`](../../src/dedup/evaluate.py)).

---

## 1. Por que Amostragem Estratificada por Vizinhanças?

Se escolhêssemos $n = 100$ registros de forma puramente aleatória dentre $N = 3.000$:
- A fração de pares que caem juntos na amostra é $\approx (100/3000)^2 \approx 0{,}11\%$.
- Como o dataset inteiro possui cerca de $1.100$ pares duplicados, uma amostra aleatória simples conteria apenas **1 par duplicado verdadeiro** em média, tornando impossível medir revocação e precisão com significância estatística.

Por isso, [`stratified_sample`](../../src/dedup/sampling.py#L40-L108) sorteia **vizinhanças completas** (componentes conexos de pares com `pontos >= 0`) divididas em 4 estratos:

| Estrato | Critério de Seleção | Registros na Amostra | Papel na Avaliação |
|---|---|---:|---|
| `provavel` | Vizinhanças sem conflito interno e com par $\ge 60$ pontos | 31 | Mede revocação em duplicatas claras (múltiplos campos) |
| `zona_cinza` | Vizinhanças sem conflito interno e com melhor par entre $15$ e $60$ pontos | 33 | Testa a fronteira de decisão do limiar (`23` a `48` pontos) |
| `homonimo` | Vizinhanças com CPFs/datas divergentes (incluindo pais/filhos) ou nomes idênticos com score $< 0$ | 24 | Testa resistência a **falsos positivos** e encadeamento |
| `isolado` | Registros sem nenhum par com pontuação $\ge 0$ | 12 | Garante que registros únicos não sejam agrupados indevidamente |
| **Total** | **49 vizinhanças** | **100** | **4.950 pares avaliados ($\binom{100}{2}$), sendo 51 positivos e 4.899 negativos** |

---

## 2. API FastAPI e Frontend React + Tailwind (`src/api/main.py` e `frontend/`)

Servida com `uvicorn src.api.main:app --reload --port 8000` (e em modo de desenvolvimento Vite com `cd frontend && npm run dev` na porta `5173`), a interface React + Tailwind possui quatro abas:
1. **Marcar Gabarito (Cego):** Consome `GET /api/gabarito/amostra` e `PUT /api/gabarito/rotulos`. Exibe uma vizinhança por vez contendo apenas os campos originais do CSV (`id_registro`, `nome`, `cpf`, `data_nascimento`, `telefone`, `email`, `cidade`, `uf`, `sistema_origem`), **sem revelar estrato, pontuação nem sugestão do sistema**. O operador atribui o mesmo identificador na coluna `pessoa` aos registros que pertencem ao mesmo indivíduo.
2. **Amostra Estratificada (100):** Tabela consolidada dos 100 registros com busca instantânea por nome, CPF, cidade ou rótulo.
3. **Métricas (Precisão & Revocação):** Consome `GET /api/gabarito/avaliar?limiar=X` e calcula em tempo real a revocação do blocking, a tabela de varredura de limiares (Precisão, Revocação, $F_1$, $F_{0.5}$, VP, FP, FN) e a inspeção detalhada dos pares de Falsos Positivos e Falsos Negativos.
4. **Pipeline & Blocking (3.000):** Consome `GET /api/pipeline/resumo` e `POST /api/pipeline/rodar` para disparar execuções completas nos 3.000 registros.

---

## 3. Fórmulas das Métricas Par-a-Par (`evaluate.py`)

Seja $P$ o conjunto de pares $(a, b)$ com $a < b$ na amostra que foram colocados no **mesmo grupo** pelo sistema, e $G$ o conjunto de pares $(a, b)$ que possuem o **mesmo rótulo `pessoa`** no gabarito:

- $\text{VP} = |P \cap G|$ (fidelidade: mesma pessoa agrupada corretamente)
- $\text{FP} = |P \setminus G|$ (erro crítico: duas pessoas diferentes fundidas)
- $\text{FN} = |G \setminus P|$ (erro tolerável: mesma pessoa deixada separada)
- $\text{VN} = \binom{100}{2} - \text{VP} - \text{FP} - \text{FN}$

$$\text{Precisão} = \frac{\text{VP}}{\text{VP} + \text{FP}}, \qquad \text{Revocação} = \frac{\text{VP}}{\text{VP} + \text{FN}}, \qquad F_{\beta} = (1 + \beta^2)\frac{\text{Precisão} \times \text{Revocação}}{\beta^2 \cdot \text{Precisão} + \text{Revocação}}$$

Usamos $F_{0.5}$ ($\beta = 0{,}5$, que atribui o dobro de importância à precisão em relação à revocação) para refletir a diretriz da equipe de priorizar zero falsos positivos.
