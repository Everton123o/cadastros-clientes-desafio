"""Backend FastAPI para o pipeline de deduplicação, marcação do gabarito e métricas.

    uvicorn src.api.main:app --reload --port 8000
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.dedup.blocking import blocking_stats
from src.dedup.clustering import cluster, group_summary
from src.dedup.evaluate import blocking_recall, confusion, threshold_sweep
from src.dedup.pipeline import DEFAULT_THRESHOLD, SWEEP, prepare
from src.dedup.sampling import stratified_sample
from src.dedup.scoring import weights_dict
from src.storage import db

ROOT = Path(__file__).resolve().parents[2]
BLIND_COLS = [
    "id_registro", "vizinhanca", "nome", "cpf", "data_nascimento",
    "telefone", "email", "cidade", "uf", "sistema_origem",
]

app = FastAPI(
    title="Deduplicação de Cadastros de Clientes API",
    version="1.0.0",
    description="API REST para deduplicação probabilística, marcação cega de gabarito e avaliação de precisão/revocação.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _cached_pipeline():
    return prepare()


class RodarRequest(BaseModel):
    limiar: float = Field(default=DEFAULT_THRESHOLD, description="Limiar em pontos para agrupar pares")


class SortearRequest(BaseModel):
    forcar: bool = Field(default=False, description="Se verdadeiro, sobrescreve amostra e rótulos existentes")


class SalvarRotulosRequest(BaseModel):
    operador: str = Field(..., min_length=1, description="Nome do operador que revisou a vizinhança")
    rotulos: dict[int, str] = Field(..., description="Mapa id_registro -> identificador da pessoa")


class RevisarGrupoRequest(BaseModel):
    acao: str = Field(..., description="Ação a executar no grupo: 'aprovar', 'rejeitar' ou 'desfazer'")
    operador: str = Field(default="equipe", min_length=1, description="Nome do operador que revisou a fusão")
    observacao: str | None = Field(default=None, description="Motivo ou observação opcional da decisão")


class DesfazerFusaoRequest(BaseModel):
    operador: str = Field(default="equipe", min_length=1, description="Nome do operador que desfez a fusão")
    observacao: str | None = Field(default=None, description="Motivo opcional da reversão")


@app.get("/api/health")
def health():
    engine = db.get_engine()
    return {"status": "ok", "dialect": engine.dialect.name}


@app.post("/api/pipeline/rodar")
def rodar_pipeline(payload: RodarRequest):
    df, pairs, scored = _cached_pipeline()
    assign = cluster(df, scored, payload.limiar)
    summary = group_summary(assign, scored)
    stats = blocking_stats(len(df), pairs)
    stats.update({
        "grupos_com_2_ou_mais": int(len(summary)),
        "registros_em_grupos": int(summary["tamanho"].sum()) if len(summary) else 0,
        "pessoas_estimadas": int(assign["grupo"].nunique()),
    })
    engine = db.get_engine()
    db.save_records(engine, df)
    run_id = db.save_run(engine, scored, summary, payload.limiar, weights_dict(), stats)
    return {"execucao_id": run_id, "limiar_pontos": payload.limiar, "estatisticas": stats}


@app.get("/api/pipeline/resumo")
def resumo_pipeline():
    engine = db.get_engine()
    latest = db.load_latest_run(engine)
    if not latest:
        df, pairs, _ = _cached_pipeline()
        return {"execucao": None, "blocking": blocking_stats(len(df), pairs)}
    return {"execucao": latest}


@app.get("/api/gabarito/amostra")
def obter_amostra():
    engine = db.get_engine()
    sample = db.load_sample(engine)
    if sample.empty:
        return {"total": 0, "rotulados": 0, "registros": []}
    labels_df = db.load_labels(engine)
    labels = dict(zip(labels_df["id_registro"], labels_df["pessoa"])) if len(labels_df) else {}
    records = []
    clean_sample = sample[BLIND_COLS].sort_values(["vizinhanca", "id_registro"]).fillna("")
    for row in clean_sample.to_dict(orient="records"):
        rid = int(row["id_registro"])
        row["pessoa"] = labels.get(rid, "")
        records.append(row)
    done = sum(1 for r in records if r["pessoa"])
    return {
        "total": len(records),
        "rotulados": done,
        "vizinhancas": sorted(sample["vizinhanca"].unique().tolist()),
        "registros": records,
    }


@app.post("/api/gabarito/amostra/sortear")
def sortear_amostra(payload: SortearRequest):
    engine = db.get_engine()
    if not payload.forcar and len(db.load_labels(engine)):
        raise HTTPException(
            status_code=409,
            detail="Já existem rótulos salvos no gabarito. Envie forcar=true para sortear novamente.",
        )
    df, _, scored = _cached_pipeline()
    db.save_records(engine, df)
    sample = stratified_sample(df, scored)
    db.save_sample(engine, sample)
    return {
        "total": len(sample),
        "vizinhancas": int(sample["vizinhanca"].nunique()),
        "por_estrato": sample["estrato"].value_counts().to_dict(),
    }


@app.put("/api/gabarito/rotulos")
def salvar_rotulos(payload: SalvarRotulosRequest):
    operador = payload.operador.strip()
    if not operador:
        raise HTTPException(status_code=422, detail="Informe o nome do operador.")
    engine = db.get_engine()
    db.save_labels(engine, payload.rotulos, operador)
    labels_df = db.load_labels(engine)
    return {"salvos": len(payload.rotulos), "total_rotulados": len(labels_df)}


@app.get("/api/gabarito/avaliar")
def avaliar_gabarito(limiar: float = Query(default=DEFAULT_THRESHOLD)):
    engine = db.get_engine()
    labels_df = db.load_labels(engine)
    if labels_df.empty:
        raise HTTPException(status_code=400, detail="Nenhum registro rotulado no gabarito.")

    df, _, scored = _cached_pipeline()
    gold = {int(r): str(p) for r, p in zip(labels_df["id_registro"], labels_df["pessoa"])}
    br = blocking_recall(scored, gold)
    thresholds = sorted(set(SWEEP + [limiar]))
    sweep_df = threshold_sweep(df, scored, gold, thresholds)

    assign = cluster(df, scored, limiar)
    pred = dict(zip(assign["id_registro"], assign["grupo"]))
    c = confusion(pred, gold)

    rec_lookup = df.set_index("id_registro")[["nome", "cpf", "data_nascimento", "telefone", "email", "cidade", "sistema_origem"]].to_dict(orient="index")
    score_lookup = scored.set_index(["id_a", "id_b"])[["pontos", "confianca", "blocos"]].to_dict(orient="index")

    def enrich(pairs_list):
        items = []
        for a, b in pairs_list:
            meta = score_lookup.get((a, b), {"pontos": None, "confianca": None, "blocos": "não gerado"})
            items.append({
                "id_a": a,
                "id_b": b,
                "pontos": meta["pontos"],
                "confianca": meta["confianca"],
                "blocos": meta["blocos"],
                "registro_a": rec_lookup.get(a, {}),
                "registro_b": rec_lookup.get(b, {}),
            })
        return items

    return {
        "rotulados": len(gold),
        "pessoas_distintas_gabarito": len(set(gold.values())),
        "limiar_escolhido": limiar,
        "blocking": br,
        "metricas_limiar": {k: v for k, v in c.items() if not k.endswith("_pares")},
        "fp_detalhes": enrich(c["fp_pares"]),
        "fn_detalhes": enrich(c["fn_pares"]),
        "varredura_limiares": sweep_df.to_dict(orient="records"),
    }


@app.get("/api/fusoes/grupos")
def listar_grupos_revisao(
    status: str | None = Query(default=None, description="Filtrar por status: pendente, aprovado, rejeitado"),
    busca: str | None = Query(default=None, description="Filtrar por ID, nome, CPF, telefone, e-mail ou cidade"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    engine = db.get_engine()
    return db.list_groups_for_review(engine, status=status, busca=busca, limit=limit, offset=offset)


@app.post("/api/fusoes/grupos/{grupo_id}/revisar")
def revisar_grupo(grupo_id: int, payload: RevisarGrupoRequest):
    operador = payload.operador.strip()
    if not operador:
        raise HTTPException(status_code=422, detail="Informe o nome do operador.")
    engine = db.get_engine()
    try:
        return db.review_group(
            engine,
            grupo_id=grupo_id,
            acao=payload.acao,
            operador=operador,
            observacao=payload.observacao,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/fusoes/grupos/{grupo_id}/desfazer")
def desfazer_fusao_grupo(grupo_id: int, payload: DesfazerFusaoRequest):
    operador = payload.operador.strip()
    if not operador:
        raise HTTPException(status_code=422, detail="Informe o nome do operador.")
    engine = db.get_engine()
    try:
        return db.review_group(
            engine,
            grupo_id=grupo_id,
            acao="desfazer",
            operador=operador,
            observacao=payload.observacao,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/fusoes/historico")
def listar_historico_fusoes(limit: int = Query(default=100, ge=1, le=500)):
    engine = db.get_engine()
    return {"historico": db.list_fusion_history(engine, limit=limit)}


@app.post("/api/fusoes/historico/{historico_id}/desfazer")
def desfazer_fusao_historico(historico_id: int, payload: DesfazerFusaoRequest):
    operador = payload.operador.strip()
    if not operador:
        raise HTTPException(status_code=422, detail="Informe o nome do operador.")
    engine = db.get_engine()
    try:
        return db.undo_fusion_by_history(
            engine,
            historico_id=historico_id,
            operador=operador,
            observacao=payload.observacao,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


FRONTEND_DIST = ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
