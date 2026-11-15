from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.distribution import (
    CentroDistribuicao,
    DistribuicaoEquidadeSLA,
    DistribuicaoInsercaoMaisBarata,
    DistribuidorPedidos,
    calcular_indice_equidade_sla,
)
from app.domain.models import Bairro, CategoriaProduto, Entregador, Pedido
from app.domain.routing import Coordenada
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


FUSO = ZoneInfo("America/Bahia")
PARTIDA = datetime(2026, 10, 30, 9, 0, tzinfo=FUSO)
CENTRO = CentroDistribuicao("Centro", Coordenada(-12.971, -38.501))


def criar_pedido(
    codigo,
    bairro,
    *,
    prazo,
    criado_em=None,
    categoria=CategoriaProduto.OUTRO,
    rapida=False,
    peso=1.0,
    volume=1.0,
    servico=10,
):
    criado_em = criado_em or PARTIDA - timedelta(hours=1)
    return Pedido(
        codigo=codigo,
        bairro=bairro,
        categoria_produto=categoria,
        cliente_clube=False,
        entrega_rapida=rapida,
        sla_dias_uteis=1,
        criado_em=criado_em,
        prazo_entrega_em=prazo,
        peso_kg=peso,
        volume_l=volume,
        tempo_servico_min=servico,
    )


def planejar(pedidos, estrategia, entregadores=None):
    entregadores = entregadores or [
        Entregador("CAM-01"),
        Entregador("CAM-02"),
    ]
    distribuidor = DistribuidorPedidos(
        ServicoRoteamentoSimulado(fator_transito=1.0),
        CENTRO,
        entregadores,
        estrategia,
    )
    return distribuidor.planejar(pedidos, PARTIDA)


def indice_do_plano(plano):
    atrasos = defaultdict(list)

    for parada in plano.paradas:
        pedido = parada.pedido
        if pedido.prazo_entrega_em is None:
            continue

        sla_min = (
            pedido.prazo_entrega_em - pedido.criado_em
        ).total_seconds() / 60
        if sla_min <= 0:
            continue

        atraso_min = max(
            0.0,
            (parada.saida_em - pedido.prazo_entrega_em).total_seconds()
            / 60,
        )
        atrasos[pedido.bairro.nome].append(atraso_min / sla_min)

    return calcular_indice_equidade_sla(atrasos)


def assinatura(plano):
    return tuple(
        (
            rota.entregador.codigo,
            tuple(
                tuple(parada.pedido.codigo for parada in viagem.paradas)
                for viagem in rota.viagens
            ),
        )
        for rota in plano.rotas
    )


def test_indice_equidade_pesa_bairros_igualmente_e_ignora_vazios():
    desequilibrado = calcular_indice_equidade_sla(
        {"A": [0.0, 0.0, 0.0], "B": [0.4], "SemPedidos": []}
    )
    sem_bairro_vazio = calcular_indice_equidade_sla(
        {"A": [0.0, 0.0, 0.0], "B": [0.4]}
    )
    equilibrado = calcular_indice_equidade_sla(
        {"A": [0.1], "B": [0.1]}
    )

    assert desequilibrado == pytest.approx(sem_bairro_vazio)
    assert desequilibrado > equilibrado
    assert calcular_indice_equidade_sla({"A": []}) == 0.0
    assert calcular_indice_equidade_sla({"A": [float("nan"), -1.0]}) == 0.0


def test_estrategia_respeita_capacidade_peso_volume_e_paradas():
    bairro = Bairro("Bairro", -12.971, -38.501)
    prazo = PARTIDA + timedelta(days=1)
    pedidos = [
        criar_pedido("P1", bairro, prazo=prazo, peso=2, volume=2),
        criar_pedido("P2", bairro, prazo=prazo, peso=2, volume=2),
        criar_pedido("P3", bairro, prazo=prazo, peso=8, volume=8),
    ]
    entregadores = [
        Entregador(
            "CAM-01",
            max_paradas_por_viagem=1,
            capacidade_peso_kg=3,
            capacidade_volume_l=3,
        )
    ]

    plano = planejar(pedidos, DistribuicaoEquidadeSLA(), entregadores)

    assert {p.pedido.codigo for p in plano.paradas} == {"P1", "P2"}
    assert [p.codigo for p in plano.nao_atribuidos] == ["P3"]
    assert all(len(v.paradas) <= 1 for v in plano.rotas[0].viagens)
    assert all(v.peso_kg <= 3 and v.volume_l <= 3 for v in plano.rotas[0].viagens)


def test_urgencia_e_sla_continuam_no_custo_da_estrategia():
    bairro = Bairro("Bairro", -12.971, -38.501)
    urgente = criar_pedido(
        "URGENTE",
        bairro,
        prazo=PARTIDA + timedelta(minutes=15),
        categoria=CategoriaProduto.MEDICAMENTO,
        rapida=True,
        servico=5,
    )
    normal = criar_pedido(
        "NORMAL",
        bairro,
        prazo=PARTIDA + timedelta(days=3),
        servico=5,
    )

    plano = planejar(
        [urgente, normal],
        DistribuicaoEquidadeSLA(),
        [Entregador("CAM-01")],
    )

    assert [p.pedido.codigo for p in plano.paradas] == ["URGENTE", "NORMAL"]
    assert not plano.paradas[0].atrasada


def test_equidade_reduz_concentracao_de_atrasos_ante_insercao_mais_barata():
    # As coordenadas iguais isolam o efeito territorial: os dois bairros
    # têm o mesmo custo de deslocamento e cada rota pode receber pedidos.
    bairro_a = Bairro("Bairro A", -12.971, -38.501)
    bairro_b = Bairro("Bairro B", -12.971, -38.501)
    prazo = PARTIDA + timedelta(minutes=15)
    pedidos = [
        criar_pedido(f"A{n}", bairro_a, prazo=prazo)
        for n in range(1, 4)
    ] + [criar_pedido("B1", bairro_b, prazo=prazo)]

    baseline = planejar(pedidos, DistribuicaoInsercaoMaisBarata())
    equidade = planejar(pedidos, DistribuicaoEquidadeSLA())

    assert indice_do_plano(equidade) < indice_do_plano(baseline)


def test_estrategia_e_deterministica_para_as_mesmas_entradas():
    bairro_a = Bairro("Bairro A", -12.971, -38.501)
    bairro_b = Bairro("Bairro B", -12.971, -38.501)
    prazo = PARTIDA + timedelta(minutes=15)
    pedidos = [
        criar_pedido("A1", bairro_a, prazo=prazo),
        criar_pedido("A2", bairro_a, prazo=prazo),
        criar_pedido("B1", bairro_b, prazo=prazo),
    ]

    primeira = planejar(pedidos, DistribuicaoEquidadeSLA())
    segunda = planejar(pedidos, DistribuicaoEquidadeSLA())

    assert assinatura(primeira) == assinatura(segunda)
