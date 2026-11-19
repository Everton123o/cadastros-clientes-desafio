# Roteiro da apresentação — Deduplicação de cadastros

## Ideia do projeto em uma frase

Temos cadastros de clientes vindos de sistemas diferentes. A mesma pessoa pode aparecer mais de uma vez, com o nome ou os dados escritos de formas diferentes. O projeto procura registros que provavelmente pertencem à mesma pessoa e tenta evitar juntar pessoas diferentes.

> **Exemplo simples:** uma loja registra “José da Silva” e o televendas registra “JOSE SILVA”. Pode ser a mesma pessoa, mas o sistema precisa olhar outros dados antes de decidir.

## Divisão entre as duas pessoas

| Apresentador | Parte | Arquivos principais |
|---|---|---|
| Pessoa 1 | Preparação dos dados, busca de candidatos e pontuação | `normalize.py`, `blocking.py`, `scoring.py` |
| Pessoa 2 | Formação dos grupos, avaliação e aplicação | `clustering.py`, `sampling.py`, `evaluate.py`, API, banco e frontend |

Uma boa transição entre as partes é: **“Agora que sabemos quais pares parecem promissores e quanto combinam, vamos ver como o sistema forma grupos com segurança e como conferimos os resultados.”**

---

# Pessoa 1 — Como o sistema encontra e compara possíveis duplicatas

## 1. O problema dos dados

O arquivo de entrada tem **3.000 cadastros**, vindos de `site`, `loja` e `televendas`. Cada sistema pode preencher campos diferentes e usar formatos diferentes. Por exemplo, há telefones com DDD, sem DDD, com parênteses ou hífen; também há nomes com acentos, abreviações e erros de digitação.

Há muitos campos incompletos: cerca de **1.064 registros não têm CPF**, **1.192 não têm e-mail** e **510 não têm data de nascimento**. Por isso, não dá para exigir que todos os campos estejam preenchidos.

## 2. Normalização: deixar os dados comparáveis

O programa começa em `src/dedup/normalize.py`. Normalizar significa transformar valores equivalentes para um formato comum, sem apagar os dados originais.

Exemplos:

- `José da Silva`, `JOSE SILVA` → tokens de nome equivalentes, sem acentos e sem partículas como “da”.
- `(82) 98431-2819` e `82984312819` → telefone separado em DDD e número.
- `98431-2819` → número local sem DDD; ainda pode ser comparado pelo final do telefone.
- `12.345.678-90` → CPF apenas com dígitos, e o sistema também verifica os dígitos verificadores.
- `07/09/1997` e `1997-09-07` → mesma data no formato ISO.

Os sufixos `Filho`, `Neto`, `Junior` e `Sobrinho` são preservados. Eles podem indicar pessoas diferentes. Por exemplo, “Fernando Lopes” e “Fernando Lopes Filho” podem morar na mesma casa e compartilhar um telefone.

**Como explicar:** “Antes de comparar, colocamos os dados em formatos parecidos. É como corrigir a formatação de uma lista para poder comparar as informações, sem tratar um campo vazio como prova contra a pessoa.”

## 3. Blocking: reduzir a quantidade de comparações

Se comparássemos cada cadastro com todos os outros, seriam **4.498.500 pares**. Isso é muita comparação e várias delas seriam claramente improváveis. O `blocking.py` cria grupos menores usando cinco chaves: CPF, telefone, e-mail, primeiro nome com cidade e último sobrenome com cidade.

Dois registros viram candidatos se compartilharem pelo menos uma dessas chaves. A união das chaves gera **14.947 pares candidatos**, uma redução de aproximadamente **99,67%**.

As chaves cobrem erros diferentes:

- Mesmo CPF: pode encontrar alguém cujo nome mudou bastante.
- Mesmo telefone: ajuda quando CPF ou e-mail está vazio.
- Mesmo e-mail: ajuda quando o telefone mudou.
- Mesmo primeiro nome e cidade: pode encontrar erro no sobrenome.
- Mesmo sobrenome e cidade: pode encontrar erro no primeiro nome.

**Exemplo:** “Manoel Barros” digitado como “Maoel Barros” pode não combinar exatamente pelo nome. Se os dois registros tiverem o mesmo sobrenome e cidade, ainda podem virar candidatos.

