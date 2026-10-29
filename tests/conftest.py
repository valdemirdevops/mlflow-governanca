import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))


@pytest.fixture()
def mlflow_isolado(tmp_path, monkeypatch):
    """MLflow em SQLite descartável + contexto de CI simulado (GitHub Actions)."""
    import mlflow

    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "exemplo/mlflow-governanca")
    monkeypatch.setenv("GITHUB_SHA", "a1b2c3d4e5f6")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_RUN_ID", "1001")
    monkeypatch.setenv("GITHUB_ACTOR", "ana-dados")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)
    mlflow.set_tracking_uri(uri)
    yield tmp_path
    mlflow.set_tracking_uri(None)


@pytest.fixture()
def politica():
    from comum import carregar_politica

    return carregar_politica(RAIZ / "governanca.yml")
