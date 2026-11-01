from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.distribution import (
    CentroDistribuicao,
    DistribuicaoInsercaoMaisBarata,
    DistribuicaoOrdemDaFila,
    DistribuidorPedidos,
    MapaDeslocamentos,
)
from app.domain.models import Bairro, CategoriaProduto, Entregador, Pedido
from app.domain.priority_queue import FilaPrioridadeHeap
from app.domain.routing import Coordenada, ElementoMatriz
from app.infrastructure.distribution_config import (
    CENTRO_PADRAO,
    criar_entregadores_padrao,
    obter_centro_distribuicao,
)
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


FUSO = ZoneInfo("America/Bahia")
PARTIDA = datetime(2026, 10, 30, 9, 0, tzinfo=FUSO)
CRIADO_EM = datetime(2026, 10, 29, 9, 0, tzinfo=FUSO)

CENTRO = CentroDistribuicao("Comercio", Coordenada(-12.971, -38.501))

BARRA = Bairro("Barra", -13.006, -38.528)
BROTAS = Bairro("Brotas", -12.986, -38.482)
PITUBA = Bairro("Pituba", -12.999, -38.460)
RIO_VERMELHO = Bairro("Rio Vermelho", -13.010, -38.490)
ITAPUA = Bairro("Itapua", -12.940, -38.358)
BOCA_DO_RIO = Bairro("Boca do Rio", -12.976, -38.429)


def criar_pedido(
    codigo: str,
    bairro: Bairro,
    prazo: datetime | None = None,
    peso_kg: float = 1.0,
    volume_l: float = 1.0,
    tempo_servico_min: int = 5,
) -> Pedido:
    return Pedido(
        codigo=codigo,
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=1,
        criado_em=CRIADO_EM,
        prazo_entrega_em=prazo or PARTIDA + timedelta(days=3),
        peso_kg=peso_kg,
        volume_l=volume_l,
        tempo_servico_min=tempo_servico_min,
    )


def criar_distribuidor(entregadores=None, estrategia=None, servico=None):
    return DistribuidorPedidos(
        servico or ServicoRoteamentoSimulado(fator_transito=1.0),
        CENTRO,
        entregadores or criar_entregadores_padrao(2),
        estrategia,
    )


PEDIDOS = [
    criar_pedido("P1", BARRA),
    criar_pedido("P2", PITUBA),
    criar_pedido("P3", BROTAS),
    criar_pedido("P4", ITAPUA),
    criar_pedido("P5", RIO_VERMELHO),
    criar_pedido("P6", BOCA_DO_RIO),
]


class ServicoContador(ServicoRoteamentoSimulado):
    """Registra as rotas pedidas ao servico."""

    def __init__(self) -> None:
        super().__init__(fator_transito=1.0)
        self.matrizes = []
        self.rotas = []

    def calcular_matriz(self, origens, destinos, partida_em=None):
        self.matrizes.append(list(origens))
        return super().calcular_matriz(origens, destinos, partida_em)

    def calcular_rota(self, origem, destino, paradas=(), partida_em=None):
        self.rotas.append((origem, list(paradas), destino, partida_em))
        return super().calcular_rota(origem, destino, paradas, partida_em)


# Modelos


def test_entregador_tem_capacidade_padrao():
    entregador = Entregador(codigo="CAM-01")

    assert entregador.max_paradas_por_viagem == 6
    assert entregador.capacidade_peso_kg == 500
    assert entregador.capacidade_volume_l == 3000


@pytest.mark.parametrize(
    "dados",
    [
        {"max_paradas_por_viagem": 0},
        {"max_paradas_por_viagem": 2.5},
        {"capacidade_peso_kg": 0},
        {"capacidade_volume_l": -1},
    ],
)
def test_entregador_com_capacidade_invalida(dados):
    with pytest.raises(ValueError):
        Entregador(codigo="CAM-01", **dados)


