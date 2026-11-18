"""Blocking: gera pares candidatos sem comparar todos contra todos.

Um par só é comparado se os dois registros compartilham pelo menos uma
chave de bloco. Cada chave cobre uma forma de erro diferente, então um par
verdadeiro só escapa se errar em TODAS as chaves ao mesmo tempo:

- cpf        : mesmo CPF (só dígitos)                   -> pega nomes muito diferentes
- fone8      : mesmos 8 últimos dígitos do telefone     -> pega quem não tem CPF
- email      : mesmo e-mail                             -> pega quem trocou de telefone
- primeiro+cidade : mesmo primeiro nome na mesma cidade -> pega erro no sobrenome
- ultimo+cidade   : mesmo último sobrenome na mesma cidade -> pega erro no primeiro nome
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

BLOCK_KEYS: dict[str, tuple[str, ...]] = {
    "cpf": ("n_cpf",),
    "fone8": ("n_fone8",),
    "email": ("n_email",),
    "primeiro_cidade": ("n_primeiro", "n_cidade"),
    "ultimo_cidade": ("n_ultimo", "n_cidade"),
}


def candidate_pairs(df: pd.DataFrame, keys: dict[str, tuple[str, ...]] = BLOCK_KEYS) -> pd.DataFrame:
    """Devolve DataFrame com colunas id_a < id_b e `blocos` (chaves que geraram o par)."""
    found: dict[tuple[int, int], set[str]] = {}
    for key_name, cols in keys.items():
        sub = df.dropna(subset=list(cols))
        for _, group in sub.groupby(list(cols), sort=False):
            ids = sorted(group["id_registro"].tolist())
            if len(ids) < 2:
                continue
            for a, b in combinations(ids, 2):
                found.setdefault((a, b), set()).add(key_name)
    rows = [(a, b, ",".join(sorted(k))) for (a, b), k in found.items()]
    return pd.DataFrame(rows, columns=["id_a", "id_b", "blocos"]).sort_values(["id_a", "id_b"], ignore_index=True)


def blocking_stats(n_records: int, pairs: pd.DataFrame) -> dict:
    total = n_records * (n_records - 1) // 2
    n = len(pairs)
    per_key = {}
    if n:
        exploded = pairs["blocos"].str.split(",").explode()
        per_key = exploded.value_counts().to_dict()
    return {
        "pares_possiveis": total,
        "pares_candidatos": n,
        "reducao_pct": round(100 * (1 - n / total), 3) if total else 0.0,
        "pares_por_chave": per_key,
    }
