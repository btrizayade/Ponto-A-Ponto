from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.distribution import CentroDistribuicao, DistribuidorPedidos
from app.domain.models import Bairro, CategoriaProduto, Entregador, Pedido
from app.domain.models import StatusPedido as S
from app.domain.routing import Coordenada
from app.domain.simulation import (
    EstadoExecucao,
    RelogioSimulado,
    Simulacao,
    TipoEvento as T,
)
from app.api.registro import SimulacaoAtiva
from app.infrastructure.auditoria_repository import AuditoriaSimulacao
from app.infrastructure.execucao_automatica import sincronizar_relogio
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


FUSO = ZoneInfo("America/Bahia")
# Sexta-feira.
INICIO = datetime(2026, 10, 30, 9, 0, tzinfo=FUSO)
CRIADO_EM = datetime(2026, 10, 29, 9, 0, tzinfo=FUSO)

CENTRO = CentroDistribuicao("Comercio", Coordenada(-12.971, -38.501))

BARRA = Bairro("Barra", -13.006, -38.528)
BROTAS = Bairro("Brotas", -12.986, -38.482)
PITUBA = Bairro("Pituba", -12.999, -38.460)
ITAPUA = Bairro("Itapua", -12.940, -38.358)


def criar_pedido(
    codigo: str,
    bairro: Bairro,
    prazo: datetime | None = None,
    criado_em: datetime = CRIADO_EM,
    peso_kg: float = 1.0,
) -> Pedido:
    return Pedido(
        codigo=codigo,
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=1,
        criado_em=criado_em,
        prazo_entrega_em=prazo or INICIO + timedelta(days=3),
        peso_kg=peso_kg,
    )


PEDIDOS = [
    criar_pedido("P1", BARRA),
    criar_pedido("P2", PITUBA),
    criar_pedido("P3", BROTAS),
    criar_pedido("P4", ITAPUA),
]


def criar_simulacao(
    pedidos=PEDIDOS,
    inicio=INICIO,
    entregadores=None,
    observadores=(),
) -> Simulacao:
    distribuidor = DistribuidorPedidos(
        ServicoRoteamentoSimulado(fator_transito=1.0),
        CENTRO,
        entregadores or [Entregador("CAM-01"), Entregador("CAM-02")],
    )

    return Simulacao(
        pedidos, distribuidor, inicio, observadores=observadores
    )


def tipos(eventos):
    return [e.tipo for e in eventos]


# Inicio


def test_inicio_coloca_os_pedidos_na_fila_e_atribui():
    simulacao = criar_simulacao()

    eventos = simulacao.iniciar()

    assert simulacao.iniciada
    assert all(e.instante == INICIO for e in eventos)
    assert eventos[0].tipo == T.SIMULACAO_INICIADA
    assert tipos(eventos).count(T.PEDIDO_NA_FILA) == len(PEDIDOS)
    assert tipos(eventos).count(T.PEDIDO_ATRIBUIDO) == len(PEDIDOS)
    # Os caminhoes saem no inicio da simulacao.
    assert T.VIAGEM_INICIADA in tipos(eventos)
    assert set(simulacao.status_dos_pedidos().values()) == {S.EM_ROTA}


def test_iniciar_duas_vezes_e_rejeitado():
    simulacao = criar_simulacao()
    simulacao.iniciar()

    with pytest.raises(RuntimeError):
        simulacao.iniciar()


def test_eventos_de_fila_seguem_a_ordem_de_prioridade():
    simulacao = criar_simulacao()

    eventos = simulacao.iniciar()
    na_fila = [e.pedido_codigo for e in eventos if e.tipo == T.PEDIDO_NA_FILA]

    assert na_fila == [p.codigo for p in simulacao.ordem_fila]


# Execucao por etapas


def test_cada_etapa_processa_um_instante():
    simulacao = criar_simulacao()
    simulacao.iniciar()

    while not simulacao.concluida:
        proximo = simulacao.proximo_instante
        eventos = simulacao.proxima_etapa()

        assert eventos
        assert {e.instante for e in eventos} == {proximo}
        assert simulacao.agora == proximo

    assert simulacao.proximo_instante is None
    assert simulacao.proxima_etapa() == []


