"""Pontuação de pares candidatos.

Modelo de evidência aditiva inspirado em Fellegi-Sunter: cada critério soma
pontos quando concorda e subtrai quando discorda. Campo vazio em qualquer
um dos lados vale 0, ou seja, não conta a favor nem contra. Isso evita
punir quem veio de um sistema que não coletava CPF ou e-mail.

A soma de pontos vira uma confiança de 0 a 100 por uma curva logística.
Os pesos ficam todos em `Weights` para a equipe poder calibrá-los.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein, OSA


@dataclass(frozen=True)
class Weights:
    # CPF: identificador forte, mas existem CPFs digitados errado
    cpf_igual: float = 40
    cpf_quase: float = 10          # 1 dígito trocado/transposto
    cpf_diferente: float = -40     # dois CPFs válidos diferentes = pessoas diferentes
    cpf_diferente_invalido: float = -15  # diferente, mas um deles é inválido (pode ser erro)
    # Data de nascimento
    nasc_igual: float = 15
    nasc_quase: float = 5          # dia/mês invertidos ou 1 dígito diferente
    nasc_diferente: float = -20
    # Nome (similaridade 0..1 mapeada linearmente em pontos)
    nome_max: float = 25           # nome idêntico
    nome_neutro: float = 0.85      # similaridade que vale 0 ponto
    nome_min: float = -25          # nome muito diferente
    nome_piso: float = 0.60        # similaridade em que chega ao mínimo
    # Telefone (8 últimos dígitos)
    fone_igual: float = 20
    fone_igual_ddd_conflitante: float = 5
    fone_diferente: float = -5     # pessoas trocam de número: penalidade leve
    # E-mail
    email_igual: float = 20
    email_mesmo_usuario: float = 10  # mesma parte antes do @, domínio diferente
    email_diferente: float = -5
    # Localização
    cidade_igual: float = 3
    cidade_diferente: float = -3
    uf_diferente: float = -10
    # Curva logística: confiança = 100 / (1 + exp(-(pontos - centro) / escala))
    centro: float = 25
    escala: float = 7


DEFAULT_WEIGHTS = Weights()


# --------------------------------------------------------------------------- nome
def _token_sim(a: str, b: str) -> float:
    if len(a) == 1 or len(b) == 1:  # inicial abreviada: "Q" casa com "QUEIROZ"
        return 1.0 if a[0] == b[0] else 0.0
    return Levenshtein.normalized_similarity(a, b)


def _structured_name_sim(ta: list[str], tb: list[str]) -> float:
    """Compara primeiro com primeiro, último com último e os nomes do meio
    tolerando abreviações ("Eduardo Q. R. Barbosa" x "Eduardo Queiroz Ramos Barbosa")."""
    parts: list[tuple[float, float]] = [(0.4, _token_sim(ta[0], tb[0]))]
    if len(ta) > 1 and len(tb) > 1:
        parts.append((0.4, _token_sim(ta[-1], tb[-1])))
        ma, mb = ta[1:-1], tb[1:-1]
        short, long_ = (ma, mb) if len(ma) <= len(mb) else (mb, ma)
        if long_:
            mid = sum(max(_token_sim(s, l) for l in long_) for s in short) / len(long_) if short else 0.25
            parts.append((0.2, mid))
    total_w = sum(w for w, _ in parts)
    return sum(w * s for w, s in parts) / total_w


def name_similarity(ta: list[str], tb: list[str]) -> float | None:
    if not ta or not tb:
        return None
    tsr = fuzz.token_sort_ratio(" ".join(ta), " ".join(tb)) / 100
    return max(tsr, _structured_name_sim(ta, tb))


def _name_points(sim: float, w: Weights) -> float:
    if sim >= w.nome_neutro:
        return w.nome_max * (sim - w.nome_neutro) / (1 - w.nome_neutro)
    pts = w.nome_min * (w.nome_neutro - sim) / (w.nome_neutro - w.nome_piso)
    return max(pts, w.nome_min)


# --------------------------------------------------------------------------- demais campos
def _cpf_points(a, b, a_ok, b_ok, w: Weights) -> tuple[float, str]:
    if not a or not b:
        return 0.0, "ausente"
    if a == b:
        return w.cpf_igual, "igual"
    if OSA.distance(a, b) <= 1:
        return w.cpf_quase, "quase"
    if a_ok and b_ok:
        return w.cpf_diferente, "diferente"
    return w.cpf_diferente_invalido, "diferente_invalido"


def _date_points(a, b, w: Weights) -> tuple[float, str]:
    if not a or not b:
        return 0.0, "ausente"
    if a == b:
        return w.nasc_igual, "igual"
    ya, ma, da = a.split("-")
    yb, mb, db = b.split("-")
    if ya == yb and ma == db and da == mb:
        return w.nasc_quase, "dia_mes_invertidos"
    if Levenshtein.distance(a, b) <= 1:
        return w.nasc_quase, "quase"
    return w.nasc_diferente, "diferente"


def _phone_points(fa, fb, da, db, w: Weights) -> tuple[float, str]:
    if not fa or not fb:
        return 0.0, "ausente"
    if fa == fb:
        if da and db and da != db:
            return w.fone_igual_ddd_conflitante, "igual_ddd_conflitante"
        return w.fone_igual, "igual"
    return w.fone_diferente, "diferente"


def _email_points(a, b, w: Weights) -> tuple[float, str]:
    if not a or not b:
        return 0.0, "ausente"
    if a == b:
        return w.email_igual, "igual"
    if a.split("@")[0] == b.split("@")[0]:
        return w.email_mesmo_usuario, "mesmo_usuario"
    return w.email_diferente, "diferente"


def _location_points(ca, cb, ua, ub, w: Weights) -> tuple[float, str]:
    if ua and ub and ua != ub:
        return w.uf_diferente, "uf_diferente"
    if not ca or not cb:
        return 0.0, "ausente"
    if ca == cb:
        return w.cidade_igual, "igual"
    return w.cidade_diferente, "diferente"


def confidence(points: float, w: Weights = DEFAULT_WEIGHTS) -> float:
    return 100.0 / (1.0 + math.exp(-(points - w.centro) / w.escala))


# --------------------------------------------------------------------------- API
def score_pair(ra, rb, w: Weights = DEFAULT_WEIGHTS) -> dict:
    sim = name_similarity(ra.n_tokens, rb.n_tokens)
    p_nome = 0.0 if sim is None else _name_points(sim, w)
    p_cpf, s_cpf = _cpf_points(ra.n_cpf, rb.n_cpf, ra.n_cpf_valido, rb.n_cpf_valido, w)
    p_nasc, s_nasc = _date_points(ra.n_nascimento, rb.n_nascimento, w)
    p_fone, s_fone = _phone_points(ra.n_fone8, rb.n_fone8, ra.n_ddd, rb.n_ddd, w)
    p_email, s_email = _email_points(ra.n_email, rb.n_email, w)
    p_loc, s_loc = _location_points(ra.n_cidade, rb.n_cidade, ra.n_uf, rb.n_uf, w)
    pontos = p_nome + p_cpf + p_nasc + p_fone + p_email + p_loc
    return {
        "sim_nome": None if sim is None else round(sim, 4),
        "p_nome": round(p_nome, 2),
        "p_cpf": p_cpf, "cpf": s_cpf,
        "p_nasc": p_nasc, "nasc": s_nasc,
        "p_fone": p_fone, "fone": s_fone,
        "p_email": p_email, "email": s_email,
        "p_local": p_loc, "local": s_loc,
        "pontos": round(pontos, 2),
        "confianca": round(confidence(pontos, w), 2),
    }


def score_pairs(df: pd.DataFrame, pairs: pd.DataFrame, w: Weights = DEFAULT_WEIGHTS) -> pd.DataFrame:
    recs = df.set_index("id_registro")
    lookup = {rid: row for rid, row in zip(recs.index, recs.itertuples())}
    rows = [score_pair(lookup[a], lookup[b], w) for a, b in zip(pairs["id_a"], pairs["id_b"])]
    return pd.concat([pairs.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def weights_dict(w: Weights = DEFAULT_WEIGHTS) -> dict:
    return asdict(w)
