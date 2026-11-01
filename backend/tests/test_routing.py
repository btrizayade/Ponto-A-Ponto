from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.domain.models import Bairro, CategoriaProduto, Pedido
from app.domain.polyline import codificar_polyline, decodificar_polyline
from app.domain.priority_scoring import calcular_prioridade
from app.domain.routing import (
    Coordenada,
    ElementoMatriz,
    MatrizDistancias,
    RotaNaoEncontrada,
    estimar_tempo_entrega_min,
)
from app.infrastructure.routing_factory import criar_servico_roteamento
from app.infrastructure.simulated_routing import (
    FATOR_TRANSITO_NORMAL,
    FATOR_TRANSITO_PICO,
    ServicoRoteamentoSimulado,
    calcular_distancia_haversine_m,
)


FUSO_HORARIO = ZoneInfo("America/Bahia")

CENTRO_DISTRIBUICAO = Coordenada(-12.971, -38.501)
BARRA = Coordenada(-13.006, -38.528)
PITUBA = Coordenada(-12.999, -38.460)
ITAPUA = Coordenada(-12.940, -38.358)

HORARIO_PICO = datetime(2026, 10, 30, 18, 0, tzinfo=FUSO_HORARIO)
HORARIO_NORMAL = datetime(2026, 10, 30, 14, 0, tzinfo=FUSO_HORARIO)


def criar_pedido(bairro: Bairro, tempo_servico_min: int = 5) -> Pedido:
    return Pedido(
        codigo="PED-TESTE",
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=1,
        criado_em=datetime(2026, 10, 30, 9, 0, tzinfo=FUSO_HORARIO),
        prazo_entrega_em=datetime(
            2026, 10, 30, 16, 0, tzinfo=FUSO_HORARIO
        ),
        tempo_servico_min=tempo_servico_min,
    )


# Polyline


def test_polyline_exemplo_oficial_do_formato():
    pontos = [
        Coordenada(38.5, -120.2),
        Coordenada(40.7, -120.95),
        Coordenada(43.252, -126.453),
    ]

    assert codificar_polyline(pontos) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def test_polyline_ida_e_volta_preserva_pontos():
    pontos = [CENTRO_DISTRIBUICAO, BARRA, PITUBA, ITAPUA]

    assert decodificar_polyline(codificar_polyline(pontos)) == pontos


def test_polyline_invalida_gera_erro():
    with pytest.raises(ValueError):
        decodificar_polyline("_p~iF~ps|U_")


# Coordenada


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (0, 181), (float("nan"), 0), (True, 0)],
)
def test_coordenada_invalida(latitude, longitude):
    with pytest.raises(ValueError):
        Coordenada(latitude, longitude)


def test_coordenada_do_pedido_usa_bairro():
    bairro = Bairro("Barra", -13.006, -38.528)

    assert Coordenada.do_pedido(criar_pedido(bairro)) == BARRA


# Matriz


def test_matriz_sem_rota_gera_erro():
    matriz = MatrizDistancias(
        origens=[CENTRO_DISTRIBUICAO],
        destinos=[BARRA],
        elementos={
            (0, 0): ElementoMatriz(0, 0, rota_existe=False),
        },
    )

    with pytest.raises(RotaNaoEncontrada):
        matriz.duracao_min(0, 0)


def test_matriz_com_indices_errados_nao_esta_completa():
    # Mesma quantidade de elementos, mas um par fora dos limites.
    matriz = MatrizDistancias(
        origens=[CENTRO_DISTRIBUICAO],
        destinos=[BARRA, PITUBA],
        elementos={
            (0, 0): ElementoMatriz(0, 0, True),
            (0, 5): ElementoMatriz(0, 5, True),
        },
    )

    assert not matriz.esta_completa()


def test_fator_transito_do_elemento():
    elemento = ElementoMatriz(
        0, 0, True,
        distancia_m=1000,
        duracao_s=900,
        duracao_sem_transito_s=600,
    )

    assert elemento.fator_transito == pytest.approx(1.5)
    assert elemento.duracao_min == 15


# Provedor simulado


def test_haversine_distancia_conhecida():
    # Um grau de latitude mede cerca de 111,2 km.
    distancia = calcular_distancia_haversine_m(
        Coordenada(0, 0),
        Coordenada(1, 0),
    )

    assert distancia == pytest.approx(111_195, rel=1e-3)