def test_primeira_etapa_inicia_a_simulacao():
    simulacao = criar_simulacao()

    eventos = simulacao.proxima_etapa()

    assert simulacao.iniciada
    assert eventos[0].tipo == T.SIMULACAO_INICIADA


def test_status_de_cada_pedido_segue_o_ciclo_completo():
    simulacao = criar_simulacao()

    simulacao.executar_ate_o_fim()

    for pedido in PEDIDOS:
        mudancas = [
            (e.status_anterior, e.status_novo)
            for e in simulacao.historico
            if e.pedido_codigo == pedido.codigo and e.status_novo
        ]
        assert mudancas == [
            (S.PENDENTE, S.NA_FILA),
            (S.NA_FILA, S.ATRIBUIDO),
            (S.ATRIBUIDO, S.EM_ROTA),
            (S.EM_ROTA, S.ENTREGUE),
        ]


def test_historico_e_sequencial_e_ordenado_no_tempo():
    simulacao = criar_simulacao()

    simulacao.executar_ate_o_fim()
    historico = simulacao.historico

    assert [e.sequencia for e in historico] == list(
        range(1, len(historico) + 1)
    )
    instantes = [e.instante for e in historico]
    assert instantes == sorted(instantes)
    assert historico[-1].tipo == T.SIMULACAO_CONCLUIDA
    assert historico[-1].instante == simulacao.plano.termino_em
    assert simulacao.concluida


def test_retorno_ao_centro_vem_antes_da_proxima_viagem():
    # Uma parada por viagem: a viagem 2 sai quando a 1 termina.
    entregador = Entregador("CAM-01", max_paradas_por_viagem=1)
    simulacao = criar_simulacao(PEDIDOS[:2], entregadores=[entregador])

    simulacao.executar_ate_o_fim()
    viagens = [
        (e.tipo, e.viagem_numero)
        for e in simulacao.historico
        if e.tipo in (T.VIAGEM_INICIADA, T.VIAGEM_CONCLUIDA)
    ]

    assert viagens == [
        (T.VIAGEM_INICIADA, 1),
        (T.VIAGEM_CONCLUIDA, 1),
        (T.VIAGEM_INICIADA, 2),
        (T.VIAGEM_CONCLUIDA, 2),
    ]


def test_avancar_processa_somente_ate_o_instante():
    simulacao = criar_simulacao()
    simulacao.iniciar()
    primeira_entrega = min(p.saida_em for p in simulacao.plano.paradas)

    antes = simulacao.avancar_ate(primeira_entrega - timedelta(seconds=1))

    assert antes == []
    assert simulacao.agora == primeira_entrega - timedelta(seconds=1)

    eventos = simulacao.avancar(1)

    assert T.PEDIDO_ENTREGUE in tipos(eventos)
    assert all(e.instante <= simulacao.agora for e in eventos)


def test_avancar_sem_iniciar_inclui_os_eventos_do_inicio():
    simulacao = criar_simulacao()

    eventos = simulacao.avancar(0)

    assert eventos[0].tipo == T.SIMULACAO_INICIADA


def test_relogio_para_na_conclusao():
    simulacao = criar_simulacao()

    eventos = simulacao.avancar(600)
    conclusao = eventos[-1]

    assert conclusao.tipo == T.SIMULACAO_CONCLUIDA
    assert conclusao.instante < INICIO + timedelta(minutes=600)
    assert simulacao.agora == conclusao.instante

    assert simulacao.avancar(120) == []
    assert simulacao.agora == conclusao.instante


def test_relogio_avanca_sem_eventos_durante_a_simulacao():
    simulacao = criar_simulacao()
    simulacao.iniciar()

    eventos = simulacao.avancar(1)

    assert eventos == []
    assert simulacao.agora == INICIO + timedelta(minutes=1)


