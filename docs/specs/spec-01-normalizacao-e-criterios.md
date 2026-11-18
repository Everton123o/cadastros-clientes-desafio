# SPEC-01: Normalização, Critérios de Comparação e Pesos

Esta especificação detalha o comportamento de [`src/dedup/normalize.py`](../../src/dedup/normalize.py) e [`src/dedup/scoring.py`](../../src/dedup/scoring.py) a partir do perfil real de `data/clientes.csv`.

---

## 1. Perfil dos Dados de Entrada (`clientes.csv`)

- **Total de registros:** `3.000` (`site`: 1.006, `televendas`: 1.001, `loja`: 993)
- **Campos ausentes por origem:**

| Sistema | Total | Sem CPF | Sem E-mail | Sem Data de Nascimento |
|---|---:|---:|---:|---:|
| `site` | 1.006 | 75 (7,5%) | 0 (0,0%) | 0 (0,0%) |
| `loja` | 993 | 360 (36,3%) | 494 (49,7%) | 0 (0,0%) |
| `televendas` | 1.001 | 629 (62,8%) | 698 (69,7%) | 510 (50,9%) |
| **Total** | **3.000** | **1.064 (35,5%)** | **1.192 (39,7%)** | **510 (17,0%)** |

- **Formatos de telefone observados:** `(99) 99999-9999` (1.006), `99999999999` (767), `99999-9999` sem DDD (612), `99 99999-9999` (389) e `999999999` sem DDD (226).
- **Formatos de data:** `AAAA-MM-DD` (1.006) e `DD/MM/AAAA` (1.484), além de 9 casos com dia e mês invertidos entre sistemas.
- **Formatos de CPF:** `999.999.999-99` (931) e `99999999999` (1.005), sendo **40 CPFs com dígito verificador inválido** por erro de digitação de 1 dígito.

---

## 2. Regras de Normalização (`normalize.py`)

1. **`name_tokens(raw)`:**
   - Separa palavras coladas em `camelCase` (`"BeneditoDias"` $\to$ `"Benedito Dias"`).
   - Remove acentos (`NFKD`) e converte para maiúsculas.
   - Remove pontuação e filtra partículas (`DE`, `DA`, `DO`, `DOS`, `DAS`, `E`, `D`).
   - Preserva iniciais de 1 letra (`"Eduardo Q. R. Barbosa"` $\to$ `["EDUARDO", "Q", "R", "BARBOSA"]`).
   - Preserva sufixos geracionais (`JUNIOR`, `FILHO`, `NETO`, `SOBRINHO`) como último token para não confundir pais e filhos.
2. **`normalize_cpf(raw)` e `cpf_is_valid(cpf)`:**
   - Extrai apenas dígitos (`zfill(11)`).
   - Valida os dois dígitos verificadores pelo algoritmo oficial módulo 11 da Receita Federal (`n_cpf_valido`).
3. **`normalize_date(raw)`:**
   - Converte tanto `%Y-%m-%d` quanto `%d/%m/%Y` para ISO `YYYY-MM-DD`.
4. **`normalize_phone(raw)` e `phone_key(local)`:**
   - Remove máscara e prefixo `+55`; separa `(n_ddd, n_fone)` quando há 10 ou 11 dígitos, ou `(None, n_fone)` quando há 8 ou 9 dígitos.
   - Extrai `n_fone8` (últimos 8 dígitos), invariante à ausência de DDD e ao nono dígito móvel.

---

## 3. Cálculo da Pontuação (`scoring.py`)

Para cada par candidato $(A, B)$:

$$\text{pontos}(A, B) = p_{\text{cpf}} + p_{\text{nome}} + p_{\text{fone}} + p_{\text{email}} + p_{\text{nasc}} + p_{\text{local}}$$

### 3.1. Similaridade de Nome (`p_nome`)
- Calcula `tsr = fuzz.token_sort_ratio(nome_a, nome_b) / 100`.
- Calcula `estruturado = 0,4 * sim(primeiro_a, primeiro_b) + 0,4 * sim(ultimo_a, ultimo_b) + 0,2 * sim_meio`, onde:
  - Se um dos tokens tem comprimento 1 (inicial abreviada), `sim(a, b) = 1,0` se `a[0] == b[0]` e `0,0` caso contrário.
  - Caso contrário, `sim(a, b) = Levenshtein.normalized_similarity(a, b)`.
- `sim_nome = max(tsr, estruturado)`.
- Mapeamento linear em pontos:
  - Se `sim_nome >= 0,85`: $p_{\text{nome}} = 25 \times \frac{\text{sim\_nome} - 0{,}85}{0{,}15} \in [0, +25]$.
  - Se `sim_nome < 0,85`: $p_{\text{nome}} = \max\left(-25, -25 \times \frac{0{,}85 - \text{sim\_nome}}{0{,}25}\right) \in [-25, 0)$.

### 3.2. Exemplos Reais de Pontuação no Dataset

| Caso | Nome | CPF | Nasc. | Telefone | E-mail | Cidade | Total (Pontos) | Confiança |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mesmo CPF + nasc + tel + email | `+25` | `+40` | `+15` | `+20` | `+20` | `+3` | **`123,0`** | `100,0%` |
| CPF com 1 dígito errado (`quase`) + nasc + tel | `+25` | `+10` | `+15` | `+20` | `0` | `+3` | **`73,0`** | `99,9%` |
| Sem CPF (`televendas`), mesmo nome abreviado + mesmo tel + cidade | `+25` | `0` | `0` | `+20` | `0` | `+3` | **`48,0`** | `96,4%` |
| Sem CPF, mesmo nome + mesma data nasc + tel trocado | `+25` | `0` | `+15` | `-5` | `0` | `+3` | **`38,0`** | `86,5%` |
| Nome com typo (`GUTSAVO`) + mesmo tel + cidade | `+5,95` | `0` | `0` | `+20` | `0` | `+3` | **`28,95`** | `63,7%` |
| **Apenas mesmo nome + cidade, tel diferente, sem CPF/nasc/email** | `+25` | `0` | `0` | `-5` | `0` | `+3` | **`23,0`** | `42,9%` |
| Homônimos com CPFs e datas diferentes | `+25` | `-40` | `-20` | `-5` | `0` | `+3` | **`-37,0`** | `0,01%` |
