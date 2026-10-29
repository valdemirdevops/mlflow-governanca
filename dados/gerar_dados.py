"""Gera os dados SINTÉTICOS do laboratório, no formato do dataset Unicorn (50 startups).

Os números são fictícios: servem só para treinar, comparar e promover modelos.
Rodar de novo com a mesma semente produz exatamente os mesmos arquivos, o que
mantém o `digest` registrado no MLflow estável.

    python dados/gerar_dados.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

PASTA = Path(__file__).parent
ESTADOS = ["New York", "California", "Florida"]
EFEITO_ESTADO = {"New York": 0.0, "California": -2500.0, "Florida": 3000.0}


def gerar(n: int, semente: int, ruido: float) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    rd = rng.uniform(0, 165_000, n)
    adm = rng.uniform(50_000, 185_000, n)
    mkt = rng.uniform(0, 470_000, n)
    estado = rng.choice(ESTADOS, n)
    lucro = (
        50_000
        + 0.80 * rd
        - 0.03 * adm
        + 0.03 * mkt
        + np.vectorize(EFEITO_ESTADO.get)(estado)
        + rng.normal(0, ruido, n)
    )
    return pd.DataFrame({
        "R&D Spend": rd.round(2),
        "Administration": adm.round(2),
        "Marketing Spend": mkt.round(2),
        "State": estado,
        "Profit": lucro.round(2),
    })


if __name__ == "__main__":
    # Snapshot de setembro: menos linhas e mais ruído
    gerar(120, semente=9, ruido=14_000).to_csv(PASTA / "unicorn-2026-09.csv", index=False)
    # Snapshot de outubro: mais linhas, dados mais limpos
    gerar(400, semente=10, ruido=7_000).to_csv(PASTA / "unicorn-2026-10.csv", index=False)
    # Holdout FIXO usado pelo gate para comparar challenger e champion
    gerar(100, semente=2026, ruido=7_000).to_csv(PASTA / "holdout.csv", index=False)
    print("Arquivos gerados em", PASTA)
