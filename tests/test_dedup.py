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


def test_fusion_review_and_undo_workflow(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from src.api.main import (
        DesfazerFusaoRequest,
        RevisarGrupoRequest,
        desfazer_fusao_historico,
        listar_grupos_revisao,
        listar_historico_fusoes,
        revisar_grupo,
    )
    from src.dedup.blocking import blocking_stats
    from src.dedup.clustering import group_summary
    from src.dedup.scoring import weights_dict
    from src.storage import db
    from src.storage.models import Base

    engine = create_engine(f"sqlite:///{(tmp_path / 'review_test.db').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "get_engine", lambda url=None: engine)

    raw = pd.DataFrame([
        {"id_registro": 1, "sistema_origem": "loja", "nome": "José da Silva",
         "cpf": "04345133009", "data_nascimento": "17/06/2004",
         "telefone": "(81) 99072-0417", "email": "jose@email.com", "cidade": "RECIFE", "uf": "PE"},
        {"id_registro": 2, "sistema_origem": "televendas", "nome": "JOSE SILVA",
         "cpf": "04345133009", "data_nascimento": "",
         "telefone": "99072-0417", "email": "", "cidade": "Recife", "uf": "PE"},
        {"id_registro": 3, "sistema_origem": "site", "nome": "José d. Silva",
         "cpf": "", "data_nascimento": "17/06/2004",
         "telefone": "81990720417", "email": "jose@email.com", "cidade": "Recife", "uf": "PE"},
    ])
    df = normalize_dataframe(raw)
    pairs = candidate_pairs(df)
    scored = score_pairs(df, pairs)
    assign = cluster(df, scored, threshold_points=25.0)
    summary = group_summary(assign, scored)
    stats = blocking_stats(len(df), pairs)

    db.save_records(engine, df)
    db.save_run(engine, scored, summary, 25.0, weights_dict(), stats)

    # 1. Lista grupos propostos com pontuação de confiança
    gdata = listar_grupos_revisao(status=None, busca=None, limit=50, offset=0)
    assert gdata["contagem"]["total"] == 1
    assert gdata["contagem"]["pendente"] == 1
    grupo = gdata["grupos"][0]
    grupo_id = grupo["id"]
    assert grupo["tamanho"] == 3
    assert grupo["confianca_media"] > 90.0
    assert grupo["status"] == "pendente"
    assert len(grupo["membros"]) == 3

    # 2. Operador aprova a fusão na tela de revisão
    res_approve = revisar_grupo(
        grupo_id,
        RevisarGrupoRequest(acao="aprovar", operador="ana", observacao="Mesmo CPF e telefone"),
    )
    assert res_approve["grupo"]["status"] == "aprovado"

    # 3. Verifica histórico de fusões
    hist = listar_historico_fusoes(limit=100)["historico"]
    assert len(hist) == 1
    assert hist[0]["acao"] == "aprovada"
    assert hist[0]["operador"] == "ana"
    assert hist[0]["status_anterior"] == "pendente"
    assert hist[0]["status_novo"] == "aprovado"
    assert len(hist[0]["membros_snapshot"]) == 3
    hist_id = hist[0]["id"]

    # 4. Operador desfaz a fusão a partir do histórico
    res_undo = desfazer_fusao_historico(
        hist_id,
        DesfazerFusaoRequest(operador="ana", observacao="Desfazendo para revisão adicional"),
    )
    assert res_undo["grupo"]["status"] == "pendente"

    # 5. Histórico registra tanto a aprovação quanto a reversão
    hist2 = listar_historico_fusoes(limit=100)["historico"]
    assert len(hist2) == 2
    assert hist2[0]["acao"] == "desfeita"
    assert hist2[0]["status_novo"] == "pendente"
