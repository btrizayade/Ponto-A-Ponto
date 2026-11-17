from dataclasses import replace
from datetime import date, datetime

import pytest

from app.domain.alinhamento_temporal_pedidos import (
    MANIFESTO_TEMPORAL_PEDIDOS,
    VERSAO_REGRA_TEMPORAL_PEDIDOS,
    alinhar_pedidos_do_cenario,
    validar_data_criacao_manual,
)
from app.domain.configuracao_temporal import (
    CONFIGURACOES_TEMPORAIS_CENARIOS,
    ConfiguracaoTemporalCenario,
    VERSAO_CONFIGURACAO_TEMPORAL_CENARIO,
)
from app.domain.models import (
    Bairro,
    CategoriaProduto,
    OrigemPedido,
    Pedido,
)
from app.domain.sla import FUSO_HORARIO, calcular_prazo_entrega
from app.infrastructure import database
from app.infrastructure.auditoria_repository import (
    obter_parametros_experimentais,
)
from app.infrastructure.pedido_repository import listar_pedidos_por_cenario
from app.infrastructure.seed import inicializar_todos_cenarios
from app.infrastructure.simulacao_factory import criar_simulacao_auditada
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


@pytest.fixture
def cenarios_em_banco_temporario(tmp_path, monkeypatch):
    diretorio = tmp_path / "temporalidade"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    return {c.codigo: c for c in inicializar_todos_cenarios()}


def pedido(codigo, origem, criado_em, *, ativo=True):
    return Pedido(
        id=1,
        codigo=codigo,
        bairro=Bairro("Comercio", -12.963, -38.507, id=1),
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
        criado_em=criado_em,
        prazo_entrega_em=calcular_prazo_entrega(criado_em, 1),
        peso_kg=1.2,
        volume_l=2.0,
        tempo_servico_min=7,
        origem=origem,
        ativo=ativo,
    )


def test_manifesto_tem_49_codigos_unicos_e_datas_na_janela():
    assert sum(map(len, MANIFESTO_TEMPORAL_PEDIDOS.values())) == 49
    assert {codigo: len(m) for codigo, m in MANIFESTO_TEMPORAL_PEDIDOS.items()} == {
        "NORMAL": 10,
        "EQUIDADE": 15,
        "ALTA_DEMANDA": 24,
    }
    codigos = {
        cenario: set(manifesto)
        for cenario, manifesto in MANIFESTO_TEMPORAL_PEDIDOS.items()
    }
    assert codigos["NORMAL"] == {
        f"PED-{numero:03d}" for numero in range(1, 11)
    }
    assert codigos["EQUIDADE"] == {
        f"EQ-{numero:03d}" for numero in range(1, 16)
    }
    assert codigos["ALTA_DEMANDA"] == {
        f"ALTA-{numero:03d}" for numero in range(1, 25)
    }
    assert all(
        instante.weekday() < 5
        and instante.hour in (9, 13)
        and instante.minute == 0
        and configuracao.data_inicial_janela
        <= instante.date()
        <= configuracao.data_final_janela
        and instante <= configuracao.inicio_simulacao
        for codigo, manifesto in MANIFESTO_TEMPORAL_PEDIDOS.items()
        for instante in manifesto.values()
        for configuracao in [CONFIGURACOES_TEMPORAIS_CENARIOS[codigo]]
    )


