# ADR-0003: Agrupamento com Restrições e Escolha de Limiar

- **Status:** Aceito
- **Data:** 2026-11-17

---

## Contexto

Mesmo com uma boa pontuação par-a-par, dois problemas clássicos surgem ao formar grupos de registros:
1. **Encadeamento transitivo (*single-linkage chaining*):** Em cidades grandes, homônimos como `"LUCAS VIEIRA"` (Recife) ou `"DANIEL PACHECO LOPES DE SOUZA"` (Salvador) possuem registros de duas pessoas distintas (com CPFs e datas de nascimento diferentes), além de um terceiro registro do `televendas` sem CPF nem data de nascimento. Se usarmos componente conexo puro, o registro incompleto funciona como "ponte" e funde as duas pessoas distintas num único grupo.
2. **Escolha do limiar sob custo assimétrico de erro:** Fundir duas pessoas diferentes (falso positivo) corrompe histórico financeiro e cadastral; deixar uma duplicata passar (falso negativo) apenas mantém dois cadastros até uma revisão futura. A equipe definiu que **é melhor errar deixando duplicatas passarem**.

## Decisão

1. **Union-Find Guloso com Veto de Conflitos ([`src/dedup/clustering.py`](file:///c:/Users/pedro/Desktop/cod/cadastros-clientes-desafio/src/dedup/clustering.py)):**
   - Ordenamos os pares candidatos com `pontos >= limiar` da **maior para a menor pontuação**.
   - Dois grupos $G_a$ e $G_b$ **são impedidos de se fundir (veto)** se:
     - possuírem CPFs com distância de edição (OSA) $> 1$; ou
     - existir qualquer par $(x, y) \in G_a \times G_b$ com `pontos < 0`, `nasc == "diferente"` ou `cpf` divergente.
   - Como as arestas fortes (`63` a `113` pontos) são unidas primeiro, o registro sem CPF se junta ao seu par verdadeiro (que tem CPF/data) antes das arestas fracas (`23` pontos), herdando o CPF do grupo e bloqueando automaticamente a fusão com o homônimo.

2. **Limiar Escolhido: `25,0` pontos (`50%` de confiança) — com opção ultraconservadora em `35,0` pontos (`80,7%`):**
   - Na amostra estratificada de 100 registros (51 pares verdadeiros e 4.899 pares negativos):

| Limiar (pontos) | Confiança (%) | VP | FP | FN | VN | Precisão | Revocação | $F_1$ | $F_{0.5}$ |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `20` | 32,9% | 51 | 1 | 0 | 4.898 | 98,08% | 100,00% | 99,03% | 98,46% |
| `23` | 42,9% | 51 | 1 | 0 | 4.898 | 98,08% | 100,00% | 99,03% | 98,46% |
| **`25` (Recomendado)** | **50,0%** | **44** | **0** | **7** | **4.899** | **100,00%** | **86,27%** | **92,63%** | **96,92%** |
| `28` | 60,5% | 43 | 0 | 8 | 4.899 | 100,00% | 84,31% | 91,49% | 96,41% |
| `30` | 67,1% | 42 | 0 | 9 | 4.899 | 100,00% | 82,35% | 90,32% | 95,89% |
| **`35` (Conservador)** | **80,7%** | **39** | **0** | **12** | **4.899** | **100,00%** | **76,47%** | **86,67%** | **94,20%** |
| `40` | 89,5% | 37 | 0 | 14 | 4.899 | 100,00% | 72,55% | 84,09% | 92,96% |
| `50` | 97,3% | 26 | 0 | 25 | 4.899 | 100,00% | 50,98% | 67,53% | 83,87% |

## Consequências

- Com **`limiar = 25,0` pontos**, o sistema exige que um par com telefones diferentes tenha **pelo menos mais um campo corroborando o nome** (CPF igual/quase, data de nascimento igual/invertida ou e-mail igual/mesmo usuário).
- Resultado nos 3.000 registros completos: **757 grupos** (reunindo **1.745 registros**) e **2.012 clientes únicos estimados**, com **0 falsos positivos** medidos na amostra estratificada.
