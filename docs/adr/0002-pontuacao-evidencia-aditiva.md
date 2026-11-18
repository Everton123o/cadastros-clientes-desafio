# ADR-0002: Modelo de Pontuação por Evidência Aditiva e RapidFuzz

- **Status:** Aceito
- **Data:** 2026-11-17

---

## Contexto

Nos 3.000 registros consolidados de `site`, `loja` e `televendas`:
1. Uma média ponderada ingênua de todos os campos falha porque `televendas` omite CPF em 62,8% dos casos, e-mail em 69,7% e data de nascimento em 50,9%. Se campo ausente contar como zero numa média fixa, todo registro de `televendas` fica com nota artificialmente baixa.
2. Nomes possuem três tipos de variação simultâneos:
   - Partículas omitidas ou abreviadas (`"José da Silva"` x `"JOSE SILVA"` x `"José d. Silva"`).
   - Nomes do meio abreviados por inicial (`"Eduardo Q. R. Barbosa"` x `"Eduardo Queiroz Ramos Barbosa"`).
   - Erros de digitação (`"Manoel aBrros"`, `"CONCIECAO"`, `"BeneditoDias"`).
3. Existem **40 CPFs com dígito verificador inválido** que diferem por apenas 1 dígito ou transposição do CPF verdadeiro daquela pessoa (ex.: `61760040208` vs `617.600.402-07`), e **9 pares com dia e mês de nascimento invertidos** (`1997-07-09` vs `1997-09-07`).

## Decisão

Implementamos em [`src/dedup/scoring.py`](../../src/dedup/scoring.py) um **modelo aditivo de pesos de evidência** (inspirado em Fellegi-Sunter):

1. **Neutralidade de campos ausentes:** Se qualquer um dos dois registros tiver o campo vazio, a contribuição daquele critério é exatamente `0` ponto (não ajuda nem atrapalha).
2. **Similaridade de nome híbrida (`name_similarity`):**
   - Removemos acentos, pontuação e partículas (`DE`, `DA`, `DO`, `DOS`, `DAS`, `E`, `D`) e separamos `camelCase` (`"BeneditoDias"` $\to$ `"BENEDITO DIAS"`).
   - Calculamos o máximo entre:
     - `fuzz.token_sort_ratio` do RapidFuzz; e
     - Comparador estruturado (`_structured_name_sim`): `40%` primeiro nome + `40%` último nome + `20%` nomes do meio (onde token de 1 letra casa com `1.0` se for a inicial do nome por extenso, e demais tokens usam `Levenshtein.normalized_similarity`).
   - A similaridade $s \in [0, 1]$ é mapeada em pontos entre `-25` ($s \le 0{,}60$) e `+25` ($s = 1{,}00$), com ponto neutro `0` em $s = 0{,}85$.
3. **Pesos por critério (`Weights`):**

| Critério | Concordância Total | Concordância Parcial (Erro de Digitação) | Discordância | Campo Vazio |
|---|---:|---:|---:|---:|
| **CPF** | `+40` (igual) | `+10` (distância OSA $\le 1$) | `-40` (ambos válidos) / `-15` (um inválido) | `0` |
| **Nome** | até `+25` ($s = 1{,}0$) | `0` em $s = 0{,}85$ | até `-25` ($s \le 0{,}60$) | `0` |
| **Telefone (8 dígitos)** | `+20` (DDD igual ou ausente) | `+5` (DDD conflitante) | `-5` (pessoas trocam de linha) | `0` |
| **E-mail** | `+20` (igual) | `+10` (mesmo usuário antes do `@`) | `-5` | `0` |
| **Data de Nascimento** | `+15` (igual) | `+5` (dia/mês invertidos ou 1 dígito) | `-20` | `0` |
| **Localização** | `+3` (mesma cidade) | — | `-3` (outra cidade) / `-10` (outra UF) | `0` |

4. **Conversão para Confiança (0 a 100%):**
   $$\text{confiança} = \frac{100}{1 + \exp\left(-\frac{\text{pontos} - 25}{7}\right)}$$
   De modo que `25` pontos correspondem exatamente a **50% de confiança**, `35` pontos a **80,7%** e `48` pontos a **96,4%**.

## Consequências

- Registros de `televendas` sem CPF nem data de nascimento que tenham **nome compatível + mesmo telefone + mesma cidade** somam `25 + 20 + 3 = 48` pontos (`96,4%` de confiança).
- Pares que só coincidem em **nome + cidade** e têm **telefones diferentes** (sem CPF/data/e-mail em comum) somam `25 + 3 - 5 = 23` pontos (`42,9%` de confiança), ficando separados dos pares com evidência corroboradora.
