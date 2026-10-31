import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.domain.polyline import codificar_polyline
from app.domain.routing import (
    Coordenada,
    ErroRoteamento,
    RotaNaoEncontrada,
)
from app.infrastructure.google_routes import (
    URL_COMPUTE_ROUTE_MATRIX,
    URL_COMPUTE_ROUTES,
    ServicoRoteamentoGoogle,
    converter_duracao_s,
)


AGORA = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)

CENTRO_DISTRIBUICAO = Coordenada(-12.971, -38.501)
BARRA = Coordenada(-13.006, -38.528)
PITUBA = Coordenada(-12.999, -38.460)


class TransporteFalso:
    """Registra as requisicoes e devolve uma resposta fixa."""

    def __init__(self, status: int = 200, corpo=None, erro=None):
        self.status = status
        self.corpo = corpo
        self.erro = erro
        self.requisicoes: list[httpx.Request] = []

    def __call__(self, requisicao: httpx.Request) -> httpx.Response:
        self.requisicoes.append(requisicao)

        if self.erro is not None:
            raise self.erro

        return httpx.Response(self.status, json=self.corpo)

    @property
    def ultimo_corpo(self) -> dict:
        return json.loads(self.requisicoes[-1].content)


def criar_servico(transporte: TransporteFalso, **opcoes):
    cliente = httpx.Client(transport=httpx.MockTransport(transporte))

    return ServicoRoteamentoGoogle(
        chave_api="chave-teste",
        cliente_http=cliente,
        relogio=lambda: AGORA,
        **opcoes,
    )


# Matriz de distancias


def test_matriz_envia_requisicao_no_formato_da_api():
    transporte = TransporteFalso(
        corpo=[
            {
                "destinationIndex": 1,
                "condition": "ROUTE_EXISTS",
                "distanceMeters": 5200,
                "duration": "900s",
                "staticDuration": "600s",
                "status": {},
            },
            {
                "condition": "ROUTE_EXISTS",
                "distanceMeters": 4100,
                "duration": "720s",
                "staticDuration": "540s",
                "status": {},
            },
        ]
    )
    servico = criar_servico(transporte)

    matriz = servico.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA, PITUBA]
    )

    requisicao = transporte.requisicoes[0]
    assert str(requisicao.url) == URL_COMPUTE_ROUTE_MATRIX
    assert requisicao.headers["X-Goog-Api-Key"] == "chave-teste"
    assert "staticDuration" in requisicao.headers["X-Goog-FieldMask"]

    corpo = transporte.ultimo_corpo
    assert corpo["travelMode"] == "DRIVE"
    assert corpo["routingPreference"] == "TRAFFIC_AWARE"
    assert corpo["origins"][0]["waypoint"]["location"]["latLng"] == {
        "latitude": -12.971,
        "longitude": -38.501,
    }
    assert len(corpo["destinations"]) == 2
    assert "departureTime" not in corpo

    # Indices iguais a zero sao omitidos pela API.
    assert matriz.distancia_m(0, 0) == 4100
    assert matriz.duracao_min(0, 1) == 15
    assert matriz.obter(0, 1).fator_transito == pytest.approx(1.5)


def test_matriz_marca_destino_sem_rota():
    transporte = TransporteFalso(
        corpo=[{"condition": "ROUTE_NOT_FOUND", "status": {}}]
    )
    matriz = criar_servico(transporte).calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA]
    )

    assert not matriz.obter(0, 0).rota_existe

    with pytest.raises(RotaNaoEncontrada):
        matriz.duracao_min(0, 0)


def test_matriz_elemento_com_status_de_erro():
    transporte = TransporteFalso(
        corpo=[
            {
                "condition": "ROUTE_EXISTS",
                "status": {"code": 3, "message": "invalido"},
            }
        ]
    )
    matriz = criar_servico(transporte).calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA]
    )

    assert not matriz.obter(0, 0).rota_existe


def test_matriz_incompleta_gera_erro():
    transporte = TransporteFalso(corpo=[])

    with pytest.raises(ErroRoteamento):
        criar_servico(transporte).calcular_matriz(
            [CENTRO_DISTRIBUICAO], [BARRA]
        )


def test_matriz_acima_do_limite_nao_chama_api():
    transporte = TransporteFalso(corpo=[])
    pontos = [Coordenada(-12.9, -38.5)] * 26

    with pytest.raises(ValueError):
        criar_servico(transporte).calcular_matriz(pontos, pontos)

    assert transporte.requisicoes == []


def test_limite_menor_na_preferencia_otima():
    transporte = TransporteFalso(corpo=[])
    pontos = [Coordenada(-12.9, -38.5)] * 11

    servico = criar_servico(
        transporte,
        preferencia_roteamento="TRAFFIC_AWARE_OPTIMAL",
    )

    with pytest.raises(ValueError):
        servico.calcular_matriz(pontos, pontos)