@pytest.mark.parametrize("velocidade", [5, 15, 30, 60])
def test_velocidade_selecionada_converte_segundos_em_hora_simulada(
    monkeypatch, velocidade
):
    simulacao = criar_simulacao()
    simulacao.iniciar()
    alvos = []

    def capturar_alvo(alvo):
        alvos.append(alvo)
        simulacao._relogio.avancar_para(alvo)
        return []

    monkeypatch.setattr(
        simulacao,
        "_processar_ate",
        capturar_alvo,
    )

    simulacao.avancar_tempo_real(velocidade, velocidade)
    assert alvos[-1] == INICIO + timedelta(hours=1)


@pytest.mark.parametrize("velocidade", [5, 15, 30, 60])
def test_pausa_congela_o_relogio_e_retomada_preserva_a_velocidade(
    monkeypatch, velocidade
):
    simulacao = criar_simulacao()
    monkeypatch.setattr(
        simulacao,
        "_processar_ate",
        lambda instante: simulacao._relogio.avancar_para(instante) or [],
    )
    ativa = SimulacaoAtiva(
        simulacao=simulacao,
        auditoria=AuditoriaSimulacao(999),
        cenario_id=1,
        inicio=INICIO,
        provedor="simulado",
        estrategia="insercao_mais_barata",
        estado_execucao=EstadoExecucao.EXECUTANDO,
        segundos_reais_por_hora_simulada=velocidade,
    )

    class RelogioControlado:
        agora = 100.0

        def __call__(self):
            return self.agora

    relogio = RelogioControlado()
    ativa.relogio_monotonic = relogio
    ativa.marca_relogio_monotonic = relogio.agora
    simulacao.iniciar()

    relogio.agora += velocidade / 2
    sincronizar_relogio(ativa)
    meio = simulacao.agora

    ativa.estado_execucao = EstadoExecucao.PAUSADA
    relogio.agora += velocidade * 3
    sincronizar_relogio(ativa)
    assert simulacao.agora == meio

    ativa.marca_relogio_monotonic = relogio.agora
    ativa.estado_execucao = EstadoExecucao.EXECUTANDO
    relogio.agora += velocidade / 2
    sincronizar_relogio(ativa)

    assert ativa.segundos_reais_por_hora_simulada == velocidade
    assert simulacao.agora == INICIO + timedelta(hours=1)


@pytest.mark.parametrize("velocidade", [5, 15, 30, 60])
def test_evento_de_entrega_ocorre_no_instante_planejado(velocidade):
    simulacao = criar_simulacao()
    simulacao.iniciar()
    parada = min(
        simulacao.plano.paradas,
        key=lambda item: item.saida_em,
    )
    segundos_reais = (
        parada.saida_em - simulacao.agora
    ).total_seconds() / 3600 * velocidade

    eventos = simulacao.avancar_tempo_real(
        segundos_reais + 0.00001, velocidade
    )

    entrega = next(
        evento
        for evento in eventos
        if evento.tipo == T.PEDIDO_ENTREGUE
        and evento.pedido_codigo == parada.pedido.codigo
    )
    assert entrega.instante == parada.saida_em
    assert simulacao.status_do_pedido(parada.pedido.codigo) == S.ENTREGUE


def test_avanco_acelerado_processa_eventos_simultaneos_sem_perdas():
    simulacao = criar_simulacao(
        PEDIDOS[:2],
        entregadores=[Entregador("CAM-01", max_paradas_por_viagem=1)],
    )
    referencia = criar_simulacao(
        PEDIDOS[:2],
        entregadores=[Entregador("CAM-01", max_paradas_por_viagem=1)],
    )
    simulacao.iniciar()
    referencia.executar_ate_o_fim()
    fim = simulacao.plano.termino_em
    velocidade = 15
    segundos_reais = (fim - simulacao.agora).total_seconds() / 3600 * velocidade

    simulacao.avancar_tempo_real(segundos_reais + velocidade, velocidade)

    assert simulacao.concluida
    assert simulacao.historico == referencia.historico


def test_relogio_nao_volta():
    simulacao = criar_simulacao()
    simulacao.avancar(30)

    with pytest.raises(ValueError):
        simulacao.avancar_ate(INICIO)

    with pytest.raises(ValueError):
        simulacao.avancar(-1)

    relogio = RelogioSimulado(INICIO)
    with pytest.raises(ValueError):
        relogio.avancar_para(INICIO - timedelta(minutes=1))


