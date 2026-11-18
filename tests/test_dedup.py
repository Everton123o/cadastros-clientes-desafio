from __future__ import annotations

import pandas as pd

from src.dedup.blocking import candidate_pairs
from src.dedup.clustering import cluster
from src.dedup.evaluate import confusion
from src.dedup.normalize import (
    cpf_is_valid,
    name_tokens,
    normalize_cpf,
    normalize_dataframe,
    normalize_date,
    normalize_phone,
    phone_key,
)
from src.dedup.scoring import name_similarity, score_pairs


def test_name_normalization_and_abbreviations():
    assert name_tokens("José da Silva") == ["JOSE", "SILVA"]
    assert name_tokens("JOSE SILVA") == ["JOSE", "SILVA"]
    assert name_tokens("José d. Silva") == ["JOSE", "SILVA"]
    assert name_tokens("BeneditoDias") == ["BENEDITO", "DIAS"]
    t_abrev = name_tokens("Eduardo Q. R. Barbosa")
    t_full = name_tokens("Eduardo Queiroz Ramos Barbosa")
    assert name_similarity(t_abrev, t_full) == 1.0


def test_cpf_and_phone_and_date_normalization():
    assert normalize_cpf("300.484.220-37") == "30048422037"
    assert cpf_is_valid("30048422037") is True
    assert cpf_is_valid("11111111111") is False
    assert cpf_is_valid("33781615038") is False
    assert normalize_date("27/02/1977") == "1977-02-27"
    assert normalize_date("1977-02-27") == "1977-02-27"
    ddd, num = normalize_phone("(82) 96738-8740")
    assert (ddd, phone_key(num)) == ("82", "67388740")
    ddd2, num2 = normalize_phone("96738-8740")
    assert (ddd2, phone_key(num2)) == (None, "67388740")


def test_blocking_and_clustering_prevent_homonym_chaining():
    raw = pd.DataFrame([
        # Pessoa 1 (Lucas Vieira nascido em 2004, dois registros)
        {"id_registro": 1, "sistema_origem": "loja", "nome": "LUCAS VIEIRA",
         "cpf": "04345133009", "data_nascimento": "17/06/2004",
         "telefone": "81990720417", "email": "", "cidade": "RECIFE", "uf": "PE"},
        {"id_registro": 2, "sistema_origem": "televendas", "nome": "Lucas Vieira",
         "cpf": "04345133009", "data_nascimento": "",
         "telefone": "81 99072-0417", "email": "", "cidade": "Recife", "uf": "PE"},
        # Pessoa 2 (homônimo Lucas Vieira nascido em 1982)
        {"id_registro": 3, "sistema_origem": "televendas", "nome": "Lucas Vieira",
         "cpf": "", "data_nascimento": "06/07/1982",
         "telefone": "96980-8739", "email": "", "cidade": "Recife", "uf": "PE"},
        {"id_registro": 4, "sistema_origem": "loja", "nome": "LUCAS VIEIRA",
         "cpf": "72717765913", "data_nascimento": "06/07/1982",
         "telefone": "81969808739", "email": "", "cidade": "RECIFE", "uf": "PE"},
    ])
    df = normalize_dataframe(raw)
    pairs = candidate_pairs(df)
    scored = score_pairs(df, pairs)
    assign = cluster(df, scored, threshold_points=20.0)
    pred = dict(zip(assign["id_registro"], assign["grupo"]))
    gold = {1: "A", 2: "A", 3: "B", 4: "B"}
    metrics = confusion(pred, gold)
    assert metrics["FP"] == 0
    assert metrics["FN"] == 0
    assert metrics["precisao"] == 1.0
    assert metrics["revocacao"] == 1.0


def test_fastapi_endpoints():
    from fastapi.testclient import TestClient
    from src.api.main import app

    client = TestClient(app)
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    res_sample = client.get("/api/gabarito/amostra")
    assert res_sample.status_code == 200
    body = res_sample.json()
    assert body["total"] == 100
    assert len(body["registros"]) == 100
    # Garante que a marcação é cega (não expõe estrato nem pontuação)
    assert "estrato" not in body["registros"][0]
    assert "pontos" not in body["registros"][0]

    res_eval = client.get("/api/gabarito/avaliar?limiar=25")
    assert res_eval.status_code == 200
    ev = res_eval.json()
    assert ev["blocking"]["revocacao_blocking"] == 1.0
    assert ev["metricas_limiar"]["FP"] == 0
    assert ev["metricas_limiar"]["precisao"] == 1.0