def test_partida_futura_e_enviada_em_utc():
    transporte = TransporteFalso(
        corpo=[{"condition": "ROUTE_EXISTS", "duration": "60s"}]
    )
    partida = AGORA + timedelta(hours=2)

    criar_servico(transporte).calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA], partida_em=partida
    )

    assert transporte.ultimo_corpo["departureTime"] == (
        "2026-10-30T14:00:00Z"
    )


def test_partida_no_passado_nao_e_enviada():
    transporte = TransporteFalso(
        corpo=[{"condition": "ROUTE_EXISTS", "duration": "60s"}]
    )

    criar_servico(transporte).calcular_matriz(
        [CENTRO_DISTRIBUICAO],
        [BARRA],
        partida_em=AGORA - timedelta(hours=1),
    )

    assert "departureTime" not in transporte.ultimo_corpo


# Rotas e geometria


def test_rota_com_paradas_e_geometria():
    geometria = [CENTRO_DISTRIBUICAO, BARRA, PITUBA, CENTRO_DISTRIBUICAO]
    transporte = TransporteFalso(
        corpo={
            "routes": [
                {
                    "distanceMeters": 15000,
                    "duration": "2400s",
                    "staticDuration": "1800s",
                    "polyline": {
                        "encodedPolyline": codificar_polyline(geometria)
                    },
                    "legs": [
                        {
                            "distanceMeters": 5000,
                            "duration": "800s",
                            "staticDuration": "600s",
                        },
                        {
                            "distanceMeters": 6000,
                            "duration": "900s",
                            "staticDuration": "700s",
                        },
                        {
                            "distanceMeters": 4000,
                            "duration": "700s",
                        },
                    ],
                }
            ]
        }
    )

    rota = criar_servico(transporte).calcular_rota(
        CENTRO_DISTRIBUICAO,
        CENTRO_DISTRIBUICAO,
        paradas=[BARRA, PITUBA],
    )

    requisicao = transporte.requisicoes[0]
    assert str(requisicao.url) == URL_COMPUTE_ROUTES
    assert "routes.polyline.encodedPolyline" in (
        requisicao.headers["X-Goog-FieldMask"]
    )
    assert len(transporte.ultimo_corpo["intermediates"]) == 2

    assert rota.distancia_m == 15000
    assert rota.duracao_min == 40
    assert rota.atraso_transito_min == 10
    assert len(rota.trechos) == 3
    assert rota.trechos[2].duracao_sem_transito_s == 700
    assert rota.pontos == geometria


def test_rota_sem_resultado():
    transporte = TransporteFalso(corpo={})

    with pytest.raises(RotaNaoEncontrada):
        criar_servico(transporte).calcular_rota(
            CENTRO_DISTRIBUICAO, BARRA
        )


def test_rota_com_paradas_demais():
    transporte = TransporteFalso(corpo={})

    with pytest.raises(ValueError):
        criar_servico(transporte).calcular_rota(
            CENTRO_DISTRIBUICAO, BARRA, paradas=[PITUBA] * 26
        )


# Erros de comunicacao


def test_erro_http_da_api_gera_erro_de_roteamento():
    transporte = TransporteFalso(
        status=403,
        corpo={"error": {"code": 403, "message": "API key not valid."}},
    )

    with pytest.raises(ErroRoteamento, match="403: API key not valid"):
        criar_servico(transporte).calcular_matriz(
            [CENTRO_DISTRIBUICAO], [BARRA]
        )


def test_falha_de_rede_gera_erro_de_roteamento():
    transporte = TransporteFalso(erro=httpx.ConnectTimeout("timeout"))

    with pytest.raises(ErroRoteamento):
        criar_servico(transporte).calcular_rota(
            CENTRO_DISTRIBUICAO, BARRA
        )


def test_chave_nao_aparece_na_mensagem_de_erro():
    transporte = TransporteFalso(status=500, corpo={})

    with pytest.raises(ErroRoteamento) as erro:
        criar_servico(transporte).calcular_matriz(
            [CENTRO_DISTRIBUICAO], [BARRA]
        )

    assert "chave-teste" not in str(erro.value)


# Configuracao


def test_chave_lida_do_ambiente(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave-ambiente")
    transporte = TransporteFalso(
        corpo=[{"condition": "ROUTE_EXISTS", "duration": "60s"}]
    )
    cliente = httpx.Client(transport=httpx.MockTransport(transporte))

    ServicoRoteamentoGoogle(cliente_http=cliente).calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA]
    )

    assert transporte.requisicoes[0].headers["X-Goog-Api-Key"] == (
        "chave-ambiente"
    )


def test_sem_chave_gera_erro(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    with pytest.raises(ValueError):
        ServicoRoteamentoGoogle()


def test_preferencia_invalida():
    with pytest.raises(ValueError):
        ServicoRoteamentoGoogle(
            chave_api="x", preferencia_roteamento="RAPIDO"
        )


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("123s", 123.0), ("1.5s", 1.5), (None, 0.0), ("", 0.0)],
)
def test_converter_duracao(valor, esperado):
    assert converter_duracao_s(valor) == esperado


def test_converter_duracao_invalida():
    with pytest.raises(ErroRoteamento):
        converter_duracao_s("10min")