def test_observadores_recebem_todos_os_eventos():
    recebidos = []
    simulacao = criar_simulacao(observadores=[recebidos.append])

    simulacao.executar_ate_o_fim()

    assert recebidos == simulacao.historico


# Expediente


def test_viagem_que_sairia_depois_das_17h_e_cancelada():
    entregador = Entregador("CAM-01", max_paradas_por_viagem=1)
    inicio = INICIO.replace(hour=16, minute=30)
    simulacao = criar_simulacao(
        PEDIDOS, inicio=inicio, entregadores=[entregador]
    )

    simulacao.executar_ate_o_fim()
    historico = simulacao.historico
    iniciadas = [e for e in historico if e.tipo == T.VIAGEM_INICIADA]
    canceladas = [e for e in historico if e.tipo == T.VIAGEM_CANCELADA]

    assert iniciadas and canceladas
    assert all(e.instante <= simulacao.fim_expediente for e in iniciadas)
    assert all(e.instante == simulacao.fim_expediente for e in canceladas)

    devolvidos = {
        e.pedido_codigo
        for e in historico
        if e.tipo == T.PEDIDO_DEVOLVIDO_A_FILA
    }
    status = simulacao.status_dos_pedidos()

    assert devolvidos
    assert all(status[c] == S.NA_FILA for c in devolvidos)
    assert all(
        status[p.codigo] == S.ENTREGUE
        for p in PEDIDOS
        if p.codigo not in devolvidos
    )


def test_viagem_iniciada_ate_17h_pode_terminar_depois():
    inicio = INICIO.replace(hour=16, minute=55)
    simulacao = criar_simulacao([criar_pedido("P4", ITAPUA)], inicio=inicio)

    simulacao.executar_ate_o_fim()

    assert simulacao.status_do_pedido("P4") == S.ENTREGUE
    assert simulacao.plano.termino_em > simulacao.fim_expediente


@pytest.mark.parametrize(
    "inicio",
    [
        datetime(2026, 10, 30, 8, 59, tzinfo=FUSO),
        datetime(2026, 10, 30, 17, 0, tzinfo=FUSO),
        datetime(2026, 10, 31, 10, 0, tzinfo=FUSO),  # sabado
        datetime(2026, 10, 30, 10, 0),  # sem fuso
    ],
)
def test_inicio_fora_do_expediente_e_rejeitado(inicio):
    with pytest.raises(ValueError):
        criar_simulacao(inicio=inicio)


def test_inicio_em_outro_fuso_usa_o_horario_de_salvador():
    # 12:00 UTC equivale a 09:00 em Salvador.
    inicio = datetime(2026, 10, 30, 12, 0, tzinfo=ZoneInfo("UTC"))

    simulacao = criar_simulacao(inicio=inicio)

    assert simulacao.fim_expediente == INICIO.replace(hour=17)


# Casos especiais


def test_pedido_com_criacao_posterior_e_incluido_no_snapshot_do_plano():
    tardio = criar_pedido(
        "TARDIO", BARRA, criado_em=INICIO + timedelta(hours=1)
    )
    simulacao = criar_simulacao([*PEDIDOS, tardio])

    simulacao.executar_ate_o_fim()
    eventos = [e for e in simulacao.historico if e.pedido_codigo == "TARDIO"]

    assert tipos(eventos) == [
        T.PEDIDO_NA_FILA,
        T.PEDIDO_ATRIBUIDO,
        T.PEDIDO_EM_ROTA,
        T.PEDIDO_ENTREGUE,
    ]
    assert eventos[0].instante == INICIO
    assert simulacao.status_do_pedido("TARDIO") == S.ENTREGUE
    assert tardio.criado_em == INICIO + timedelta(hours=1)