def test_centro_sem_nome_e_rejeitado():
    with pytest.raises(ValueError):
        CentroDistribuicao(" ", Coordenada(-12.9, -38.5))


# Distribuicao


@pytest.mark.parametrize(
    "estrategia",
    [DistribuicaoInsercaoMaisBarata, DistribuicaoOrdemDaFila],
)
def test_todos_os_pedidos_sao_atribuidos_uma_vez(estrategia):
    plano = criar_distribuidor(estrategia=estrategia()).planejar(
        PEDIDOS, PARTIDA
    )

    codigos = [p.pedido.codigo for p in plano.paradas]

    assert sorted(codigos) == sorted(p.codigo for p in PEDIDOS)
    assert plano.nao_atribuidos == []


def test_insercao_reduz_distancia_em_relacao_a_ordem_da_fila():
    insercao = criar_distribuidor().planejar(PEDIDOS, PARTIDA)
    fila = criar_distribuidor(
        estrategia=DistribuicaoOrdemDaFila()
    ).planejar(PEDIDOS, PARTIDA)

    assert insercao.distancia_total_m < fila.distancia_total_m


def test_limite_de_paradas_cria_nova_viagem():
    entregador = Entregador(codigo="CAM-01", max_paradas_por_viagem=2)

    plano = criar_distribuidor([entregador]).planejar(PEDIDOS[:5], PARTIDA)
    viagens = plano.rotas[0].viagens

    assert len(viagens) == 3
    assert all(len(v.paradas) <= 2 for v in viagens)
    assert viagens[1].partida_em == viagens[0].retorno_em


def test_limite_de_peso_e_volume_por_viagem():
    entregador = Entregador(
        codigo="CAM-01", capacidade_peso_kg=10, capacidade_volume_l=10
    )
    pedidos = [
        criar_pedido("P1", BARRA, peso_kg=6),
        criar_pedido("P2", PITUBA, peso_kg=6),
        criar_pedido("P3", BROTAS, volume_l=8),
    ]

    plano = criar_distribuidor([entregador]).planejar(pedidos, PARTIDA)

    for viagem in plano.rotas[0].viagens:
        assert viagem.peso_kg <= 10
        assert viagem.volume_l <= 10


def test_pedido_maior_que_todos_os_caminhoes_fica_sem_atribuicao():
    pedidos = [
        criar_pedido("P1", BARRA),
        criar_pedido("P2", PITUBA, peso_kg=900),
    ]

    plano = criar_distribuidor().planejar(pedidos, PARTIDA)

    assert [p.codigo for p in plano.nao_atribuidos] == ["P2"]
    assert [p.pedido.codigo for p in plano.paradas] == ["P1"]


def test_pedido_vai_para_o_caminhao_que_comporta():
    pequeno = Entregador(codigo="PEQ", capacidade_peso_kg=5)
    grande = Entregador(codigo="GRD", capacidade_peso_kg=100)
    pedido = criar_pedido("P1", BARRA, peso_kg=50)

    plano = criar_distribuidor([pequeno, grande]).planejar([pedido], PARTIDA)
    entregador, _ = plano.rota_do_pedido("P1")

    assert entregador.codigo == "GRD"


def test_prazo_apertado_e_atendido_no_prazo():
    # Itapua fica longe; com prazo curto ele precisa chegar a tempo.
    urgente = criar_pedido(
        "URG", ITAPUA, prazo=PARTIDA + timedelta(minutes=50)
    )
    pedidos = [*PEDIDOS[:3], urgente]

    plano = criar_distribuidor([Entregador("CAM-01")]).planejar(
        pedidos, PARTIDA
    )

    assert plano.pedidos_atrasados == []

    # Sem considerar o prazo, Itapua ficaria para o fim da rota.
    sem_prazo = criar_distribuidor([Entregador("CAM-01")]).planejar(
        [*PEDIDOS[:3], criar_pedido("URG", ITAPUA)], PARTIDA
    )
    assert sem_prazo.paradas[-1].pedido.codigo == "URG"


