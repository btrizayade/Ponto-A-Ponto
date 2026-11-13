from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.api.estado import _Historico, _indicadores_territoriais
from app.domain.distribution import Parada, Viagem, calcular_indice_equidade_sla
from app.domain.models import Bairro, CategoriaProduto, Entregador, Pedido, StatusPedido
from app.domain.simulation import EventoSimulacao, TipoEvento
from app.infrastructure import database
from app.infrastructure.seed import inicializar_bairros_cenario_01


FUSO = ZoneInfo("America/Bahia")
AGORA = datetime(2026, 10, 30, 10, 0, tzinfo=FUSO)
BARRA = Bairro("Barra", -13.006, -38.528)


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    database.inicializar_banco()
    inicializar_bairros_cenario_01()


def criar_pedido(codigo, *, prazo, criado_em=None, bairro=BARRA):
    return Pedido(
        codigo=codigo,
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=1,
        criado_em=criado_em or AGORA - timedelta(hours=1),
        prazo_entrega_em=prazo,
    )


def criar_evento(tipo, pedido, instante, *, status=None, entregador=None):
    return EventoSimulacao(
        sequencia=1,
        instante=instante,
        tipo=tipo,
        pedido_codigo=pedido.codigo,
        entregador_codigo=entregador,
        viagem_numero=1 if entregador else None,
        status_novo=status,
        atraso_min=None,
    )


def simular(pedidos, status, eventos=(), plano=None, agora=AGORA):
    simulacao = SimpleNamespace(
        pedidos=pedidos,
        status_dos_pedidos=lambda: status,
        agora=agora,
        fim_expediente=agora.replace(hour=17, minute=0),
        plano=plano,
    )
    historico = _Historico(list(eventos))
    return _indicadores_territoriais(simulacao, historico, status)


def por_nome(indicadores):
    bairros, _ = indicadores
    return {item.bairro: item for item in bairros}


def test_bairros_sem_pedidos_sao_exibidos_com_metricas_nulas(
    banco_temporario,
):
    bairros, equidade = simular([], {})

    assert len(bairros) == 8
    assert all(item.total_pedidos == 0 for item in bairros)
    assert all(item.tempo_medio_entrega_min is None for item in bairros)
    assert all(item.percentual_cumprimento_sla is None for item in bairros)
    assert equidade.indice_equidade_territorial_real is None
    assert equidade.melhor_bairro is None
    assert equidade.bairros_com_amostras_validas == 0


def test_pedido_sem_sla_valido_nao_entra_nos_indicadores_de_sla(
    banco_temporario,
):
    pedido = criar_pedido("SEM-SLA", prazo=None)
    entregue_em = AGORA - timedelta(minutes=10)
    eventos = [
        criar_evento(
            TipoEvento.PEDIDO_ENTREGUE,
            pedido,
            entregue_em,
            status=StatusPedido.ENTREGUE,
            entregador="CAM-01",
        )
    ]

    bairros, equidade = simular(
        [pedido],
        {pedido.codigo: StatusPedido.ENTREGUE},
        eventos,
    )
    barra = por_nome((bairros, equidade))["Barra"]

    assert barra.total_pedidos == 1
    assert barra.entregues == 1
    assert barra.tempo_medio_entrega_min == 50.0
    assert barra.entregues_com_sla_valido == 0
    assert barra.entregues_no_prazo == 0
    assert barra.entregues_atrasados == 0
    assert barra.percentual_cumprimento_sla is None
    assert barra.taxa_atraso is None
    assert barra.atraso_medio_normalizado_sla is None
    assert equidade.indice_equidade_territorial_real is None


