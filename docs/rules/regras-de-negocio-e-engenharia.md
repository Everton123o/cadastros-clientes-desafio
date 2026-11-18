# Regras Aplicadas no Projeto

Resumo consolidado das regras de domínio, estatística e engenharia aplicadas na deduplicação.

---

## 1. Regras de Identidade ("O que define a mesma pessoa")

1. **Dois CPFs válidos diferentes nunca são a mesma pessoa**, a menos que difiram por apenas 1 operação de edição/transposição (`OSA.distance <= 1`) acompanhada de alta concordância nos demais campos (erro de digitação em um dos sistemas).
2. **Datas de nascimento incompatíveis impedem a fusão**, exceto quando são inversão exata de dia e mês no mesmo ano (`DD/MM/AAAA` vs `MM/DD/AAAA`) ou diferem por 1 dígito.
3. **Sufixos familiares (`FILHO`, `NETO`, `JUNIOR`, `SOBRINHO`) diferenciam gerações:** Pais e filhos frequentemente residem na mesma cidade e compartilham telefone fixo ou familiar; por isso o sufixo nunca é descartado quando aparece em apenas um dos registros.
4. **Nome + cidade isoladamente não bastam quando o telefone diverge:** Dois registros que compartilham apenas nome e cidade, sem CPF, data de nascimento ou e-mail em comum e com telefones diferentes somam no máximo `23,0` pontos, ficando abaixo do limiar padrão (`25,0` pontos).
5. **Ausência de dado não é discordância:** Como `televendas` e `loja` omitem grande parte dos CPFs e e-mails, todo campo vazio recebe peso `0`.

---

## 2. Regras de Engenharia e Qualidade

- **Reprodutibilidade:** A amostragem estratificada usa semente fixa (`seed=42`) e todas as execuções do pipeline salvam os pesos e o limiar utilizados na tabela `execucoes`.
- **Separação de responsabilidades:**
  - `src/dedup/`: funções puras sobre DataFrames pandas (sem dependência de banco ou interface).
  - `src/storage/`: persistência SQLAlchemy compatível com MySQL e SQLite.
  - `src/api/`: endpoints REST FastAPI consumindo `src/dedup/` e `src/storage/`.
  - `frontend/`: aplicação web em React, HTML e Tailwind CSS consumindo a API FastAPI.
- **Testes automatizados:** Qualquer ajuste em normalização, pesos ou regras de veto deve passar por `pytest` (`tests/test_dedup.py`) e pela verificação de métricas (`python -m src.dedup.pipeline avaliar`).
