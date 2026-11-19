import importlib

from app.infrastructure import database


def _recarregar_com_caminho(monkeypatch, caminho: str | None):
    with monkeypatch.context() as ambiente:
        if caminho is None:
            ambiente.delenv(database.VARIAVEL_CAMINHO_BANCO, raising=False)
        else:
            ambiente.setenv(database.VARIAVEL_CAMINHO_BANCO, caminho)

        modulo = importlib.reload(database)
        resultado = modulo.DATABASE_PATH, modulo.DATABASE_DIR

    # Restaura as constantes do módulo de acordo com o ambiente original do teste.
    importlib.reload(database)
    return resultado


def test_caminho_padrao_quando_variavel_nao_esta_definida(monkeypatch):
    caminho, diretorio = _recarregar_com_caminho(monkeypatch, None)

    esperado = database.BACKEND_DIR / "data" / "pontoaponto.db"
    assert caminho == esperado
    assert diretorio == esperado.parent


def test_caminho_alternativo_e_diretorio_derivado_da_variavel(monkeypatch, tmp_path):
    caminho_alternativo = tmp_path / "isolado" / "pontoaponto-teste.db"

    caminho, diretorio = _recarregar_com_caminho(
        monkeypatch,
        str(caminho_alternativo),
    )

    assert caminho == caminho_alternativo
    assert diretorio == caminho_alternativo.parent