def test_horario_real_define_atraso_e_previsao_fica_so_em_risco(
    banco_temporario,
):
    vencido = criar_pedido("VENCIDO", prazo=AGORA - timedelta(minutes=5))
    futuro = criar_pedido("RISCO", prazo=AGORA + timedelta(minutes=5))
    eventos = [
        criar_evento(
            TipoEvento.PEDIDO_ENTREGUE,
            vencido,
            AGORA + timedelta(minutes=5),
            status=StatusPedido.ENTREGUE,
            entregador="CAM-01",
        ),
        criar_evento(
            TipoEvento.PEDIDO_ATRIBUIDO,
            futuro,
            AGORA,
            status=StatusPedido.ATRIBUIDO,
            entregador="CAM-02",
        ),
    ]
    entregador = Entregador("CAM-02")
    parada = Parada(
        futuro,
        chegada_em=AGORA + timedelta(minutes=20),
        saida_em=AGORA + timedelta(minutes=25),
    )
    viagem = Viagem(
        numero=1,
        partida_em=AGORA,
        retorno_em=AGORA + timedelta(minutes=30),
        distancia_m=1000,
        paradas=[parada],
    )
    plano = SimpleNamespace(
        rotas=[SimpleNamespace(entregador=entregador, viagens=[viagem])]
    )

    bairros, equidade = simular(
        [vencido, futuro],
        {
            vencido.codigo: StatusPedido.ENTREGUE,
            futuro.codigo: StatusPedido.EM_ROTA,
        },
        eventos,
        plano,
    )
    barra = por_nome((bairros, equidade))["Barra"]

    assert barra.entregues == 1
    assert barra.entregues_atrasados == 1
    assert barra.atraso_medio_min == 10.0
    assert barra.pendentes_vencidos == 0
    assert barra.em_risco_sla == 1
    assert barra.atraso_medio_normalizado_sla == round(10 / 55, 4)
    assert equidade.indice_equidade_territorial_real == round(
        calcular_indice_equidade_sla({"Barra": [10 / 55]}),
        4,
    )


def test_pendentes_vencidos_sao_separados_de_atrasos_reais(
    banco_temporario,
):
    pedido = criar_pedido("PENDENTE", prazo=AGORA - timedelta(minutes=1))

    bairros, equidade = simular(
        [pedido],
        {pedido.codigo: StatusPedido.NA_FILA},
    )
    barra = por_nome((bairros, equidade))["Barra"]

    assert barra.pendentes == 1
    assert barra.pendentes_vencidos == 1
    assert barra.entregues_atrasados == 0
    assert barra.atraso_medio_min is None
    assert barra.taxa_atraso is None
    assert equidade.indice_equidade_territorial_real is None


def test_bairro_sem_amostra_valida_nao_entra_na_equidade_territorial(
    banco_temporario,
):
    pituba = Bairro("Pituba", -12.999, -38.460)
    no_prazo = criar_pedido(
        "VALIDO-BARRA",
        prazo=AGORA + timedelta(minutes=30),
    )
    sem_sla = criar_pedido("SEM-SLA-PITUBA", prazo=None, bairro=pituba)
    eventos = [
        criar_evento(
            TipoEvento.PEDIDO_ENTREGUE,
            no_prazo,
            AGORA,
            status=StatusPedido.ENTREGUE,
            entregador="CAM-01",
        ),
        criar_evento(
            TipoEvento.PEDIDO_ENTREGUE,
            sem_sla,
            AGORA,
            status=StatusPedido.ENTREGUE,
            entregador="CAM-02",
        ),
    ]

    bairros, equidade = simular(
        [no_prazo, sem_sla],
        {
            no_prazo.codigo: StatusPedido.ENTREGUE,
            sem_sla.codigo: StatusPedido.ENTREGUE,
        },
        eventos,
    )
    por_bairro = por_nome((bairros, equidade))

    assert por_bairro["Barra"].atraso_medio_normalizado_sla == 0.0
    assert por_bairro["Pituba"].entregues == 1
    assert por_bairro["Pituba"].entregues_com_sla_valido == 0
    assert por_bairro["Pituba"].atraso_medio_normalizado_sla is None
    assert equidade.bairros_com_amostras_validas == 1
    assert equidade.melhor_bairro == "Barra"
    assert equidade.pior_bairro == "Barra"
    assert equidade.indice_equidade_territorial_real == 0.0