@pytest.mark.parametrize(
    ("codigo", "quantidade"),
    [("NORMAL", 10), ("EQUIDADE", 15), ("ALTA_DEMANDA", 24)],
)
def test_fabrica_usa_copias_efetivas_e_snapshot_preserva_historico(
    cenarios_em_banco_temporario, codigo, quantidade
):
    cenario = cenarios_em_banco_temporario[codigo]
    historicos = listar_pedidos_por_cenario(cenario.id)
    historico_por_codigo = {p.codigo: p for p in historicos}
    fotografia_banco = {
        p.codigo: (p.criado_em, p.prazo_entrega_em) for p in historicos
    }
    inicio = CONFIGURACOES_TEMPORAIS_CENARIOS[codigo].inicio_simulacao

    simulacao, auditoria = criar_simulacao_auditada(
        cenario.id,
        inicio,
        servico=ServicoRoteamentoSimulado(fator_transito=1.0),
    )

    assert len(simulacao.pedidos) == quantidade
    assert all(p.criado_em <= inicio for p in simulacao.pedidos)
    assert all(
        p.prazo_entrega_em == calcular_prazo_entrega(
            p.criado_em, p.sla_dias_uteis
        )
        for p in simulacao.pedidos
    )
    assert {
        p.codigo: (p.criado_em, p.prazo_entrega_em)
        for p in listar_pedidos_por_cenario(cenario.id)
    } == fotografia_banco

    resultado = obter_parametros_experimentais(auditoria.simulacao_id)
    snapshot = resultado["snapshot_pedidos"]["dados"]
    assert snapshot["versao"] == 2
    assert resultado["parametros"]["temporalidade"][
        "versao_configuracao"
    ] == VERSAO_CONFIGURACAO_TEMPORAL_CENARIO
    assert resultado["parametros"]["temporalidade"][
        "versao_regra_pedidos"
    ] == VERSAO_REGRA_TEMPORAL_PEDIDOS
    assert snapshot["temporalidade"]["fuso_horario"] == "America/Bahia"
    assert snapshot["temporalidade"]["inicio_simulacao_utilizado"] == inicio.isoformat()
    por_codigo = {p["codigo"]: p for p in snapshot["pedidos"]}
    por_codigo_motor = {p.codigo: p for p in simulacao.pedidos}
    assert set(por_codigo) == set(por_codigo_motor)
    for codigo_pedido, item in por_codigo.items():
        original = historico_por_codigo[codigo_pedido]
        efetivo = por_codigo_motor[codigo_pedido]
        assert item["criado_em"] == efetivo.criado_em.isoformat()
        assert item["prazo_entrega_em"] == efetivo.prazo_entrega_em.isoformat()
        assert item["datas_efetivas"]["criado_em"] == item["criado_em"]
        assert item["datas_efetivas"]["prazo_entrega_em"] == item[
            "prazo_entrega_em"
        ]
        assert item["datas_historicas"]["criado_em"] == original.criado_em.isoformat()
        assert item["datas_historicas"]["prazo_entrega_em"] == original.prazo_entrega_em.isoformat()

    simulacao.iniciar()
    pedidos_por_codigo = {p.codigo: p for p in simulacao.pedidos}
    for rota in simulacao.plano.rotas:
        for viagem in rota.viagens:
            for parada in viagem.paradas:
                assert parada.chegada_em >= pedidos_por_codigo[
                    parada.pedido.codigo
                ].criado_em


def test_transformacao_independe_da_ordem_e_nao_muta_pedidos_originais():
    inicio = CONFIGURACOES_TEMPORAIS_CENARIOS["NORMAL"].inicio_simulacao
    originals = [
        pedido(
            codigo,
            OrigemPedido.REFERENCIA,
            datetime(2026, 10, 26, 9, tzinfo=FUSO_HORARIO),
        )
        for codigo in MANIFESTO_TEMPORAL_PEDIDOS["NORMAL"]
    ]
    datas_antes = {p.codigo: (p.criado_em, p.prazo_entrega_em) for p in originals}
    _, primeira = alinhar_pedidos_do_cenario("NORMAL", originals, inicio)
    _, segunda = alinhar_pedidos_do_cenario(
        "NORMAL", list(reversed(originals)), inicio
    )

    datas_primeira = {p.codigo: (p.criado_em, p.prazo_entrega_em) for p in primeira}
    datas_segunda = {p.codigo: (p.criado_em, p.prazo_entrega_em) for p in segunda}
    assert datas_primeira == datas_segunda
    assert {p.codigo: (p.criado_em, p.prazo_entrega_em) for p in originals} == datas_antes


