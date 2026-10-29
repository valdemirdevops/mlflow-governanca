"""Reconstrói a linhagem e o histórico de mudanças de um modelo: a evidência da RFC.

    python src/auditar.py                       # JSON do @champion
    python src/auditar.py --alias challenger
    python src/auditar.py --formato markdown --saida evidencia.md

Responde, a partir do Registry e do Tracking: qual versão está em produção, de qual
run, commit e dataset ela veio, com que métrica passou no gate, qual RFC a promoveu,
quem aprovou e qual é o histórico de promoções e rollbacks de todas as versões.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from mlflow import MlflowClient

from comum import agora_utc, carregar_politica


def _data(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds") if ms else ""


def _origem(source: str) -> str:
    """O MLflow guarda a origem como JSON ({"url": ...} ou {"path": ...}); devolve o endereço."""
    try:
        dados = json.loads(source)
        return dados.get("url") or dados.get("path") or dados.get("uri") or source
    except (ValueError, AttributeError):
        return source


def linhagem(nome: str, alias: str = "champion") -> dict:
    c = MlflowClient()
    v = c.get_model_version_by_alias(nome, alias)
    r = c.get_run(v.run_id)
    modelo = c.get_registered_model(nome)
    return {
        "gerado_em": agora_utc(),
        "modelo": nome,
        "item_de_configuracao": {"descricao": modelo.description, "atributos": dict(modelo.tags)},
        "alias": alias,
        "versao": str(v.version),
        "versao_criada_em": _data(v.creation_timestamp),
        "run_id": v.run_id,
        "codigo": {
            "commit": r.data.tags.get("git_commit"),
            "branch": r.data.tags.get("git_branch"),
            "pipeline": r.data.tags.get("pipeline_url"),
            "disparado_por": r.data.tags.get("executor_ci"),
        },
        "datasets": [
            {"nome": d.dataset.name, "digest": d.dataset.digest, "origem": _origem(d.dataset.source),
             "contexto": next((t.value for t in d.tags if t.key == "mlflow.data.context"), "")}
            for d in r.inputs.dataset_inputs
        ],
        "parametros": dict(r.data.params),
        "metricas_treino": dict(r.data.metrics),
        "gate": {k.removeprefix("gate_"): val for k, val in v.tags.items() if k.startswith("gate_")},
        "mudanca": {k: v.tags.get(k) for k in (
            "validacao", "rfc", "tipo_mudanca", "aprovado_por", "promovido_por",
            "promovido_em", "substitui_versao", "justificativa_emergencial") if v.tags.get(k)},
        "historico": historico(nome),
    }


def historico(nome: str) -> list[dict]:
    c = MlflowClient()
    # search_model_versions não traz os aliases; o modelo registrado traz o mapa alias -> versão
    aliases: dict[str, list[str]] = {}
    for alias, versao in c.get_registered_model(nome).aliases.items():
        aliases.setdefault(str(versao), []).append(alias)
    linhas = []
    for v in sorted(c.search_model_versions(f"name='{nome}'"), key=lambda x: int(x.version)):
        t = v.tags
        linhas.append({
            "versao": str(v.version), "aliases": aliases.get(str(v.version), []),
            "validacao": t.get("validacao"),
            "gate_r2": t.get("gate_r2"), "rfc": t.get("rfc"), "aprovado_por": t.get("aprovado_por"),
            "promovido_em": t.get("promovido_em"), "substituida_em": t.get("substituida_em"),
            "rollback_em": t.get("rollback_em"), "rollback_rfc": t.get("rollback_rfc"),
            "restaurada_em": t.get("restaurada_em"),
        })
    return linhas


def como_markdown(e: dict) -> str:
    cod, ds = e["codigo"], e["datasets"]
    linhas = [
        f"# Evidência de mudança — {e['modelo']} @{e['alias']}",
        "",
        f"Gerada em {e['gerado_em']}.",
        "",
        "| Elo | Valor |",
        "|---|---|",
        f"| Versão em `@{e['alias']}` | {e['versao']} (criada em {e['versao_criada_em']}) |",
        f"| Run | `{e['run_id']}` |",
        f"| Commit | `{cod['commit']}` ({cod['branch']}) |",
        f"| Pipeline | {cod['pipeline']} |",
        *[f"| Dataset | `{d['nome']}` digest `{d['digest']}` — {d['origem']} |" for d in ds],
        f"| r2 no holdout (gate) | {e['gate'].get('r2')} (champion anterior: {e['gate'].get('r2_champion')}) |",
        f"| Política do gate | sha `{e['gate'].get('politica_sha')}` |",
        f"| RFC | {e['mudanca'].get('rfc')} ({e['mudanca'].get('tipo_mudanca')}) |",
        f"| Aprovado por | {e['mudanca'].get('aprovado_por')} |",
        f"| Executado por | {e['mudanca'].get('promovido_por')} em {e['mudanca'].get('promovido_em')} |",
        f"| Substituiu a versão | {e['mudanca'].get('substitui_versao')} |",
        "",
        "## Histórico de versões",
        "",
        "| Versão | Aliases | Validação | r2 gate | RFC | Aprovado por | Promovida | Rollback |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for h in e["historico"]:
        linhas.append(
            f"| {h['versao']} | {', '.join(h['aliases']) or '-'} | {h['validacao'] or '-'} | "
            f"{h['gate_r2'] or '-'} | {h['rfc'] or '-'} | {h['aprovado_por'] or '-'} | "
            f"{h['promovido_em'] or '-'} | {h['rollback_em'] or '-'} |")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--alias", default="champion")
    p.add_argument("--formato", choices=["json", "markdown"], default="json")
    p.add_argument("--saida", default=None)
    p.add_argument("--politica", default=None)
    a = p.parse_args()
    evidencia = linhagem(carregar_politica(a.politica)["modelo"], a.alias)
    texto = (json.dumps(evidencia, indent=2, ensure_ascii=False, default=str)
             if a.formato == "json" else como_markdown(evidencia))
    if a.saida:
        open(a.saida, "w", encoding="utf-8").write(texto)
    print(texto)
