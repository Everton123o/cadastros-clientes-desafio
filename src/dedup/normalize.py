"""Normalização dos campos brutos do CSV.

Cada função recebe o valor cru (string, possivelmente vazia) e devolve uma
forma canônica comparável. O resultado de `normalize_dataframe` acrescenta
colunas com prefixo `n_` sem alterar as colunas originais.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

import pandas as pd

# Partículas que não ajudam a distinguir pessoas e variam entre sistemas
# ("José da Silva" x "JOSE SILVA" x "José d. Silva").
PARTICLES = {"DE", "DA", "DO", "DOS", "DAS", "E", "D"}

_CAMEL_RE = re.compile(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Þ])")  # "BeneditoDias" -> "Benedito Dias"
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9 ]+")
_SPACES_RE = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def name_tokens(raw: str) -> list[str]:
    """Tokens do nome em maiúsculas, sem acento, sem pontuação e sem partículas.

    Iniciais abreviadas ("Q." -> "Q") são mantidas como tokens de 1 letra para
    que o comparador de nomes possa casá-las com o nome por extenso.
    """
    if is_blank(raw):
        return []
    text = _CAMEL_RE.sub(" ", str(raw).strip())
    text = strip_accents(text).upper()
    text = _NON_ALNUM_RE.sub(" ", text)
    tokens = [t for t in _SPACES_RE.split(text) if t]
    return [t for t in tokens if t not in PARTICLES]


def normalize_cpf(raw) -> str | None:
    if is_blank(raw):
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    return digits.zfill(11) if len(digits) <= 11 else digits


def cpf_is_valid(cpf: str | None) -> bool:
    """Valida os dígitos verificadores (módulo 11 da Receita Federal)."""
    if not cpf or len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    nums = [int(c) for c in cpf]
    for size in (9, 10):
        total = sum(n * (size + 1 - i) for i, n in enumerate(nums[:size]))
        check = (total * 10) % 11 % 10
        if check != nums[size]:
            return False
    return True


def normalize_date(raw) -> str | None:
    """Aceita ISO (AAAA-MM-DD) e brasileiro (DD/MM/AAAA). Devolve ISO."""
    if is_blank(raw):
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_phone(raw) -> tuple[str | None, str | None]:
    """Devolve (ddd, numero_local). O DDD fica None quando não foi informado.

    Formatos observados no CSV: "(82) 98431-2819", "82984312819",
    "82 98431-2819", "98431-2819", "984312819".
    """
    if is_blank(raw):
        return None, None
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) in (10, 11):
        return digits[:2], digits[2:]
    if len(digits) in (8, 9):
        return None, digits
    return None, digits or None


def phone_key(local_number: str | None) -> str | None:
    """Últimos 8 dígitos: tolera o 9 extra de celular e a ausência de DDD."""
    if not local_number or len(local_number) < 8:
        return None
    return local_number[-8:]


def normalize_email(raw) -> str | None:
    if is_blank(raw):
        return None
    return str(raw).strip().lower()


def normalize_city(raw) -> str | None:
    if is_blank(raw):
        return None
    return _SPACES_RE.sub(" ", strip_accents(str(raw)).upper().strip())


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    def col(values) -> pd.Series:
        # dtype object preserva None (o pandas converteria None em NaN, que é "truthy")
        return pd.Series(list(values), index=out.index, dtype=object)

    tokens = [name_tokens(v) for v in out["nome"]]
    cpfs = [normalize_cpf(v) for v in out["cpf"]]
    phones = [normalize_phone(v) for v in out["telefone"]]
    out["n_tokens"] = col(tokens)
    out["n_nome"] = col(" ".join(t) for t in tokens)
    out["n_primeiro"] = col(t[0] if t else None for t in tokens)
    out["n_ultimo"] = col(t[-1] if len(t) > 1 else None for t in tokens)
    out["n_cpf"] = col(cpfs)
    out["n_cpf_valido"] = col(cpf_is_valid(c) for c in cpfs)
    out["n_nascimento"] = col(normalize_date(v) for v in out["data_nascimento"])
    out["n_ddd"] = col(p[0] for p in phones)
    out["n_fone"] = col(p[1] for p in phones)
    out["n_fone8"] = col(phone_key(p[1]) for p in phones)
    out["n_email"] = col(normalize_email(v) for v in out["email"])
    out["n_cidade"] = col(normalize_city(v) for v in out["cidade"])
    out["n_uf"] = col(None if is_blank(v) else str(v).strip().upper() for v in out["uf"])
    return out


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    df["id_registro"] = df["id_registro"].astype(int)
    return df
