"""Funções compartilhadas: política de governança, contexto de CI e saída para o pipeline."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


def carregar_politica(caminho: str | Path | None = None) -> dict:
    caminho = Path(caminho or os.getenv("GOVERNANCA_YML", RAIZ / "governanca.yml"))
    with open(caminho, encoding="utf-8") as f:
        politica = yaml.safe_load(f)
    politica["_arquivo"] = str(caminho)
    return politica


def agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def contexto_ci() -> dict:
    """Identifica a plataforma de CI e devolve os elos de linhagem (commit, pipeline)."""
    e = os.environ
    if e.get("GITHUB_ACTIONS") == "true":
        repo_url = f"{e['GITHUB_SERVER_URL']}/{e['GITHUB_REPOSITORY']}"
        return {
            "plataforma": "github",
            "git_commit": e.get("GITHUB_SHA", ""),
            "git_branch": e.get("GITHUB_REF_NAME", ""),
            "pipeline_id": e.get("GITHUB_RUN_ID", ""),
            "pipeline_url": f"{repo_url}/actions/runs/{e.get('GITHUB_RUN_ID', '')}",
            "repo_url": repo_url,
            "executor_ci": e.get("GITHUB_ACTOR", ""),
        }
    if e.get("GITLAB_CI") == "true":
        return {
            "plataforma": "gitlab",
            "git_commit": e.get("CI_COMMIT_SHA", ""),
            "git_branch": e.get("CI_COMMIT_REF_NAME", ""),
            "pipeline_id": e.get("CI_PIPELINE_ID", ""),
            "pipeline_url": e.get("CI_PIPELINE_URL", ""),
            "repo_url": e.get("CI_PROJECT_URL", ""),
            "executor_ci": e.get("GITLAB_USER_LOGIN", ""),
        }
    if e.get("TF_BUILD") == "True":
        repo_url = e.get("BUILD_REPOSITORY_URI", "")
        return {
            "plataforma": "azure",
            "git_commit": e.get("BUILD_SOURCEVERSION", ""),
            "git_branch": e.get("BUILD_SOURCEBRANCHNAME", ""),
            "pipeline_id": e.get("BUILD_BUILDID", ""),
            "pipeline_url": (f"{e.get('SYSTEM_COLLECTIONURI', '')}{e.get('SYSTEM_TEAMPROJECT', '')}"
                             f"/_build/results?buildId={e.get('BUILD_BUILDID', '')}"),
            "repo_url": repo_url,
            "executor_ci": e.get("BUILD_REQUESTEDFOR", ""),
        }
    # Execução local: sem pipeline, o gate vai reprovar por falta de linhagem
    return {
        "plataforma": "local",
        "git_commit": e.get("GIT_COMMIT_LOCAL", ""),
        "git_branch": "",
        "pipeline_id": "",
        "pipeline_url": "",
        "repo_url": "",
        "executor_ci": e.get("USER", ""),
    }


def publicar_saida(nome: str, valor: str) -> None:
    """Expõe um valor para os próximos steps (GitHub Actions) e imprime no log."""
    print(f"{nome}={valor}")
    destino = os.getenv("GITHUB_OUTPUT")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(f"{nome}={valor}\n")


def resumo(markdown: str) -> None:
    """Escreve no resumo do job (GitHub Actions); fora dele, só imprime."""
    destino = os.getenv("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    else:
        print(markdown)
