"""Acesso ao banco MySQL. A URL vem de DATABASE_URL (.env)."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .models import (
    Base,
    Execucao,
    GabaritoAmostra,
    GabaritoRotulo,
    Grupo,
    GrupoMembro,
    HistoricoFusao,
    ParCandidato,
    Registro,
    utcnow,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = f"sqlite:///{(ROOT / 'data' / 'dedup.db').as_posix()}"

_RAW_COLS = ["sistema_origem", "nome", "cpf", "data_nascimento", "telefone", "email", "cidade", "uf"]
_NORM_COLS = ["n_nome", "n_cpf", "n_cpf_valido", "n_nascimento", "n_fone8", "n_email"]
_DETAIL_COLS = ["sim_nome", "p_nome", "p_cpf", "cpf", "p_nasc", "nasc", "p_fone", "fone",
                "p_email", "email", "p_local", "local"]


def _ensure_columns(engine: Engine) -> None:
    insp = inspect(engine)
    if "grupos" in insp.get_table_names():
        existing_cols = {c["name"] for c in insp.get_columns("grupos")}
        with engine.begin() as conn:
            if "revisado_por" not in existing_cols:
                conn.execute(text("ALTER TABLE grupos ADD COLUMN revisado_por VARCHAR(100) NULL"))
            if "revisado_em" not in existing_cols:
                conn.execute(text("ALTER TABLE grupos ADD COLUMN revisado_em DATETIME NULL"))


def get_engine(url: str | None = None) -> Engine:
    load_dotenv(ROOT / ".env")
    database_url = url or os.getenv("DATABASE_URL", DEFAULT_URL)
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    _ensure_columns(engine)
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
                "revisado_por": g.revisado_por,
                "revisado_em": g.revisado_em.isoformat() if g.revisado_em else None,
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


# ----------------------------------------------------------------------- revisão de fusões e histórico
def _serialize_registro(r: Registro) -> dict:
    return {
        "id_registro": r.id_registro,
        "sistema_origem": r.sistema_origem,
        "nome": r.nome,
        "cpf": r.cpf or "",
        "data_nascimento": r.data_nascimento or "",
        "telefone": r.telefone or "",
        "email": r.email or "",
        "cidade": r.cidade or "",
        "uf": r.uf or "",
    }


def _serialize_historico(h: HistoricoFusao, grupo_status: str | None = None) -> dict:
    return {
        "id": h.id,
        "grupo_id": h.grupo_id,
        "execucao_id": h.execucao_id,
        "acao": h.acao,
        "status_anterior": h.status_anterior,
        "status_novo": h.status_novo,
        "operador": h.operador,
        "observacao": h.observacao or "",
        "confianca_media": h.confianca_media,
        "membros_snapshot": h.membros_snapshot or [],
        "criado_em": h.criado_em.isoformat() if h.criado_em else None,
        "grupo_status_atual": grupo_status,
    }


def list_groups_for_review(
    engine: Engine,
    status: str | None = None,
    busca: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    with Session(engine) as s:
        run = s.scalars(select(Execucao).order_by(Execucao.id.desc()).limit(1)).first()
        if not run:
            return {
                "execucao_id": None,
                "limiar_pontos": None,
                "contagem": {"total": 0, "pendente": 0, "aprovado": 0, "rejeitado": 0},
                "total_filtrado": 0,
                "grupos": [],
            }

        all_groups = list(
            s.scalars(
                select(Grupo)
                .where(Grupo.execucao_id == run.id)
                .order_by(Grupo.confianca_media.desc(), Grupo.id.asc())
            )
        )
        counts = {"total": len(all_groups), "pendente": 0, "aprovado": 0, "rejeitado": 0}
        for g in all_groups:
            if g.status in counts:
                counts[g.status] += 1

        # Mapa de membros de todos os grupos da execução
        group_member_ids: dict[int, list[int]] = {
            g.id: sorted(m.id_registro for m in g.membros) for g in all_groups
        }
        all_member_ids = {rid for ids in group_member_ids.values() for rid in ids}
        reg_map: dict[int, dict] = {}
        if all_member_ids:
            for r in s.scalars(select(Registro).where(Registro.id_registro.in_(all_member_ids))):
                reg_map[r.id_registro] = _serialize_registro(r)

        filtered = all_groups
        if status and status in ("pendente", "aprovado", "rejeitado"):
            filtered = [g for g in filtered if g.status == status]

        q = (busca or "").strip().lower()
        if q:
            matched = []
            for g in filtered:
                if q in str(g.id):
                    matched.append(g)
                    continue
                mems = [reg_map.get(rid, {}) for rid in group_member_ids.get(g.id, [])]
                if any(
                    q in str(m.get("id_registro", ""))
                    or q in (m.get("nome", "") or "").lower()
                    or q in (m.get("cpf", "") or "").lower()
                    or q in (m.get("telefone", "") or "").lower()
                    or q in (m.get("email", "") or "").lower()
                    or q in (m.get("cidade", "") or "").lower()
                    for m in mems
                ):
                    matched.append(g)
            filtered = matched

        total_filtrado = len(filtered)
        page_groups = filtered[offset : offset + limit]

        # Carrega pares candidatos internos para os grupos da página
        page_member_ids = {rid for g in page_groups for rid in group_member_ids.get(g.id, [])}
        rec_to_group = {rid: g.id for g in page_groups for rid in group_member_ids.get(g.id, [])}
        pairs_by_group: dict[int, list[dict]] = {g.id: [] for g in page_groups}
        if page_member_ids:
            pair_rows = s.scalars(
                select(ParCandidato).where(
                    ParCandidato.execucao_id == run.id,
                    ParCandidato.id_a.in_(page_member_ids),
                    ParCandidato.id_b.in_(page_member_ids),
                )
            )
            for p in pair_rows:
                ga = rec_to_group.get(p.id_a)
                gb = rec_to_group.get(p.id_b)
                if ga is not None and ga == gb:
                    pairs_by_group[ga].append({
                        "id_a": p.id_a,
                        "id_b": p.id_b,
                        "blocos": p.blocos,
                        "pontos": p.pontos,
                        "confianca": p.confianca,
                        "detalhes": p.detalhes or {},
                    })

        out_groups = []
        for g in page_groups:
            mids = group_member_ids.get(g.id, [])
            out_groups.append({
                "id": g.id,
                "execucao_id": g.execucao_id,
                "tamanho": g.tamanho,
                "confianca_media": g.confianca_media,
                "confianca_min": g.confianca_min,
                "status": g.status,
                "revisado_por": g.revisado_por,
                "revisado_em": g.revisado_em.isoformat() if g.revisado_em else None,
                "membros": [reg_map.get(rid, {"id_registro": rid}) for rid in mids],
                "pares": sorted(pairs_by_group.get(g.id, []), key=lambda x: x["pontos"], reverse=True),
            })

        return {
            "execucao_id": run.id,
            "limiar_pontos": run.limiar_pontos,
            "contagem": counts,
            "total_filtrado": total_filtrado,
            "grupos": out_groups,
        }


_ACTION_MAP = {
    "aprovar": ("aprovado", "aprovada"),
    "rejeitar": ("rejeitado", "rejeitada"),
    "desfazer": ("pendente", "desfeita"),
}


def review_group(
    engine: Engine,
    grupo_id: int,
    acao: str,
    operador: str,
    observacao: str | None = None,
) -> dict:
    if acao not in _ACTION_MAP:
        raise ValueError(f"Ação inválida: {acao}. Use 'aprovar', 'rejeitar' ou 'desfazer'.")
    novo_status, acao_hist = _ACTION_MAP[acao]

    with Session(engine) as s, s.begin():
        grupo = s.get(Grupo, int(grupo_id))
        if not grupo:
            raise LookupError(f"Grupo #{grupo_id} não encontrado.")
        if acao == "desfazer" and grupo.status == "pendente":
            raise ValueError(f"Grupo #{grupo_id} já está com status pendente.")

        status_anterior = grupo.status
        mids = sorted(m.id_registro for m in grupo.membros)
        regs = list(s.scalars(select(Registro).where(Registro.id_registro.in_(mids)))) if mids else []
        reg_by_id = {r.id_registro: r for r in regs}
        snapshot = [
            {
                "id_registro": rid,
                "nome": reg_by_id[rid].nome if rid in reg_by_id else "",
                "cpf": (reg_by_id[rid].cpf or "") if rid in reg_by_id else "",
                "telefone": (reg_by_id[rid].telefone or "") if rid in reg_by_id else "",
                "sistema_origem": reg_by_id[rid].sistema_origem if rid in reg_by_id else "",
            }
            for rid in mids
        ]

        now = utcnow()
        grupo.status = novo_status
        if novo_status == "pendente":
            grupo.revisado_por = None
            grupo.revisado_em = None
        else:
            grupo.revisado_por = operador
            grupo.revisado_em = now

        hist = HistoricoFusao(
            grupo_id=grupo.id,
            execucao_id=grupo.execucao_id,
            acao=acao_hist,
            status_anterior=status_anterior,
            status_novo=novo_status,
            operador=operador,
            observacao=(observacao or "").strip() or None,
            confianca_media=grupo.confianca_media,
            membros_snapshot=snapshot,
            criado_em=now,
        )
        s.add(hist)
        s.flush()
        return {
            "grupo": {
                "id": grupo.id,
                "status": grupo.status,
                "status_anterior": status_anterior,
                "revisado_por": grupo.revisado_por,
                "revisado_em": grupo.revisado_em.isoformat() if grupo.revisado_em else None,
            },
            "historico": _serialize_historico(hist, grupo.status),
        }


def undo_fusion_by_history(
    engine: Engine,
    historico_id: int,
    operador: str,
    observacao: str | None = None,
) -> dict:
    with Session(engine) as s:
        hist = s.get(HistoricoFusao, int(historico_id))
        if not hist:
            raise LookupError(f"Registro de histórico #{historico_id} não encontrado.")
        grupo_id = hist.grupo_id
    nota = observacao or f"Desfeita a partir do histórico #{historico_id}"
    return review_group(engine, grupo_id=grupo_id, acao="desfazer", operador=operador, observacao=nota)


def list_fusion_history(engine: Engine, limit: int = 100) -> list[dict]:
    with Session(engine) as s:
        rows = s.execute(
            select(HistoricoFusao, Grupo.status)
            .join(Grupo, Grupo.id == HistoricoFusao.grupo_id)
            .order_by(HistoricoFusao.id.desc())
            .limit(limit)
        ).all()
        return [_serialize_historico(h, g_status) for h, g_status in rows]
