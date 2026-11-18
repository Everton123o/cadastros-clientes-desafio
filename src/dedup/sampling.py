"""Amostra estratificada de 100 registros para o gabarito manual.

Uma amostra aleatória simples de 100 em 3.000 registros teria pouquíssimos
pares duplicados dentro dela, e precisão/revocação ficariam sem base. Por
isso a amostra é feita por vizinhanças: grupos inteiros de registros
ligados por pares candidatos entram juntos, assim os pares duplicados
ficam dentro da amostra.

Estratos (cotas em número de registros):
- provavel   : vizinhança com par >= 60 pontos e sem conflito interno
- zona_cinza : vizinhança com melhor par entre 15 e 60 pontos (onde o limiar decide)
- homonimo   : vizinhança com homônimos (CPFs/datas divergentes ou só nome+cidade iguais)
- isolado    : registro sem nenhum par com pontuação >= 0
"""
from __future__ import annotations

import random

import pandas as pd

QUOTAS = {"provavel": 32, "zona_cinza": 34, "homonimo": 24, "isolado": 10}
MAX_NEIGHBORHOOD = 6
LOOSE_POINTS = 0.0


def _components(ids: list[int], edges: list[tuple[int, int]]) -> list[list[int]]:
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    comps: dict[int, list[int]] = {}
    for i in ids:
        comps.setdefault(find(i), []).append(i)
    return [sorted(c) for c in comps.values()]


def stratified_sample(df: pd.DataFrame, scored: pd.DataFrame, size: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    loose = scored[scored["pontos"] >= LOOSE_POINTS]
    linked = sorted(set(loose["id_a"]) | set(loose["id_b"]))
    comps = [c for c in _components(linked, list(zip(loose["id_a"], loose["id_b"]))) if len(c) <= MAX_NEIGHBORHOOD]

    best = {}
    has_conflict: set[int] = set()
    for a, b, p, cpf_s, nasc_s in zip(loose["id_a"], loose["id_b"], loose["pontos"], loose["cpf"], loose["nasc"]):
        best[a] = max(best.get(a, -1e9), p)
        best[b] = max(best.get(b, -1e9), p)
        if cpf_s == "diferente" or nasc_s == "diferente":
            has_conflict.add(a)
            has_conflict.add(b)

    # Também detecta componentes que têm 2+ CPFs válidos distintos
    cpf_of = {r: c for r, c, ok in zip(df["id_registro"], df["n_cpf"], df["n_cpf_valido"]) if ok}

    pools: dict[str, list[list[int]]] = {"provavel": [], "zona_cinza": [], "homonimo": [], "isolado": []}
    for c in comps:
        top = max(best[i] for i in c)
        cpfs = {cpf_of[i] for i in c if i in cpf_of}
        if len(cpfs) > 1 or any(i in has_conflict for i in c):
            pools["homonimo"].append(c)
        elif top >= 60:
            pools["provavel"].append(c)
        elif top >= 15:
            pools["zona_cinza"].append(c)

    isolated = set(df["id_registro"]) - set(linked)
    homon = scored[(scored["sim_nome"] >= 0.90) & (scored["pontos"] < 0)]
    for a, b in zip(homon["id_a"], homon["id_b"]):
        if a in isolated and b in isolated:
            pools["homonimo"].append([a, b])
    pools["isolado"] = [[i] for i in sorted(isolated)]

    # Em zona_cinza, prioriza mistura entre faixa baixa (15..30) e média (30..60)
    low_gray = [c for c in pools["zona_cinza"] if max(best[i] for i in c) < 30]
    mid_gray = [c for c in pools["zona_cinza"] if max(best[i] for i in c) >= 30]
    rng.shuffle(low_gray)
    rng.shuffle(mid_gray)
    pools["zona_cinza"] = [c for pair in zip(low_gray, mid_gray) for c in pair] + low_gray[len(mid_gray):] + mid_gray[len(low_gray):]

    chosen: list[tuple[int, str, int]] = []
    used: set[int] = set()
    hood = 0
    for stratum, quota in QUOTAS.items():
        pool = pools[stratum][:]
        if stratum != "zona_cinza":
            rng.shuffle(pool)
        taken = 0
        for c in pool:
            if taken >= quota or len(chosen) >= size:
                break
            if any(i in used for i in c) or taken + len(c) > quota:
                continue
            hood += 1
            for i in c:
                chosen.append((i, stratum, hood))
                used.add(i)
            taken += len(c)

    rest = [i for i in sorted(isolated) if i not in used]
    rng.shuffle(rest)
    while len(chosen) < size and rest:
        hood += 1
        chosen.append((rest.pop(), "isolado", hood))

    return pd.DataFrame(chosen, columns=["id_registro", "estrato", "vizinhanca"])
