"""Testes das regras de governança: cada teste é uma regra que o auditor pode cobrar."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from mlflow import MlflowClient

import auditar
import promover as pm
import train

RAIZ = pm.RAIZ
SP = ZoneInfo("America/Sao_Paulo")
DENTRO = datetime(2026, 10, 28, 20, 0, tzinfo=SP)   # quarta 20h
FORA = datetime(2026, 10, 31, 10, 0, tzinfo=SP)     # sábado 10h


def treinar_challenger(politica, arquivo, run_id_ci="1001"):
    import os
    os.environ["GITHUB_RUN_ID"] = run_id_ci
    run_id = train.treinar(str(RAIZ / "dados" / arquivo), 0.5, politica)
    return pm.marcar_challenger(politica, run_id)


def test_treino_grava_linhagem_completa(mlflow_isolado, politica):
    versao = treinar_challenger(politica, "unicorn-2026-09.csv")
    c = MlflowClient()
    v = c.get_model_version(politica["modelo"], versao)
    run = c.get_run(v.run_id)
    assert run.data.tags["git_commit"] == "a1b2c3d4e5f6"
    assert run.data.tags["pipeline_url"].endswith("/actions/runs/1001")
    ds = run.inputs.dataset_inputs[0].dataset
    assert ds.digest and "blob/a1b2c3d4e5f6/dados/unicorn-2026-09.csv" in ds.source
    assert c.get_registered_model(politica["modelo"]).tags["dono"] == "time-risco"


def test_gate_aprova_primeira_versao(mlflow_isolado, politica):
    treinar_challenger(politica, "unicorn-2026-09.csv")
    r = pm.avaliar_gate(politica)
    assert r["resultado"] == "aprovado" and r["r2_champion"] is None


def test_gate_reprova_abaixo_do_piso(mlflow_isolado, politica):
    v = treinar_challenger(politica, "unicorn-2026-09.csv")
    r = pm.avaliar_gate(politica, piso=0.99)
    assert r["resultado"] == "reprovado"
    tags = MlflowClient().get_model_version(politica["modelo"], v).tags
    assert tags["validacao"] == "reprovado" and "piso" in tags["gate_falhas"]


def test_gate_reprova_sem_linhagem(mlflow_isolado, politica, monkeypatch):
    for var in ("GITHUB_ACTIONS", "GITHUB_SHA"):
        monkeypatch.delenv(var)
    treinar_challenger(politica, "unicorn-2026-09.csv")   # treino "no notebook"
    r = pm.avaliar_gate(politica)
    assert r["resultado"] == "reprovado"
    assert any("git_commit" in f for f in r["falhas"])


def test_gate_exige_ripd_quando_ha_dados_pessoais(mlflow_isolado, politica):
    politica["atributos_modelo"]["dados_pessoais"] = "sim"
    treinar_challenger(politica, "unicorn-2026-09.csv")
    r = pm.avaliar_gate(politica)
    assert any("ripd" in f for f in r["falhas"])


def test_promocao_bloqueada_sem_gate(mlflow_isolado, politica):
    treinar_challenger(politica, "unicorn-2026-09.csv")
    with pytest.raises(pm.MudancaRecusada, match="não foi aprovada"):
        pm.promover(politica, "RFC-1", "maria-mudancas", "svc", momento=DENTRO)


def test_promocao_exige_segregacao(mlflow_isolado, politica):
    treinar_challenger(politica, "unicorn-2026-09.csv")
    pm.avaliar_gate(politica)
    with pytest.raises(pm.MudancaRecusada, match="Segregação"):
        pm.promover(politica, "RFC-1", "ana-dados", "svc", momento=DENTRO)


def test_promocao_respeita_janela(mlflow_isolado, politica):
    treinar_challenger(politica, "unicorn-2026-09.csv")
    pm.avaliar_gate(politica)
    with pytest.raises(pm.MudancaRecusada, match="Fora da janela"):
        pm.promover(politica, "RFC-1", "maria-mudancas", "svc", momento=FORA)
    r = pm.promover(politica, "RFC-1", "maria-mudancas", "svc",
                    emergencial="incidente INC-77", momento=FORA)
    tags = MlflowClient().get_model_version(politica["modelo"], r["para"]).tags
    assert tags["tipo_mudanca"] == "emergencial"


def test_ciclo_completo_promocao_e_rollback(mlflow_isolado, politica):
    nome = politica["modelo"]
    c = MlflowClient()

    treinar_challenger(politica, "unicorn-2026-09.csv", "1001")
    pm.avaliar_gate(politica)
    pm.promover(politica, "RFC-1", "maria-mudancas", "svc", momento=DENTRO)

    v2 = treinar_challenger(politica, "unicorn-2026-10.csv", "1002")
    r = pm.avaliar_gate(politica)
    assert r["resultado"] == "aprovado" and r["r2_challenger"] > r["r2_champion"]
    pm.promover(politica, "RFC-2", "maria-mudancas", "svc", momento=DENTRO)
    assert str(c.get_model_version_by_alias(nome, "champion").version) == v2
    assert c.get_model_version(nome, v2).tags["substitui_versao"] == "1"

    pm.rollback(politica, "RFC-3", "svc")
    assert str(c.get_model_version_by_alias(nome, "champion").version) == "1"
    assert c.get_model_version(nome, v2).tags["validacao"] == "revertido"

    evidencia = auditar.linhagem(nome)
    assert evidencia["versao"] == "1" and evidencia["mudanca"]["rfc"] == "RFC-1"
    assert [h["rollback_rfc"] for h in evidencia["historico"]] == [None, "RFC-3"]


def test_gate_desatualizado_bloqueia_promocao(mlflow_isolado, politica):
    treinar_challenger(politica, "unicorn-2026-09.csv", "1001")
    pm.avaliar_gate(politica)
    pm.promover(politica, "RFC-1", "maria-mudancas", "svc", momento=DENTRO)
    treinar_challenger(politica, "unicorn-2026-10.csv", "1002")
    # gate forjado: tag aprovada, mas comparada com um champion que não é o atual
    v = pm.por_alias(politica["modelo"], "challenger")
    MlflowClient().set_model_version_tag(politica["modelo"], v.version, "validacao", "aprovado")
    MlflowClient().set_model_version_tag(politica["modelo"], v.version, "gate_champion_versao", "nenhum")
    with pytest.raises(pm.MudancaRecusada, match="Rode o gate de novo"):
        pm.promover(politica, "RFC-2", "maria-mudancas", "svc", momento=DENTRO)


def test_janela():
    janela = {"fuso": "America/Sao_Paulo", "dias": ["seg", "ter", "qua", "qui", "sex"],
              "inicio": "19:00", "fim": "23:00"}
    assert pm.dentro_da_janela(janela, DENTRO)[0]
    assert not pm.dentro_da_janela(janela, FORA)[0]
