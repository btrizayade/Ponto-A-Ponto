from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.domain.routing import Coordenada
from app.infrastructure import database
from app.infrastructure.controle_uso_api import (
    TIPO_ELEMENTOS_MATRIZ,
    TIPO_ROTAS,
    ControleUsoApi,
    LimiteUsoExcedido,
)
from app.infrastructure.google_routes import ServicoRoteamentoGoogle


# 12h em Salvador; 08h no horario do Pacifico.
AGORA = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)

CENTRO_DISTRIBUICAO = Coordenada(-12.971, -38.501)
BARRA = Coordenada(-13.006, -38.528)
PITUBA = Coordenada(-12.999, -38.460)


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    """Prepara um banco isolado para cada teste."""

    diretorio = tmp_path / "data"

    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")


class Relogio:
    """Relogio controlavel para simular a virada do dia."""

    def __init__(self, agora: datetime) -> None:
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora


def criar_controle(relogio=None, matriz=10, rotas=2) -> ControleUsoApi:
    return ControleUsoApi(
        {TIPO_ELEMENTOS_MATRIZ: matriz, TIPO_ROTAS: rotas},
        relogio=relogio or Relogio(AGORA),
    )


# Controle de uso


def test_reserva_acumula_uso_do_dia(banco_temporario):
    controle = criar_controle()

    controle.reservar(TIPO_ELEMENTOS_MATRIZ, 4)
    controle.reservar(TIPO_ELEMENTOS_MATRIZ, 6)

    assert controle.uso_do_dia(TIPO_ELEMENTOS_MATRIZ) == 10
    assert controle.restante_do_dia(TIPO_ELEMENTOS_MATRIZ) == 0


def test_reserva_acima_do_limite_e_recusada(banco_temporario):
    controle = criar_controle()
    controle.reservar(TIPO_ELEMENTOS_MATRIZ, 8)

    with pytest.raises(LimiteUsoExcedido):
        controle.reservar(TIPO_ELEMENTOS_MATRIZ, 3)

    # A reserva recusada nao consome o limite.
    assert controle.uso_do_dia(TIPO_ELEMENTOS_MATRIZ) == 8


def test_consulta_maior_que_o_limite_e_recusada(banco_temporario):
    controle = criar_controle()

    with pytest.raises(LimiteUsoExcedido):
        controle.reservar(TIPO_ELEMENTOS_MATRIZ, 11)

    assert controle.uso_do_dia(TIPO_ELEMENTOS_MATRIZ) == 0


def test_tipos_tem_limites_independentes(banco_temporario):
    controle = criar_controle()

    controle.reservar(TIPO_ELEMENTOS_MATRIZ, 10)
    controle.reservar(TIPO_ROTAS, 2)

    assert controle.uso_do_dia(TIPO_ELEMENTOS_MATRIZ) == 10
    assert controle.uso_do_dia(TIPO_ROTAS) == 2


def test_uso_persiste_entre_instancias(banco_temporario):
    criar_controle().reservar(TIPO_ROTAS, 2)

    with pytest.raises(LimiteUsoExcedido):
        criar_controle().reservar(TIPO_ROTAS, 1)


def test_limite_reinicia_a_meia_noite_do_pacifico(banco_temporario):
    relogio = Relogio(AGORA)
    controle = criar_controle(relogio)
    controle.reservar(TIPO_ROTAS, 2)

    # 23h59 no Pacifico: ainda o mesmo dia da cota.
    relogio.agora = datetime(2026, 10, 31, 6, 59, tzinfo=timezone.utc)
    with pytest.raises(LimiteUsoExcedido):
        controle.reservar(TIPO_ROTAS, 1)

    # 00h no Pacifico: novo dia.
    relogio.agora += timedelta(minutes=1)
    controle.reservar(TIPO_ROTAS, 1)

    assert controle.uso_do_dia(TIPO_ROTAS) == 1


@pytest.mark.parametrize("limite", [0, -1])
def test_limite_deve_ser_positivo(banco_temporario, limite):
    with pytest.raises(ValueError):
        criar_controle(matriz=limite)


def test_limites_lidos_do_ambiente(banco_temporario, monkeypatch):
    monkeypatch.setenv("LIMITE_DIARIO_ELEMENTOS_MATRIZ", "3")
    monkeypatch.setenv("LIMITE_DIARIO_ROTAS", "1")

    controle = ControleUsoApi.do_ambiente()

    assert controle.restante_do_dia(TIPO_ELEMENTOS_MATRIZ) == 3
    assert controle.restante_do_dia(TIPO_ROTAS) == 1


def test_limite_do_ambiente_invalido(banco_temporario, monkeypatch):
    monkeypatch.setenv("LIMITE_DIARIO_ROTAS", "muitos")

    with pytest.raises(ValueError):
        ControleUsoApi.do_ambiente()


# Integracao com o servico da Google


def test_servico_google_bloqueia_sem_chamar_api(banco_temporario):
    chamadas = []

    def transporte(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return httpx.Response(
            200,
            json=[
                {"condition": "ROUTE_EXISTS", "duration": "60s"},
                {
                    "destinationIndex": 1,
                    "condition": "ROUTE_EXISTS",
                    "duration": "60s",
                },
            ],
        )

    servico = ServicoRoteamentoGoogle(
        chave_api="chave-teste",
        cliente_http=httpx.Client(transport=httpx.MockTransport(transporte)),
        relogio=lambda: AGORA,
        controle_uso=criar_controle(matriz=3),
    )

    servico.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA, PITUBA])

    with pytest.raises(LimiteUsoExcedido):
        servico.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA, PITUBA])

    assert len(chamadas) == 1