def test_pedido_mais_prioritario_e_entregue_antes_no_mesmo_ponto():
    pedidos = [
        criar_pedido("ALTA", BARRA),
        criar_pedido("BAIXA", BARRA),
    ]

    plano = criar_distribuidor([Entregador("CAM-01")]).planejar(
        pedidos, PARTIDA
    )

    assert [p.pedido.codigo for p in plano.paradas] == ["ALTA", "BAIXA"]


def test_horarios_e_distancias_sao_consistentes():
    plano = criar_distribuidor().planejar(PEDIDOS, PARTIDA)

    for rota in plano.rotas:
        for viagem in rota.viagens:
            instantes = [viagem.partida_em]
            for parada in viagem.paradas:
                instantes += [parada.chegada_em, parada.saida_em]
            instantes.append(viagem.retorno_em)

            assert instantes == sorted(instantes)
            assert viagem.distancia_m > 0

    assert plano.distancia_total_m == sum(
        r.distancia_m for r in plano.rotas
    )
    assert plano.termino_em == max(r.termino_em for r in plano.rotas)


def test_um_unico_entregador_funciona():
    plano = criar_distribuidor([Entregador("CAM-01")]).planejar(
        PEDIDOS, PARTIDA
    )

    assert len(plano.rotas) == 1
    assert len(plano.paradas) == len(PEDIDOS)


def test_disponibilidade_atrasa_a_saida_do_entregador():
    disponivel = PARTIDA + timedelta(hours=1)

    plano = criar_distribuidor([Entregador("CAM-01")]).planejar(
        PEDIDOS,
        PARTIDA,
        disponibilidade={"CAM-01": disponivel},
    )

    assert plano.rotas[0].viagens[0].partida_em == disponivel


def test_entregador_disponivel_depois_recebe_menos_pedidos():
    plano = criar_distribuidor().planejar(
        PEDIDOS,
        PARTIDA,
        disponibilidade={"CAM-02": PARTIDA + timedelta(hours=3)},
    )

    cargas = [len(rota.pedidos) for rota in plano.rotas]

    assert cargas[0] > cargas[1]


class ServicoSemRotaParaItapua(ServicoRoteamentoSimulado):
    """Simula um ponto sem rota, como um local que exige balsa."""

    def __init__(self) -> None:
        super().__init__(fator_transito=1.0)

    def calcular_matriz(self, origens, destinos, partida_em=None):
        matriz = super().calcular_matriz(origens, destinos, partida_em)
        itapua = Coordenada.do_bairro(ITAPUA)

        for (i, j), elemento in list(matriz.elementos.items()):
            if itapua in (origens[i], destinos[j]) and origens[i] != destinos[j]:
                matriz.elementos[(i, j)] = ElementoMatriz(i, j, False)

        return matriz


def test_pedido_sem_rota_fica_sem_atribuicao():
    plano = criar_distribuidor(
        servico=ServicoSemRotaParaItapua()
    ).planejar(PEDIDOS, PARTIDA)

    assert [p.codigo for p in plano.nao_atribuidos] == ["P4"]
    assert len(plano.paradas) == len(PEDIDOS) - 1


def test_sem_pedidos_gera_plano_vazio_sem_consultar_mapa():
    servico = ServicoContador()

    plano = criar_distribuidor(servico=servico).planejar([], PARTIDA)

    assert plano.paradas == []
    assert plano.termino_em is None
    assert servico.matrizes == []


@pytest.mark.parametrize(
    "entregadores",
    [[], [Entregador("CAM-01"), Entregador("CAM-01")]],
)
def test_entregadores_invalidos(entregadores):
    with pytest.raises(ValueError):
        DistribuicaoInsercaoMaisBarata().distribuir(
            PEDIDOS, entregadores, CENTRO, None, PARTIDA
        )


