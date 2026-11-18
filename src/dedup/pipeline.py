"""CLI do pipeline de deduplicação.

    python -m src.dedup.pipeline rodar   [--limiar 35]
    python -m src.dedup.pipeline amostra [--forcar]
    python -m src.dedup.pipeline importar-gabarito arquivo.csv --operador nome
    python -m src.dedup.pipeline avaliar [--limiar 35]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from src.storage import db

from .blocking import blocking_stats, candidate_pairs
from .clustering import cluster, group_summary
from .evaluate import blocking_recall, confusion, threshold_sweep
from .normalize import load_csv, normalize_dataframe
from .sampling import stratified_sample
from .scoring import DEFAULT_WEIGHTS, weights_dict

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "clientes.csv"
OUT_DIR = ROOT / "data" / "output"
DEFAULT_THRESHOLD = 25.0
SWEEP = [0, 10, 15, 20, 23, 25, 28, 30, 32, 35, 38, 40, 45, 50, 60, 70, 80]


def prepare(csv_path: Path = CSV_PATH):
    df = normalize_dataframe(load_csv(str(csv_path)))
    pairs = candidate_pairs(df)
    from .scoring import score_pairs
    scored = score_pairs(df, pairs, DEFAULT_WEIGHTS)
    return df, pairs, scored


def cmd_rodar(args) -> None:
    df, pairs, scored = prepare()
    assign = cluster(df, scored, args.limiar)
    summary = group_summary(assign, scored)
    stats = blocking_stats(len(df), pairs)
    stats.update({
        "grupos_com_2_ou_mais": int(len(summary)),
        "registros_em_grupos": int(summary["tamanho"].sum()) if len(summary) else 0,
        "pessoas_estimadas": int(assign["grupo"].nunique()),
    })
    engine = db.get_engine()
    db.save_records(engine, df)
    run_id = db.save_run(engine, scored, summary, args.limiar, weights_dict(), stats)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scored.to_csv(OUT_DIR / "pares_pontuados.csv", index=False)
    summary.to_csv(OUT_DIR / "grupos.csv", index=False)
    df[["id_registro"]].merge(assign).to_csv(OUT_DIR / "registro_grupo.csv", index=False)
    print(f"execução #{run_id}  limiar={args.limiar} pontos")
    print(json.dumps(stats, indent=2, ensure_ascii=False))


def cmd_amostra(args) -> None:
    df, _, scored = prepare()
    engine = db.get_engine()
    db.save_records(engine, df)
    if not args.forcar and len(db.load_labels(engine)):
        sys.exit("Já existem rótulos de gabarito. Use --forcar para sortear uma nova amostra.")
    sample = stratified_sample(df, scored)
    db.save_sample(engine, sample)
    print(sample["estrato"].value_counts().to_string())
    print(f"{len(sample)} registros em {sample['vizinhanca'].nunique()} vizinhanças salvos em gabarito_amostra")


def cmd_importar(args) -> None:
    gab = pd.read_csv(args.arquivo, dtype={"pessoa": str})
    engine = db.get_engine()
    db.save_labels(engine, dict(zip(gab["id_registro"], gab["pessoa"])), args.operador)
    print(f"{len(gab)} rótulos importados por {args.operador}")


def cmd_avaliar(args) -> None:
    df, _, scored = prepare()
    engine = db.get_engine()
    labels = db.load_labels(engine)
    if labels.empty:
        sys.exit("Nenhum rótulo no gabarito. Marque na tela (uvicorn src.api.main:app --port 8000).")
    gold = dict(zip(labels["id_registro"], labels["pessoa"]))
    print(f"gabarito: {len(gold)} registros rotulados, {len(set(gold.values()))} pessoas\n")

    br = blocking_recall(scored, gold)
    print(f"blocking: {br['gerados_pelo_blocking']}/{br['pares_verdadeiros']} pares verdadeiros "
          f"gerados (revocação do blocking = {br['revocacao_blocking']:.2%}); perdidos: {br['perdidos']}\n")

    sweep = threshold_sweep(df, scored, gold, SWEEP)
    print(sweep.to_string(index=False))

    assign = cluster(df, scored, args.limiar)
    c = confusion(dict(zip(assign["id_registro"], assign["grupo"])), gold)
    print(f"\nlimiar escolhido = {args.limiar}: precisão {c['precisao']:.2%}, revocação {c['revocacao']:.2%}")
    idx = scored.set_index(["id_a", "id_b"])
    for kind in ("fp_pares", "fn_pares"):
        print(f"\n{kind.upper()}:")
        for a, b in c[kind]:
            pts = idx["pontos"].get((a, b), "não gerado pelo blocking")
            print(f"  {a} x {b}: {pts}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sweep.to_csv(OUT_DIR / "avaliacao_limiares.csv", index=False)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m src.dedup.pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rodar", help="normaliza, faz blocking, pontua, agrupa e salva no banco")
    r.add_argument("--limiar", type=float, default=DEFAULT_THRESHOLD)
    r.set_defaults(func=cmd_rodar)
    a = sub.add_parser("amostra", help="sorteia a amostra estratificada de 100 registros")
    a.add_argument("--forcar", action="store_true")
    a.set_defaults(func=cmd_amostra)
    i = sub.add_parser("importar-gabarito", help="importa rótulos de um CSV (id_registro,pessoa)")
    i.add_argument("arquivo")
    i.add_argument("--operador", required=True)
    i.set_defaults(func=cmd_importar)
    v = sub.add_parser("avaliar", help="precisão/revocação contra o gabarito para vários limiares")
    v.add_argument("--limiar", type=float, default=DEFAULT_THRESHOLD)
    v.set_defaults(func=cmd_avaliar)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
