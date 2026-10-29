"""Treina o modelo e registra uma nova versão com a linhagem completa.

    python src/train.py --dados dados/unicorn-2026-10.csv

Cada execução grava no run: commit, branch, pipeline, dataset (nome, origem, digest),
parâmetros e métrica. Também sincroniza os atributos do IC definidos em governanca.yml
com o Model Registry e devolve o run_id para o próximo passo do pipeline.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from comum import RAIZ, carregar_politica, contexto_ci, publicar_saida


def montar_modelo(alpha: float) -> Pipeline:
    pre = ColumnTransformer(
        [("estado", OneHotEncoder(handle_unknown="ignore"), ["State"])],
        remainder="passthrough",
    )
    return Pipeline([("pre", pre), ("ridge", Ridge(alpha=alpha))])


def sincronizar_ic(client: MlflowClient, politica: dict) -> None:
    """Grava descrição e atributos do IC no Registry (a fonte da verdade é o Git)."""
    nome = politica["modelo"]
    client.update_registered_model(nome, description=politica.get("descricao", "").strip())
    for chave, valor in politica.get("atributos_modelo", {}).items():
        client.set_registered_model_tag(nome, chave, str(valor))


def treinar(dados: str, alpha: float, politica: dict) -> str:
    ci = contexto_ci()
    df = pd.read_csv(dados)
    alvo = politica["gate"]["alvo"]
    X, y = df.drop(columns=[alvo]), df[alvo]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, train_size=0.7, random_state=0)

    caminho_rel = Path(dados).resolve().relative_to(RAIZ).as_posix()
    origem = (f"{ci['repo_url']}/blob/{ci['git_commit']}/{caminho_rel}"
              if ci["repo_url"] and ci["git_commit"] else caminho_rel)

    mlflow.set_experiment(politica["experimento"])
    nome_run = f"{ci['plataforma']}-{ci['pipeline_id'] or 'manual'}"
    with mlflow.start_run(run_name=nome_run) as run:
        mlflow.set_tags({
            "git_commit": ci["git_commit"],
            "git_branch": ci["git_branch"],
            "pipeline_id": ci["pipeline_id"],
            "pipeline_url": ci["pipeline_url"],
            "plataforma_ci": ci["plataforma"],
            "executor_ci": ci["executor_ci"],
        })

        ds = mlflow.data.from_pandas(df, source=origem, name=Path(dados).stem, targets=alvo)
        mlflow.log_input(ds, context="training")

        modelo = montar_modelo(alpha).fit(X_tr, y_tr)
        mlflow.log_params({"alpha": alpha, "train_size": 0.7, "random_state": 0})
        mlflow.log_metric("r2_score", r2_score(y_te, modelo.predict(X_te)))

        mlflow.sklearn.log_model(
            modelo,
            name="model",
            signature=infer_signature(X_tr, modelo.predict(X_tr)),
            input_example=X_tr.head(3),
            registered_model_name=politica["modelo"],
        )
        run_id = run.info.run_id

    sincronizar_ic(MlflowClient(), politica)
    Path("run_id.txt").write_text(run_id, encoding="utf-8")
    publicar_saida("run_id", run_id)
    return run_id


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dados", default="dados/unicorn-2026-10.csv")
    p.add_argument("--alpha", type=float, default=0.5)
    p.add_argument("--politica", default=None, help="caminho do governanca.yml")
    a = p.parse_args()
    treinar(a.dados, a.alpha, carregar_politica(a.politica))
