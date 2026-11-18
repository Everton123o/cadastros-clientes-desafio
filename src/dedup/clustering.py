"""Agrupamento dos pares em grupos (prováveis mesmas pessoas).

Union-find guloso com restrições: as arestas acima do limiar são
processadas da maior para a menor confiança, e dois grupos só se juntam se
não houver evidência forte contra. Isso evita o "encadeamento" do
componente conexo puro (A~B e B~C, mas A e C são pessoas diferentes).

Há evidência forte contra quando:
- os dois grupos têm CPFs válidos diferentes; ou
- algum par já comparado entre os dois grupos tem pontuação negativa ou
  datas de nascimento incompatíveis.
"""
from __future__ import annotations

import pandas as pd
from rapidfuzz.distance import OSA


def cluster(df: pd.DataFrame, scored: pd.DataFrame, threshold_points: float) -> pd.DataFrame:
    cpf_of = {
        rid: cpf for rid, cpf in zip(df["id_registro"], df["n_cpf"]) if cpf
    }
    veto = {
        (a, b)
        for a, b, p, n, c in zip(scored["id_a"], scored["id_b"], scored["pontos"], scored["nasc"], scored["cpf"])
        if p < 0 or n == "diferente" or c in ("diferente", "diferente_invalido")
    }

    parent: dict[int, int] = {rid: rid for rid in df["id_registro"]}
    members: dict[int, set[int]] = {rid: {rid} for rid in df["id_registro"]}
    cpfs: dict[int, set[str]] = {rid: ({cpf_of[rid]} if rid in cpf_of else set()) for rid in df["id_registro"]}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def conflict(ra: int, rb: int) -> bool:
        for c1 in cpfs[ra]:
            for c2 in cpfs[rb]:
                if OSA.distance(c1, c2) > 1:
                    return True
        for x in members[ra]:
            for y in members[rb]:
                if (min(x, y), max(x, y)) in veto:
                    return True
        return False

    edges = scored[scored["pontos"] >= threshold_points].sort_values("pontos", ascending=False)
    for a, b in zip(edges["id_a"], edges["id_b"]):
        ra, rb = find(a), find(b)
        if ra == rb or conflict(ra, rb):
            continue
        if len(members[ra]) < len(members[rb]):
            ra, rb = rb, ra
        parent[rb] = ra
        members[ra] |= members.pop(rb)
        cpfs[ra] |= cpfs.pop(rb)

    rows = [(rid, find(rid)) for rid in df["id_registro"]]
    out = pd.DataFrame(rows, columns=["id_registro", "grupo"])
    # Numera os grupos de forma estável: id do grupo = menor id_registro do grupo
    out["grupo"] = out.groupby("grupo")["id_registro"].transform("min")
    return out


def group_summary(assign: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por grupo com 2+ registros: tamanho e confiança (média e mínima
    entre os pares comparados dentro do grupo)."""
    g = assign.set_index("id_registro")["grupo"]
    s = scored.copy()
    s["ga"] = s["id_a"].map(g)
    s["gb"] = s["id_b"].map(g)
    inside = s[s["ga"] == s["gb"]]
    sizes = assign.groupby("grupo").size().rename("tamanho")
    conf = inside.groupby("ga")["confianca"].agg(confianca_media="mean", confianca_min="min")
    summary = sizes[sizes > 1].to_frame().join(conf, how="left").reset_index()
    summary["membros"] = summary["grupo"].map(
        assign.groupby("grupo")["id_registro"].apply(lambda x: ",".join(map(str, sorted(x))))
    )
    return summary.sort_values("confianca_media", ascending=False, ignore_index=True)