@pytest.mark.parametrize(
    "criado_em",
    [
        INICIO.replace(hour=17, minute=1),
        INICIO + timedelta(days=10),
    ],
)
def test_pedido_com_data_historica_futura_nao_some_do_snapshot(criado_em):
    outro_dia = criar_pedido(
        "OUTRO-DIA",
        BARRA,
        criado_em=criado_em,
        prazo=criado_em + timedelta(days=3),
    )
    simulacao = criar_simulacao([*PEDIDOS, outro_dia])
    simulacao.iniciar()

    assert len(simulacao.pedidos) == len(PEDIDOS) + 1
    assert simulacao.status_do_pedido("OUTRO-DIA") in {
        S.ATRIBUIDO,
        S.EM_ROTA,
    }
    assert simulacao.plano.rota_do_pedido("OUTRO-DIA")
    assert outro_dia.criado_em == criado_em


def test_pedido_nao_atribuido_fica_na_fila():
    pesado = criar_pedido("PESADO", BARRA, peso_kg=900)
    simulacao = criar_simulacao([*PEDIDOS, pesado])

    simulacao.executar_ate_o_fim()
    eventos = [e for e in simulacao.historico if e.pedido_codigo == "PESADO"]

    assert tipos(eventos) == [T.PEDIDO_NA_FILA, T.PEDIDO_NAO_ATRIBUIDO]
    assert simulacao.status_do_pedido("PESADO") == S.NA_FILA


def test_entrega_atrasada_registra_o_atraso():
    atrasado = criar_pedido(
        "ATRASADO", ITAPUA, prazo=INICIO + timedelta(minutes=10)
    )
    simulacao = criar_simulacao([PEDIDOS[0], atrasado])

    simulacao.executar_ate_o_fim()
    entregas = {
        e.pedido_codigo: e
        for e in simulacao.historico
        if e.tipo == T.PEDIDO_ENTREGUE
    }
    parada = next(
        p for p in simulacao.plano.paradas if p.pedido.codigo == "ATRASADO"
    )

    assert entregas["ATRASADO"].atraso_min == pytest.approx(-parada.folga_min)
    assert "atrasada" in entregas["ATRASADO"].detalhe
    assert entregas["P1"].atraso_min == 0
    assert entregas["P1"].detalhe == "no prazo"


def test_pedidos_duplicados_sao_rejeitados():
    with pytest.raises(ValueError):
        criar_simulacao([PEDIDOS[0], PEDIDOS[0]])


def test_status_de_pedido_desconhecido():
    simulacao = criar_simulacao()

    with pytest.raises(KeyError):
        simulacao.status_do_pedido("NAO-EXISTE")


class ObservadorInstavel:
    """Falha uma vez ao receber o evento de uma sequencia."""

    def __init__(self, falhar_na_sequencia: int) -> None:
        self.falhar_na_sequencia = falhar_na_sequencia
        self.recebidos = []

    def __call__(self, evento) -> None:
        if evento.sequencia == self.falhar_na_sequencia:
            self.falhar_na_sequencia = None
            raise RuntimeError("falha ao gravar")

        self.recebidos.append(evento)


@pytest.mark.parametrize("falha", [1, 3, 20])
def test_falha_do_observador_nao_perde_eventos(falha):
    observador = ObservadorInstavel(falha)
    simulacao = criar_simulacao(observadores=[observador])
    referencia = criar_simulacao()
    referencia.executar_ate_o_fim()

    with pytest.raises(RuntimeError):
        simulacao.executar_ate_o_fim()

    # O evento que falhou nao foi aplicado.
    assert len(simulacao.historico) == falha - 1

    simulacao.executar_ate_o_fim()

    assert observador.recebidos == simulacao.historico
    assert simulacao.historico == referencia.historico


def test_falha_no_evento_final_e_repetida():
    referencia = criar_simulacao()
    referencia.executar_ate_o_fim()
    ultimo = len(referencia.historico)
    observador = ObservadorInstavel(ultimo)
    simulacao = criar_simulacao(observadores=[observador])

    with pytest.raises(RuntimeError):
        simulacao.executar_ate_o_fim()

    assert not simulacao.concluida
    assert simulacao.proximo_instante == simulacao.agora

    eventos = simulacao.proxima_etapa()

    assert tipos(eventos) == [T.SIMULACAO_CONCLUIDA]
    assert simulacao.concluida
    assert observador.recebidos == simulacao.historico
