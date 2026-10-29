"""Aplica a matriz de acesso de config/acessos.yml num servidor MLflow com basic-auth.

    export MLFLOW_TRACKING_URI=http://localhost:5000
    export MLFLOW_TRACKING_USERNAME=admin MLFLOW_TRACKING_PASSWORD=...
    python src/permissoes.py --criar-usuarios

Com --criar-usuarios, cada usuário ausente é criado com a senha da variável
MLFLOW_SENHA_<USUARIO> (ex.: MLFLOW_SENHA_SVC_MLFLOW_PROD). Sem a variável, o usuário
é ignorado e o script avisa. Requer MLflow 3.13+ (permissões por papéis).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from mlflow.server import get_app_client

from comum import RAIZ


def _var_senha(usuario: str) -> str:
    return "MLFLOW_SENHA_" + usuario.upper().replace("-", "_").replace(".", "_")


def garantir_usuario(auth, usuario: str, criar: bool) -> bool:
    try:
        auth.get_user(usuario)
        return True
    except MlflowException:
        pass
    if not criar:
        print(f"  ! {usuario}: não existe (rode com --criar-usuarios)")
        return False
    senha = os.getenv(_var_senha(usuario))
    if not senha:
        print(f"  ! {usuario}: defina {_var_senha(usuario)} para criar")
        return False
    auth.create_user(username=usuario, password=senha)
    print(f"  + usuário {usuario} criado")
    return True


def conceder(auth, usuario: str, tipo: str, recurso: str, perm: str, rotulo: str) -> None:
    """Concessão idempotente: cria, mantém se igual ou substitui se mudou no YAML."""
    try:
        auth.grant_user_permission(usuario, tipo, recurso, perm)
        print(f"  + {usuario}: {perm} em {rotulo}")
    except MlflowException as erro:
        if "RESOURCE_ALREADY_EXISTS" not in str(erro):
            raise
        atual = auth.get_user_permission(usuario, tipo, recurso).permission
        if atual == perm:
            print(f"  = {usuario}: {perm} em {rotulo} (sem mudança)")
            return
        auth.revoke_user_permission(usuario, tipo, recurso)
        auth.grant_user_permission(usuario, tipo, recurso, perm)
        print(f"  ~ {usuario}: {atual} -> {perm} em {rotulo}")


def id_experimento(nome: str) -> str:
    c = MlflowClient()
    exp = c.get_experiment_by_name(nome)
    return exp.experiment_id if exp else c.create_experiment(nome)


def aplicar(auth, acessos: dict, criar: bool) -> None:
    for grupo in ("contas_de_servico", "pessoas"):
        for p in acessos.get(grupo, []):
            usuario = p["usuario"]
            if not garantir_usuario(auth, usuario, criar):
                continue
            for nome, perm in p.get("experimentos", {}).items():
                conceder(auth, usuario, "experiment", id_experimento(nome), perm, f"experimento {nome}")
            for nome, perm in p.get("modelos", {}).items():
                try:
                    MlflowClient().get_registered_model(nome)
                except MlflowException:
                    print(f"  ! {usuario}: modelo {nome} ainda não existe; rode de novo após o 1º treino")
                    continue
                conceder(auth, usuario, "registered_model", nome, perm, f"modelo {nome}")

    existentes = {r.name: r for r in auth.list_all_roles()}
    for papel in acessos.get("papeis", []):
        r = existentes.get(papel["nome"]) or auth.create_role(
            workspace=papel.get("workspace", "default"), name=papel["nome"],
            description=papel.get("descricao"))
        atuais = {(x.resource_type, x.resource_pattern) for x in auth.list_role_permissions(r.id)}
        for perm in papel.get("permissoes", []):
            if (perm["tipo"], perm["padrao"]) not in atuais:
                auth.add_role_permission(role_id=r.id, resource_type=perm["tipo"],
                                         resource_pattern=perm["padrao"], permission=perm["permissao"])
        membros = {m.user_id for m in auth.list_role_users(r.id)}
        for usuario in papel.get("membros", []):
            if garantir_usuario(auth, usuario, criar) and auth.get_user(usuario).id not in membros:
                auth.assign_role(username=usuario, role_id=r.id)
        print(f"  = papel {papel['nome']}: {len(papel.get('permissoes', []))} permissões, "
              f"membros {papel.get('membros', [])}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", default=str(RAIZ / "config" / "acessos.yml"))
    p.add_argument("--criar-usuarios", action="store_true")
    a = p.parse_args()
    uri = os.environ["MLFLOW_TRACKING_URI"]
    print(f"Aplicando {Path(a.arquivo).name} em {uri}")
    aplicar(get_app_client("basic-auth", tracking_uri=uri),
            yaml.safe_load(open(a.arquivo, encoding="utf-8")), a.criar_usuarios)
