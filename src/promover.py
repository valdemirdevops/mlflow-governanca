"""Ciclo de mudança do modelo no Model Registry: challenger, gate, promoção e rollback.

    python src/promover.py challenger --run-id <id>
    python src/promover.py gate
    python src/promover.py promover --rfc RFC-12 --aprovador maria --executor svc-mlflow-prod
    python src/promover.py rollback --rfc RFC-13 --executor svc-mlflow-prod

Regras (todas lidas de governanca.yml):
- o gate exige linhagem completa, atributos do IC e métrica acima do piso e do champion;
- a promoção exige gate aprovado contra o champion ATUAL, RFC, aprovador diferente de quem
  disparou o treino e execução dentro da janela (ou --emergencial com justificativa);
- o rollback não respeita janela: reverter precisa ser possível a qualquer hora.
Tudo o que acontece fica gravado como tag na versão afetada.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.metrics import r2_score

from comum import RAIZ, agora_utc, carregar_politica, resumo

DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


class MudancaRecusada(Exception):
    """A regra de governança não permite a operação."""


def _client() -> MlflowClient:
    return MlflowClient()


def por_alias(nome: str, alias: str):
    try:
        return _client().get_model_version_by_alias(nome, alias)
    except MlflowException:
        return None


def _tags(nome: str, versao: str, valores: dict) -> None:
    c = _client()
    for chave, valor in valores.items():
        c.set_model_version_tag(nome, versao, chave, str(valor))


def sha_politica(caminho=None) -> str:
    caminho = caminho or RAIZ / "governanca.yml"
    return hashlib.sha256(open(caminho, "rb").read()).hexdigest()[:12]


def r2_holdout(uri: str, politica: dict) -> float:
    g = politica["gate"]
    df = pd.read_csv(RAIZ / g["holdout"])
    X, y = df.drop(columns=[g["alvo"]]), df[g["alvo"]]
    return float(r2_score(y, mlflow.pyfunc.load_model(uri).predict(X)))


def dentro_da_janela(janela: dict, momento: datetime | None = None) -> tuple[bool, str]:
    fuso = ZoneInfo(janela["fuso"])
    momento = (momento or datetime.now(fuso)).astimezone(fuso)
    dia = DIAS[momento.weekday()]
    inicio = time.fromisoformat(janela["inicio"])
    fim = time.fromisoformat(janela["fim"])
    ok = dia in janela["dias"] and inicio <= momento.time() <= fim
    descricao = f"{', '.join(janela['dias'])} {janela['inicio']}-{janela['fim']} ({janela['fuso']})"
    return ok, f"agora {dia} {momento:%H:%M}; janela {descricao}"


# ---------------------------------------------------------------- challenger
def marcar_challenger(politica: dict, run_id: str) -> str:
    nome = politica["modelo"]
    versoes = _client().search_model_versions(f"name='{nome}' and run_id='{run_id}'")
    if not versoes:
        raise MudancaRecusada(f"Nenhuma versão de {nome} criada pelo run {run_id}.")
    v = versoes[0]
    _client().set_registered_model_alias(nome, "challenger", v.version)
    _tags(nome, v.version, {"validacao": "pendente"})
    resumo(f"### Challenger\n`{nome}` versão **{v.version}** marcada como `@challenger`.")
    return str(v.version)


# ---------------------------------------------------------------- gate
def avaliar_gate(politica: dict, piso: float | None = None) -> dict:
    nome, g = politica["modelo"], politica["gate"]
    piso = g["piso"] if piso is None else piso
    c = _client()

    ch = por_alias(nome, "challenger")
    if ch is None:
        raise MudancaRecusada("Nenhum @challenger para avaliar.")
    run = c.get_run(ch.run_id)
    falhas: list[str] = []

    for tag in politica.get("linhagem_obrigatoria", []):
        if not run.data.tags.get(tag):
            falhas.append(f"linhagem: tag '{tag}' ausente no run")
    if not run.inputs.dataset_inputs:
        falhas.append("linhagem: nenhum dataset registrado no run")

    ic = c.get_registered_model(nome).tags
    for tag in politica.get("tags_modelo_obrigatorias", []):
        if not ic.get(tag):
            falhas.append(f"IC: atributo '{tag}' ausente no modelo registrado")
    if ic.get("dados_pessoais") == "sim" and not ic.get("ripd"):
        falhas.append("LGPD: dados_pessoais=sim exige a tag 'ripd'")

    r2_ch = r2_holdout(f"models:/{nome}@challenger", politica)
    champ = por_alias(nome, "champion")
    r2_cp = r2_holdout(f"models:/{nome}@champion", politica) if champ else None
    if r2_ch < piso:
        falhas.append(f"métrica: r2 {r2_ch:.4f} abaixo do piso {piso}")
    if r2_cp is not None and r2_ch < r2_cp + g["margem"]:
        falhas.append(f"métrica: r2 {r2_ch:.4f} não supera o champion v{champ.version} ({r2_cp:.4f})")

    resultado = "reprovado" if falhas else "aprovado"
    _tags(nome, ch.version, {
        "validacao": resultado,
        "gate_r2": f"{r2_ch:.4f}",
        "gate_r2_champion": f"{r2_cp:.4f}" if r2_cp is not None else "nenhum",
        "gate_champion_versao": champ.version if champ else "nenhum",
        "gate_piso": piso,
        "gate_politica_sha": sha_politica(politica.get("_arquivo")),
        "gate_falhas": "; ".join(falhas)[:4900] or "nenhuma",
        "gate_em": agora_utc(),
    })

    linhas = "\n".join(f"- {f}" for f in falhas) or "- nenhuma"
    resumo(
        f"### Gate: versão {ch.version} **{resultado.upper()}**\n\n"
        f"| | r2 no holdout |\n|---|---|\n"
        f"| challenger v{ch.version} | {r2_ch:.4f} |\n"
        f"| champion {f'v{champ.version}' if champ else '-'} | "
        f"{f'{r2_cp:.4f}' if r2_cp is not None else '-'} |\n"
        f"| piso | {piso} |\n\nFalhas:\n{linhas}\n"
    )
    return {"versao": str(ch.version), "resultado": resultado, "falhas": falhas,
            "r2_challenger": r2_ch, "r2_champion": r2_cp}


# ---------------------------------------------------------------- promoção
def promover(politica: dict, rfc: str, aprovador: str, executor: str,
             emergencial: str = "", momento: datetime | None = None) -> dict:
    nome = politica["modelo"]
    ch = por_alias(nome, "challenger")
    if ch is None:
        raise MudancaRecusada("Nenhum @challenger para promover.")
    if ch.tags.get("validacao") != "aprovado":
        raise MudancaRecusada(f"Versão {ch.version} não foi aprovada no gate "
                              f"(validacao={ch.tags.get('validacao')}).")
    if not rfc.strip():
        raise MudancaRecusada("RFC obrigatória.")
    if not aprovador.strip():
        raise MudancaRecusada("Aprovador não identificado.")

    anterior = por_alias(nome, "champion")
    versao_no_gate = ch.tags.get("gate_champion_versao")
    versao_atual = str(anterior.version) if anterior else "nenhum"
    if versao_no_gate != versao_atual:
        raise MudancaRecusada(f"O gate comparou com o champion {versao_no_gate}, mas o champion "
                              f"atual é {versao_atual}. Rode o gate de novo.")

    if politica.get("exigir_segregacao", True):
        quem_treinou = _client().get_run(ch.run_id).data.tags.get("executor_ci", "")
        if quem_treinou and quem_treinou == aprovador:
            raise MudancaRecusada(f"Segregação de funções: '{aprovador}' disparou o treino "
                                  "e não pode aprovar a própria mudança.")

    na_janela, detalhe = dentro_da_janela(politica["janela"], momento)
    if not na_janela and not emergencial.strip():
        raise MudancaRecusada(f"Fora da janela de mudança ({detalhe}). "
                              "Use --emergencial com justificativa, se for o caso.")

    _tags(nome, ch.version, {
        "rfc": rfc,
        "aprovado_por": aprovador,
        "promovido_por": executor,
        "promovido_em": agora_utc(),
        "substitui_versao": versao_atual,
        "tipo_mudanca": "emergencial" if emergencial.strip() else "normal",
        **({"justificativa_emergencial": emergencial} if emergencial.strip() else {}),
    })
    c = _client()
    c.set_registered_model_alias(nome, "champion", ch.version)
    c.delete_registered_model_alias(nome, "challenger")
    if anterior:
        _tags(nome, anterior.version, {"substituida_em": agora_utc(), "substituida_por": ch.version})

    de = f"v{versao_atual}" if anterior else "nenhum"
    resumo(f"### Promoção\n`@champion`: {de} → **v{ch.version}** "
           f"| RFC `{rfc}` | aprovado por `{aprovador}` | executado por `{executor}`")
    return {"de": versao_atual, "para": str(ch.version), "rfc": rfc}


# ---------------------------------------------------------------- rollback
def rollback(politica: dict, rfc: str, executor: str, para: str | None = None) -> dict:
    nome = politica["modelo"]
    atual = por_alias(nome, "champion")
    if atual is None:
        raise MudancaRecusada("Não há @champion para reverter.")
    alvo = para or atual.tags.get("substitui_versao")
    if not alvo or alvo == "nenhum":
        raise MudancaRecusada("Sem versão anterior registrada; informe --para <versão>.")
    if alvo == str(atual.version):
        raise MudancaRecusada(f"A versão {alvo} já é o champion.")
    _client().get_model_version(nome, alvo)  # falha se a versão não existir

    _client().set_registered_model_alias(nome, "champion", alvo)
    momento = agora_utc()
    _tags(nome, atual.version, {"validacao": "revertido", "rollback_em": momento,
                                "rollback_rfc": rfc or "nao-informada", "rollback_por": executor})
    _tags(nome, alvo, {"restaurada_em": momento, "restaurada_rfc": rfc or "nao-informada"})

    resumo(f"### Rollback\n`@champion`: v{atual.version} → **v{alvo}** | RFC `{rfc}` "
           f"| executado por `{executor}`")
    return {"de": str(atual.version), "para": alvo}


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--politica", default=None, help="caminho do governanca.yml")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("challenger")
    s.add_argument("--run-id", required=True)

    s = sub.add_parser("gate")
    s.add_argument("--piso", type=float, default=None, help="sobrescreve o piso (só para testes)")

    s = sub.add_parser("promover")
    s.add_argument("--rfc", required=True)
    s.add_argument("--aprovador", required=True)
    s.add_argument("--executor", required=True)
    s.add_argument("--emergencial", default="", help="justificativa para promover fora da janela")

    s = sub.add_parser("rollback")
    s.add_argument("--rfc", default="")
    s.add_argument("--executor", required=True)
    s.add_argument("--para", default=None)

    a = p.parse_args(argv)
    politica = carregar_politica(a.politica)
    try:
        if a.cmd == "challenger":
            marcar_challenger(politica, a.run_id)
        elif a.cmd == "gate":
            if avaliar_gate(politica, a.piso)["resultado"] != "aprovado":
                return 1
        elif a.cmd == "promover":
            promover(politica, a.rfc, a.aprovador, a.executor, a.emergencial)
        elif a.cmd == "rollback":
            rollback(politica, a.rfc, a.executor, a.para)
    except MudancaRecusada as erro:
        resumo(f"### Mudança recusada\n{erro}")
        print(f"ERRO: {erro}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