def test_matriz_simulada_completa_e_simetrica():
    servico = ServicoRoteamentoSimulado()
    pontos = [CENTRO_DISTRIBUICAO, BARRA, PITUBA]

    matriz = servico.calcular_matriz(
        pontos, pontos, partida_em=HORARIO_NORMAL
    )

    assert matriz.esta_completa()
    assert matriz.distancia_m(0, 0) == 0
    assert matriz.distancia_m(0, 1) == matriz.distancia_m(1, 0)
    assert matriz.distancia_m(0, 1) > 0


def test_horario_de_pico_aumenta_duracao():
    servico = ServicoRoteamentoSimulado()

    pico = servico.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [ITAPUA], partida_em=HORARIO_PICO
    ).obter(0, 0)
    normal = servico.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [ITAPUA], partida_em=HORARIO_NORMAL
    ).obter(0, 0)

    assert pico.distancia_m == normal.distancia_m
    assert pico.fator_transito == pytest.approx(FATOR_TRANSITO_PICO)
    assert normal.fator_transito == pytest.approx(FATOR_TRANSITO_NORMAL)
    assert pico.duracao_s > normal.duracao_s


def test_fator_transito_fixo_do_cenario():
    servico = ServicoRoteamentoSimulado(fator_transito=2.0)

    elemento = servico.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA], partida_em=HORARIO_NORMAL
    ).obter(0, 0)

    assert elemento.fator_transito == pytest.approx(2.0)


def test_fator_transito_menor_que_um_e_rejeitado():
    with pytest.raises(ValueError):
        ServicoRoteamentoSimulado(fator_transito=0.5)


def test_rota_simulada_com_paradas():
    servico = ServicoRoteamentoSimulado()

    rota = servico.calcular_rota(
        CENTRO_DISTRIBUICAO,
        CENTRO_DISTRIBUICAO,
        paradas=[BARRA, PITUBA],
        partida_em=HORARIO_PICO,
    )

    assert len(rota.trechos) == 3
    assert rota.distancia_m == sum(t.distancia_m for t in rota.trechos)
    assert rota.pontos == [CENTRO_DISTRIBUICAO, BARRA, PITUBA,
                           CENTRO_DISTRIBUICAO]
    assert rota.atraso_transito_min > 0


def test_partida_sem_fuso_e_rejeitada():
    servico = ServicoRoteamentoSimulado()

    with pytest.raises(ValueError):
        servico.calcular_matriz(
            [CENTRO_DISTRIBUICAO], [BARRA],
            partida_em=datetime(2026, 10, 30, 14, 0),
        )


def test_lista_vazia_e_rejeitada():
    with pytest.raises(ValueError):
        ServicoRoteamentoSimulado().calcular_matriz([], [BARRA])


# Integracao com o motor de prioridade (F02)


def test_estimativa_soma_deslocamento_e_servico():
    servico = ServicoRoteamentoSimulado()
    bairro = Bairro("Itapua", -12.940, -38.358)
    pedido = criar_pedido(bairro, tempo_servico_min=7)

    deslocamento = servico.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [ITAPUA], partida_em=HORARIO_PICO
    ).duracao_min(0, 0)

    estimativa = estimar_tempo_entrega_min(
        servico, CENTRO_DISTRIBUICAO, pedido, partida_em=HORARIO_PICO
    )

    assert estimativa == pytest.approx(deslocamento + 7)


def test_transito_intenso_aumenta_prioridade():
    bairro = Bairro("Itapua", -12.940, -38.358)
    pedido = criar_pedido(bairro)
    agora = datetime(2026, 10, 30, 14, 30, tzinfo=FUSO_HORARIO)

    prioridades = []

    for fator in (1.0, 3.0):
        servico = ServicoRoteamentoSimulado(fator_transito=fator)
        estimativa = estimar_tempo_entrega_min(
            servico, CENTRO_DISTRIBUICAO, pedido, partida_em=agora
        )
        prioridades.append(
            calcular_prioridade(
                pedido,
                agora=agora,
                tempo_estimado_entrega_min=estimativa,
            )
        )

    assert prioridades[1] > prioridades[0]


# Fabrica


def test_fabrica_sem_chave_usa_simulado(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("PROVEDOR_MAPAS", raising=False)

    assert isinstance(
        criar_servico_roteamento(), ServicoRoteamentoSimulado
    )


def test_fabrica_provedor_desconhecido(monkeypatch):
    with pytest.raises(ValueError):
        criar_servico_roteamento("outro")


def test_fabrica_google_sem_chave_falha(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    with pytest.raises(ValueError):
        criar_servico_roteamento("google")