**Por que não comparar todos?** Porque o número de pares cresce muito rápido e a maioria não é relevante. **Por que não usar só CPF?** Porque mais de um terço dos cadastros está sem CPF e há CPFs digitados com erro.

## 4. Pontuação: somar evidências a favor e contra

No `scoring.py`, cada par candidato recebe pontos por vários sinais. Não existe uma decisão baseada só no nome.

| Evidência | Exemplo de efeito |
|---|---:|
| CPF igual | +40 |
| CPF com diferença pequena de digitação | +10 |
| Dois CPFs válidos diferentes | −40 |
| Nome idêntico/similar ao máximo | até +25 |
| Mesmo telefone local | +20 |
| Mesmo e-mail | +20 |
| Mesmo nascimento | +15 |
| Mesma cidade | +3 |
| Campo ausente em um dos lados | 0 |

Os valores são somados. Um CPF diferente pode ser evidência forte de que são pessoas distintas. Já um campo que não foi informado não ajuda nem atrapalha.

**Exemplos do projeto:**

1. Sem CPF, nome muito parecido (+25), mesmo telefone (+20) e mesma cidade (+3): **48 pontos**. É um conjunto de sinais favoráveis.
2. Apenas nome muito parecido (+25), mesma cidade (+3) e telefones diferentes (−5): **23 pontos**. Parece possível, mas pode ser homônimo; o limiar padrão é 25.
3. Homônimos com CPFs válidos diferentes (−40) e datas de nascimento diferentes (−20): mesmo que os nomes combinem, as evidências apontam fortemente para pessoas distintas.

Para comparar nomes, o código usa RapidFuzz e também compara partes do nome. Isso ajuda com erros como “BeneditoDias” (palavras coladas) e abreviações como “Eduardo Q. R. Barbosa”.

**Como explicar a confiança:** “A pontuação junta evidências. Depois, uma fórmula logística transforma a pontuação numa escala de confiança de 0 a 100%. Essa porcentagem é uma forma de apresentar o resultado do modelo; não significa que ele tenha sido treinado como um classificador probabilístico.”

---

# Pessoa 2 — Como os grupos são formados e como avaliamos o resultado

## 1. Agrupamento com proteção contra fusões erradas

O `clustering.py` transforma pares aprovados em grupos de registros que provavelmente são da mesma pessoa. Ele processa primeiro os pares com pontuação mais alta e usa Union-Find para manter os grupos.

Antes de juntar dois grupos, o algoritmo verifica conflitos. Por exemplo, evita unir grupos com CPFs incompatíveis ou com um par já conhecido que tenha evidência negativa ou data de nascimento divergente. Isso é importante porque uma relação indireta pode criar uma “ponte” incorreta.

**Exemplo:** A combina com B porque B não tem CPF. B também combina superficialmente com C. Mas A e C têm CPFs válidos diferentes. Um agrupamento simples por conexão poderia unir A, B e C; as restrições do projeto tentam impedir essa fusão.

Outro exemplo importante: “Fernando Lopes” e “Fernando Lopes Filho” podem compartilhar telefone por serem da mesma família. Preservar “Filho” no nome e conferir conflitos ajuda a não confundir parentes com a mesma pessoa.

## 2. Por que o limiar é conservador?

O limiar é a pontuação mínima para aceitar um par como possível união. O projeto usa **25 pontos** por padrão. A decisão de equipe é priorizar a precisão: é pior juntar duas pessoas diferentes do que deixar dois cadastros da mesma pessoa separados.

Na amostra rotulada de 100 registros, no limiar 25, o relatório mostra:

- **0 falsos positivos (FP):** nenhum par de pessoas diferentes foi unido na amostra.
- **7 falsos negativos (FN):** sete pares da mesma pessoa ficaram separados.
- **Precisão: 100%** e **revocação: 86,27%** nessa amostra.

O limiar 23 recuperou todos os pares verdadeiros da amostra, mas teve um falso positivo. Esse exemplo mostra o custo da escolha: baixar o limiar encontra mais duplicatas, mas também pode juntar homônimos.

