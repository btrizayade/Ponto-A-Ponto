import importlib

from app.infrastructure import database


def _recarregar_com_caminho(monkeypatch, caminho: str | None, diretorio_execucao=None):
    with monkeypatch.context() as ambiente:
        if caminho is None:
            ambiente.delenv(database.VARIAVEL_CAMINHO_BANCO, raising=False)
        else:
            ambiente.setenv(database.VARIAVEL_CAMINHO_BANCO, caminho)
        if diretorio_execucao is not None:
            ambiente.chdir(diretorio_execucao)

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


def test_variavel_vazia_preserva_caminho_padrao(monkeypatch):
    for valor in ("", "   "):
        caminho, diretorio = _recarregar_com_caminho(monkeypatch, valor)

        esperado = database.BACKEND_DIR / "data" / "pontoaponto.db"
        assert caminho == esperado
        assert diretorio == esperado.parent


def test_caminho_absoluto_e_diretorio_derivado_da_variavel(monkeypatch, tmp_path):
    caminho_alternativo = tmp_path / "isolado" / "pontoaponto-teste.db"

    caminho, diretorio = _recarregar_com_caminho(
        monkeypatch,
        str(caminho_alternativo),
    )

    assert caminho == caminho_alternativo
    assert diretorio == caminho_alternativo.parent


def test_caminho_relativo_e_resolvido_a_partir_do_backend_independente_do_cwd(
    monkeypatch,
    tmp_path,
):
    caminho_relativo = "dados-teste/execucao.db"
    cwd_a = tmp_path / "a"
    cwd_b = tmp_path / "b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    resultado_a = _recarregar_com_caminho(
        monkeypatch,
        caminho_relativo,
        cwd_a,
    )
    resultado_b = _recarregar_com_caminho(
        monkeypatch,
        caminho_relativo,
        cwd_b,
    )

    esperado = (database.BACKEND_DIR / caminho_relativo).resolve()
    assert resultado_a == (esperado, esperado.parent)
    assert resultado_b == (esperado, esperado.parent)