def test_manual_e_inativo_nao_sao_temporalizados():
    inicio = CONFIGURACOES_TEMPORAIS_CENARIOS["NORMAL"].inicio_simulacao
    manual = pedido(
        "MANUAL-01",
        OrigemPedido.MANUAL,
        datetime(2026, 10, 6, 9, tzinfo=FUSO_HORARIO),
    )
    inativo = pedido(
        "EQ-016",
        OrigemPedido.REFERENCIA,
        datetime(2026, 10, 30, 9, tzinfo=FUSO_HORARIO),
        ativo=False,
    )
    historicos, efetivos = alinhar_pedidos_do_cenario(
        "NORMAL", [manual, inativo], inicio
    )

    assert [p.codigo for p in historicos] == ["MANUAL-01"]
    assert len(efetivos) == 1
    assert efetivos[0] == manual
    assert efetivos[0] is not manual
    assert inativo.criado_em == datetime(2026, 10, 30, 9, tzinfo=FUSO_HORARIO)


def test_pedido_manual_futuro_nao_entra_na_massa_da_simulacao():
    inicio = CONFIGURACOES_TEMPORAIS_CENARIOS["NORMAL"].inicio_simulacao
    futuro = pedido(
        "MANUAL-FUTURO",
        OrigemPedido.MANUAL,
        datetime(2026, 10, 8, 9, tzinfo=FUSO_HORARIO),
    )
    historicos, efetivos = alinhar_pedidos_do_cenario(
        "NORMAL", [futuro], inicio
    )
    assert historicos == []
    assert efetivos == []


def test_pedido_de_referencia_ativo_sem_manifesto_falha_claramente():
    inicio = CONFIGURACOES_TEMPORAIS_CENARIOS["NORMAL"].inicio_simulacao
    desconhecido = pedido(
        "REF-SEM-MANIFESTO",
        OrigemPedido.REFERENCIA,
        datetime(2026, 10, 6, 9, tzinfo=FUSO_HORARIO),
    )
    with pytest.raises(ValueError, match="sem data no manifesto"):
        alinhar_pedidos_do_cenario("NORMAL", [desconhecido], inicio)


def test_snapshot_rejeita_divergencia_entre_dados_historicos_e_efetivos():
    from app.domain.models import Cenario
    from app.infrastructure.auditoria_experimental import (
        serializar_snapshot_pedidos,
    )

    historico = pedido(
        "PED-001",
        OrigemPedido.REFERENCIA,
        datetime(2026, 10, 26, 9, tzinfo=FUSO_HORARIO),
    )
    efetivo = replace(
        historico,
        criado_em=MANIFESTO_TEMPORAL_PEDIDOS["NORMAL"]["PED-001"],
        prazo_entrega_em=calcular_prazo_entrega(
            MANIFESTO_TEMPORAL_PEDIDOS["NORMAL"]["PED-001"], 1
        ),
    )
    efetivo_divergente = replace(efetivo, codigo="PED-002")

    with pytest.raises(ValueError, match="não correspondem"):
        serializar_snapshot_pedidos(
            Cenario("NORMAL", "Operação normal", id=1),
            [efetivo_divergente],
            CONFIGURACOES_TEMPORAIS_CENARIOS["NORMAL"].inicio_simulacao,
            pedidos_historicos=[historico],
        )


def test_validacao_da_data_manual_fixa_horario_e_fuso():
    configuracao = ConfiguracaoTemporalCenario(
        codigo_cenario="NORMAL",
        data_inicial_janela=date(2026, 10, 5),
        data_final_janela=date(2026, 10, 10),
        inicio_simulacao=datetime(2026, 10, 7, 9, tzinfo=FUSO_HORARIO),
        fuso_horario="America/Bahia",
    )
    criado = validar_data_criacao_manual(configuracao, date(2026, 10, 6))
    assert criado == datetime(2026, 10, 6, 9, tzinfo=FUSO_HORARIO)
    assert criado.tzinfo is FUSO_HORARIO

    with pytest.raises(ValueError, match="janela"):
        validar_data_criacao_manual(configuracao, date(2026, 10, 4))
    with pytest.raises(ValueError, match="dia útil"):
        validar_data_criacao_manual(configuracao, date(2026, 10, 10))
    with pytest.raises(ValueError, match="posterior"):
        validar_data_criacao_manual(configuracao, date(2026, 10, 8))
