# ADR-0001: Estratégia de Blocking Multichave

- **Status:** Aceito
- **Data:** 2026-11-17

---

## Contexto

Comparar todos os $N = 3.000$ registros de `clientes.csv` contra todos exige:

$$\binom{3000}{2} = \frac{3000 \times 2999}{2} = 4.498.500 \text{ comparações}$$

Embora uma única chave de bloco (por exemplo, primeiro nome) reduzisse o número de pares, qualquer erro de digitação nesse campo (`"Maoel"` em vez de `"Manoel"`, `"BeneditoDias"` colado, ou `"Sveerino"`) faria o par verdadeiro nunca ser comparado (falso negativo irrecuperável já na etapa de blocking). Além disso, `35,5%` dos registros não têm CPF e `39,7%` não têm e-mail.

## Decisão

Adotamos **Multi-Pass Blocking (união de 5 chaves ortogonais)** implementado em [`src/dedup/blocking.py`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/src/dedup/blocking.py). Dois registros formam um par candidato se compartilharem **pelo menos uma** das 5 chaves abaixo:

| Chave de Bloco | Colunas Normalizadas | Pares Gerados no CSV | Falha que Cobre |
|---|---|---:|---|
| `cpf` | `n_cpf` (11 dígitos) | 488 | Erros severos no nome, troca de telefone/cidade |
| `fone8` | `n_fone8` (8 últimos dígitos) | 1.036 | Registros sem CPF/e-mail e sem DDD (`televendas`) |
| `email` | `n_email` (minúsculas) | 389 | Troca de telefone e ausência de CPF |
| `primeiro_cidade` | `(n_primeiro, n_cidade)` | 7.122 | Erros de digitação no último sobrenome (`"Teixiera"`, `"Lpoes"`) |
| `ultimo_cidade` | `(n_ultimo, n_cidade)` | 9.131 | Erros de digitação no primeiro nome (`"Maoel"`, `"Sveerino"`) |

## Consequências e Resultados Medidos

- **Pares possíveis:** `4.498.500`
- **Pares candidatos únicos (união das 5 chaves):** `14.947`
- **Redução do espaço de busca:** **99,668%** (fator de redução de `301x`)
- **Revocação do blocking na amostra de gabarito:** **100,00%** (`51/51` pares verdadeiros foram gerados por pelo menos uma chave)
- **Tempo de execução (normalização + blocking + pontuação):** **~0,8 segundo** em Python puro com pandas e RapidFuzz.