def test_pedidos_duplicados_sao_rejeitados():
    with pytest.raises(ValueError):
        criar_distribuidor().planejar([PEDIDOS[0], PEDIDOS[0]], PARTIDA)


def test_partida_obrigatoria_com_fuso():
    with pytest.raises(ValueError):
        criar_distribuidor().planejar(PEDIDOS, None)

    with pytest.raises(ValueError):
        criar_distribuidor().planejar(PEDIDOS, datetime(2026, 10, 30, 9))


def test_rota_do_pedido_inexistente():
    plano = criar_distribuidor().planejar(PEDIDOS, PARTIDA)

    with pytest.raises(KeyError):
        plano.rota_do_pedido("NAO-EXISTE")


# Integracao com a F03 e a F04


def test_mapa_usa_um_ponto_por_coordenada():
    servico = ServicoContador()
    pedidos = [criar_pedido("P1", BARRA), criar_pedido("P2", BARRA)]

    mapa = MapaDeslocamentos.calcular(servico, CENTRO, pedidos, PARTIDA)

    assert len(servico.matrizes[0]) == 2
    assert mapa.duracao_min(pedidos[0], pedidos[1]) == 0


def test_planejar_da_fila_retira_todos_os_pedidos():
    fila = FilaPrioridadeHeap()
    for pedido in PEDIDOS:
        fila.adicionar_pedido(pedido, agora=PARTIDA)

    plano = criar_distribuidor().planejar_da_fila(fila, PARTIDA)

    assert fila.esta_vazia()
    assert len(plano.paradas) == len(PEDIDOS)


def test_montar_rotas_pede_geometria_de_cada_viagem():
    servico = ServicoContador()
    distribuidor = criar_distribuidor(servico=servico)
    pedidos = [
        criar_pedido("P1", BARRA),
        criar_pedido("P2", BARRA),
        criar_pedido("P3", PITUBA),
    ]
    plano = distribuidor.planejar(pedidos, PARTIDA)

    distribuidor.montar_rotas(plano)

    viagens = [v for r in plano.rotas for v in r.viagens]
    assert len(servico.rotas) == len(viagens)

    for viagem, (origem, paradas, destino, partida) in zip(
        viagens, servico.rotas
    ):
        assert origem == destino == CENTRO.coordenada
        assert partida == viagem.partida_em
        assert viagem.rota is not None
        # Pedidos seguidos no mesmo bairro viram uma unica parada.
        assert all(a != b for a, b in zip(paradas, paradas[1:]))


# Configuracao


def test_centro_padrao(monkeypatch):
    monkeypatch.delenv("CENTRO_DISTRIBUICAO_LATITUDE", raising=False)
    monkeypatch.delenv("CENTRO_DISTRIBUICAO_LONGITUDE", raising=False)

    assert obter_centro_distribuicao() == CENTRO_PADRAO


def test_centro_lido_do_ambiente(monkeypatch):
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_NOME", "Porto Seco")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LATITUDE", "-12.905")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LONGITUDE", "-38.462")

    centro = obter_centro_distribuicao()

    assert centro.nome == "Porto Seco"
    assert centro.coordenada == Coordenada(-12.905, -38.462)


def test_centro_com_coordenada_incompleta(monkeypatch):
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LATITUDE", "-12.905")
    monkeypatch.delenv("CENTRO_DISTRIBUICAO_LONGITUDE", raising=False)

    with pytest.raises(ValueError):
        obter_centro_distribuicao()


def test_entregadores_padrao(monkeypatch):
    monkeypatch.setenv("QUANTIDADE_ENTREGADORES", "3")

    codigos = [e.codigo for e in criar_entregadores_padrao()]

    assert codigos == ["CAM-01", "CAM-02", "CAM-03"]

    with pytest.raises(ValueError):
        criar_entregadores_padrao(0)
