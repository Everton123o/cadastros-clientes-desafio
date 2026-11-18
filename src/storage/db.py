"""Acesso ao banco MySQL. A URL vem de DATABASE_URL (.env)."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .models import (
    Base, Execucao, GabaritoAmostra, GabaritoRotulo, Grupo, GrupoMembro, ParCandidato, Registro,
)

ROOT = Path(__file__).resolve().parents[2]

_RAW_COLS = ["sistema_origem", "nome", "cpf", "data_nascimento", "telefone", "email", "cidade", "uf"]
_NORM_COLS = ["n_nome", "n_cpf", "n_cpf_valido", "n_nascimento", "n_fone8", "n_email"]
_DETAIL_COLS = ["sim_nome", "p_nome", "p_cpf", "cpf", "p_nasc", "nasc", "p_fone", "fone",
                "p_email", "email", "p_local", "local"]


def get_engine(url: str | None = None) -> Engine:
    load_dotenv(ROOT / ".env")
    database_url = url or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não definida. Configure o arquivo .env e inicie o MySQL via Docker Compose.")
    if not database_url.startswith("mysql+"):
        raise RuntimeError("Este projeto requer MySQL. Configure DATABASE_URL com um driver mysql+ (ex.: mysql+pymysql).")
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return engine


def _none(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else v


def save_records(engine: Engine, df: pd.DataFrame) -> None:
    with Session(engine) as s, s.begin():
        existing = set(s.scalars(select(Registro.id_registro)))
        for row in df.itertuples(index=False):
            if row.id_registro in existing:
                continue
            data = {c: _none(getattr(row, c)) for c in _RAW_COLS + _NORM_COLS}
            data["n_cpf_valido"] = bool(row.n_cpf_valido)
            s.add(Registro(id_registro=int(row.id_registro), **data))


def save_run(engine: Engine, scored: pd.DataFrame, summary: pd.DataFrame,
             threshold: float, weights: dict, stats: dict) -> int:
    with Session(engine) as s, s.begin():
        run = Execucao(limiar_pontos=threshold, pesos=weights, estatisticas=stats)
        s.add(run)
        s.flush()
        s.add_all(
            ParCandidato(
                execucao_id=run.id, id_a=int(r.id_a), id_b=int(r.id_b), blocos=r.blocos,
                pontos=float(r.pontos), confianca=float(r.confianca),
                detalhes={c: _none(getattr(r, c)) for c in _DETAIL_COLS},
            )
            for r in scored.itertuples(index=False)
        )
        for g in summary.itertuples(index=False):
            grupo = Grupo(
                execucao_id=run.id, tamanho=int(g.tamanho),
                confianca_media=_none(g.confianca_media), confianca_min=_none(g.confianca_min),
            )
            grupo.membros = [GrupoMembro(id_registro=int(m)) for m in g.membros.split(",")]
            s.add(grupo)
        return run.id


# ----------------------------------------------------------------------- gabarito
def save_sample(engine: Engine, sample: pd.DataFrame) -> None:
    with Session(engine) as s, s.begin():
        s.execute(delete(GabaritoRotulo))
        s.execute(delete(GabaritoAmostra))
        s.add_all(
            GabaritoAmostra(id_registro=int(r.id_registro), estrato=r.estrato, vizinhanca=int(r.vizinhanca))
            for r in sample.itertuples(index=False)
        )


def load_sample(engine: Engine) -> pd.DataFrame:
    q = select(GabaritoAmostra, Registro).join(Registro, Registro.id_registro == GabaritoAmostra.id_registro)
    rows = []
    with Session(engine) as s:
        for amostra, reg in s.execute(q):
            row = {"id_registro": reg.id_registro, "estrato": amostra.estrato, "vizinhanca": amostra.vizinhanca}
            row.update({c: getattr(reg, c) for c in _RAW_COLS})
            rows.append(row)
    return pd.DataFrame(rows)


def save_labels(engine: Engine, labels: dict[int, str], operador: str) -> None:
    with Session(engine) as s, s.begin():
        for rid, pessoa in labels.items():
            pessoa = (pessoa or "").strip()
            obj = s.get(GabaritoRotulo, int(rid))
            if not pessoa:
                if obj:
                    s.delete(obj)
                continue
            if obj:
                obj.pessoa, obj.marcado_por = pessoa, operador
            else:
                s.add(GabaritoRotulo(id_registro=int(rid), pessoa=pessoa, marcado_por=operador))


def load_labels(engine: Engine) -> pd.DataFrame:
    with Session(engine) as s:
        rows = [(r.id_registro, r.pessoa, r.marcado_por, r.marcado_em) for r in s.scalars(select(GabaritoRotulo))]
    return pd.DataFrame(rows, columns=["id_registro", "pessoa", "marcado_por", "marcado_em"])


def load_latest_run(engine: Engine) -> dict | None:
    with Session(engine) as s:
        run = s.scalars(select(Execucao).order_by(Execucao.id.desc()).limit(1)).first()
        if not run:
            return None
        grupos = [
            {
                "id": g.id,
                "tamanho": g.tamanho,
                "confianca_media": g.confianca_media,
                "confianca_min": g.confianca_min,
                "status": g.status,
                "membros": [m.id_registro for m in g.membros],
            }
            for g in run.grupos
        ]
        return {
            "id": run.id,
            "criado_em": run.criado_em.isoformat() if run.criado_em else None,
            "limiar_pontos": run.limiar_pontos,
            "pesos": run.pesos,
            "estatisticas": run.estatisticas,
            "grupos": grupos[:100],
            "total_grupos": len(grupos),
        }
