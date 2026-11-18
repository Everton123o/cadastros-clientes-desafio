"""Avaliação contra o gabarito: precisão e revocação por pares.

Considera todos os pares possíveis dentro da amostra rotulada:
- VP: o sistema juntou e o gabarito diz que é a mesma pessoa
- FP: o sistema juntou, mas são pessoas diferentes   (fusão errada: o erro mais caro)
- FN: o gabarito diz que é a mesma pessoa e o sistema não juntou (duplicata que passou)

precisão = VP / (VP + FP)     revocação = VP / (VP + FN)
F0.5 dá mais peso à precisão, de acordo com a política "melhor deixar duplicata passar".
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

from .clustering import cluster


def _pairs_same(labels: dict[int, object]) -> set[tuple[int, int]]:
    ids = sorted(labels)
    return {(a, b) for a, b in combinations(ids, 2) if labels[a] == labels[b]}


def confusion(pred: dict[int, int], gold: dict[int, str]) -> dict:
    ids = sorted(set(pred) & set(gold))
    p = _pairs_same({i: pred[i] for i in ids})
    g = _pairs_same({i: gold[i] for i in ids})
    tp, fp, fn = len(p & g), len(p - g), len(g - p)
    total = len(ids) * (len(ids) - 1) // 2
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    f05 = 1.25 * prec * rec / (0.25 * prec + rec) if prec + rec else 0.0
    return {
        "VP": tp, "FP": fp, "FN": fn, "VN": total - tp - fp - fn,
        "precisao": round(prec, 4), "revocacao": round(rec, 4),
        "f1": round(f1, 4), "f0_5": round(f05, 4),
        "fp_pares": sorted(p - g), "fn_pares": sorted(g - p),
    }


def threshold_sweep(df: pd.DataFrame, scored: pd.DataFrame, gold: dict[int, str],
                    thresholds: list[float]) -> pd.DataFrame:
    rows = []
    for t in thresholds:
        assign = cluster(df, scored, t)
        pred = dict(zip(assign["id_registro"], assign["grupo"]))
        c = confusion(pred, gold)
        rows.append({"limiar_pontos": t, **{k: v for k, v in c.items() if not k.endswith("_pares")}})
    return pd.DataFrame(rows)


def blocking_recall(scored: pd.DataFrame, gold: dict[int, str]) -> dict:
    """Dos pares verdadeiros do gabarito, quantos o blocking chegou a gerar?"""
    g = _pairs_same(gold)
    cand = set(zip(scored["id_a"], scored["id_b"]))
    missed = sorted(g - cand)
    return {
        "pares_verdadeiros": len(g),
        "gerados_pelo_blocking": len(g) - len(missed),
        "revocacao_blocking": round((len(g) - len(missed)) / len(g), 4) if g else 1.0,
        "perdidos": missed,
    }