**Como explicar as métricas:**

- Precisão: “Dos pares que o sistema decidiu juntar, quantos eram realmente a mesma pessoa?”
- Revocação: “Dos pares que eram realmente da mesma pessoa, quantos o sistema conseguiu juntar?”
- Falso positivo: juntou duas pessoas diferentes — o erro mais perigoso para este projeto.
- Falso negativo: deixou dois cadastros da mesma pessoa separados.
- F0.5: métrica que dá mais importância à precisão do que à revocação.

**Cuidado ao apresentar:** os números de zero falsos positivos e 86,27% de revocação foram medidos na amostra de 100 registros rotulados, não são uma garantia de que não haja erro nos 3.000 registros.

## 3. Gabarito e amostra estratificada

O `sampling.py` seleciona 100 registros em 49 vizinhanças. A amostra inclui casos prováveis, casos ambíguos, homônimos e registros isolados. Assim, temos exemplos úteis para avaliar tanto duplicatas quanto o risco de fusões erradas.

Uma amostra aleatória simples poderia trazer quase nenhum par duplicado, porque estamos escolhendo só 100 entre 3.000 registros. Selecionar vizinhanças aumenta a chance de avaliar pares relacionados.

A pessoa que marca o gabarito vê os dados originais, mas não deve ver a pontuação ou a sugestão do algoritmo. Isso é a **marcação cega** e reduz o risco de a sugestão influenciar a resposta humana.

## 4. Como as partes do sistema se conectam

- **FastAPI (`src/api/main.py`):** oferece endpoints para rodar o pipeline, consultar a amostra e obter métricas.
- **React + Tailwind (`frontend/`):** mostra as telas para rotular registros, consultar resultados e observar métricas.
- **MySQL + SQLAlchemy (`src/storage/`):** guarda execuções, pares avaliados, grupos e rótulos.
- **Docker Compose:** facilita iniciar o MySQL localmente com uma configuração conhecida.

**Por que separar interface e API?** A interface cuida da interação com a pessoa; a API concentra as operações e regras do backend. Assim, a tela pode pedir dados sem reimplementar o algoritmo.

**Por que MySQL e SQLAlchemy?** O projeto precisa guardar dados relacionados e o histórico das execuções. O banco relacional organiza essas relações; o SQLAlchemy mapeia as tabelas para objetos Python e centraliza o acesso ao banco.

---

# Resumo para encerrar

“Nosso processo começa padronizando os dados, reduz os milhões de comparações possíveis para uma lista pequena de candidatos e soma evidências para decidir quais pares são parecidos. Depois, forma grupos com regras para evitar conflitos e mede os erros usando um gabarito humano. Priorizamos não juntar pessoas diferentes, mesmo que isso deixe algumas duplicatas sem detectar.”

# Perguntas que podem aparecer

### Por que não usar igualdade exata nos nomes?

Porque os mesmos dados aparecem com acentos, abreviações, erros de digitação e palavras coladas. Igualdade exata perderia pares como “José da Silva” e “JOSE SILVA”.

### Por que não juntar todos os nomes parecidos?

Porque existem homônimos e parentes com nomes semelhantes. O sistema usa outros campos e vetos para reduzir o risco de fusão indevida.

### Se falta CPF, isso significa que não é a mesma pessoa?

Não. Campo vazio vale zero ponto. O sistema usa as evidências que existem, como nome, telefone, e-mail, nascimento e cidade.

### Por que aceitar falsos negativos?

Um falso negativo mantém dois cadastros da mesma pessoa separados, o que pode ser corrigido numa revisão. Um falso positivo mistura os dados de pessoas diferentes, e isso pode causar problemas mais sérios.

### A confiança de 96% garante que o par está correto?

Não. É o valor produzido pela curva logística a partir da pontuação. A avaliação contra o gabarito ajuda a verificar o comportamento do método; o resultado medido depende da amostra rotulada.

### O que vocês fariam para melhorar?

Rotular mais casos, principalmente os ambíguos e os homônimos, revisar pares que ficaram abaixo do limiar e recalibrar os pesos com base nos erros observados. Também seria importante medir o resultado em novos dados antes de usar o método em produção.
