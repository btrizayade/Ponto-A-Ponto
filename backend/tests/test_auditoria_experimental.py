import json
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.registro import registro
from app.domain.distribution import CentroDistribuicao, DistribuidorPedidos
from app.domain.models import (
    Bairro,
    CategoriaProduto,
    Entregador,
    Pedido,
)
from app.domain.routing import Coordenada
from app.domain.simulation import Simulacao
from app.infrastructure import database
from app.infrastructure.auditoria_experimental import (
    FalhaPersistenciaAuditoriaRoteamento,
    ServicoRoteamentoAuditavel,
)
from app.infrastructure.auditoria_repository import (
    AuditoriaSimulacao,
    obter_parametros_experimentais,
)
from app.infrastructure.cache_roteamento import ServicoRoteamentoComCache
from app.infrastructure.google_routes import ServicoRoteamentoGoogle
from app.infrastructure.seed import inicializar_todos_cenarios
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado
from app.main import app


FUSO = ZoneInfo("America/Bahia")
INICIO = datetime(2026, 10, 30, 10, 0, tzinfo=FUSO)
CENTRO = CentroDistribuicao("Comercio", Coordenada(-12.971, -38.501))
BARRA = Coordenada(-13.006, -38.528)


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    diretorio = tmp_path / "experimentos"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    database.inicializar_banco()


@pytest.fixture
def cliente_com_cenarios(tmp_path, monkeypatch):
    diretorio = tmp_path / "api_experimentos"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    monkeypatch.delenv("PONTO_A_PONTO_GIT_REVISION", raising=False)
    monkeypatch.delenv("PONTO_A_PONTO_BUILD_ID", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("QUANTIDADE_ENTREGADORES", raising=False)
    monkeypatch.delenv("PROVEDOR_MAPAS", raising=False)
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_NOME", "Comercio")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LATITUDE", "-12.971")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LONGITUDE", "-38.501")
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    cenarios = inicializar_todos_cenarios()
    registro.limpar()

    with TestClient(app) as cliente:
        cliente.cenarios_por_codigo = {
            cenario.codigo: cenario for cenario in cenarios
        }
        yield cliente

    registro.limpar()


@pytest.mark.parametrize(
    ("codigo", "quantidade", "estrategia", "modo_transito", "fator"),
    [
        ("NORMAL", 10, "insercao_mais_barata", "horario", None),
        ("EQUIDADE", 15, "equidade_sla", "horario", None),
        ("ALTA_DEMANDA", 24, "insercao_mais_barata", "fixo", 2.0),
    ],
)
def test_api_persiste_parametros_efetivos_e_snapshot_completo(
    cliente_com_cenarios,
    codigo,
    quantidade,
    estrategia,
    modo_transito,
    fator,
):
    cliente = cliente_com_cenarios
    cenario = cliente.cenarios_por_codigo[codigo]
    criada = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario.id,
            "inicio": INICIO.isoformat(),
            "provedor": "simulado",
        },
    )
    assert criada.status_code == 201, criada.json()
    simulacao_id = criada.json()["id"]

    resposta = cliente.get(f"/api/simulacoes/{simulacao_id}/parametros")
    assert resposta.status_code == 200, resposta.json()
    dados = resposta.json()
    assert dados["disponivel"] is True
    assert dados["parametros"]["versao"] == 1
    assert dados["parametros"]["aplicacao"] == {
        "revisao_git": None,
        "build_id": None,
    }
    assert dados["parametros"]["cenario"]["codigo"] == codigo
    assert dados["parametros"]["inicio"]["instante"] == INICIO.isoformat()
    assert dados["parametros"]["inicio"]["fuso_horario"] == "America/Bahia"
    assert dados["parametros"]["roteamento"]["provedor"] == "simulado"
    assert (
        dados["parametros"]["roteamento"]["modelo"]["transito"]["modo"]
        == modo_transito
    )
    assert (
        dados["parametros"]["roteamento"]["modelo"]["transito"]["fator_fixo"]
        == fator
    )
    assert dados["parametros"]["distribuicao"]["estrategia"] == estrategia
    assert len(dados["parametros"]["distribuicao"]["entregadores"]) == 2
    assert dados["parametros"]["distribuicao"]["entregadores"][0] == {
        "codigo": "CAM-01",
        "max_paradas_por_viagem": 6,
        "capacidade_peso_kg": 500.0,
        "capacidade_volume_l": 3000.0,
    }
    assert dados["parametros"]["distribuicao"]["centro"] == {
        "nome": "Comercio",
        "latitude": -12.971,
        "longitude": -38.501,
    }

    snapshot = dados["snapshot_pedidos"]
    assert snapshot["versao"] == 1
    entrada = snapshot["dados"]
    assert entrada["versao"] == 1
    assert entrada["cenario"]["codigo"] == codigo
    assert len(entrada["pedidos"]) == quantidade
    pedido = entrada["pedidos"][0]
    assert {
        "id", "codigo", "bairro", "categoria_produto", "cliente_clube",
        "entrega_rapida", "sla_dias_uteis", "criado_em",
        "prazo_entrega_em", "peso_kg", "volume_l", "tempo_servico_min",
        "status_inicial_motor", "prioridade_inicial", "origem", "ativo",
    } <= set(pedido)
    assert isinstance(pedido["prioridade_inicial"], int)
    assert {"id", "nome", "latitude", "longitude"} <= set(pedido["bairro"])
    assert dados["consultas_roteamento"] == []

    etapa = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert etapa.status_code == 200, etapa.json()
    dados_apos_planejamento = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    ).json()
    consultas_matriz = [
        consulta
        for consulta in dados_apos_planejamento["consultas_roteamento"]
        if consulta["tipo"] == "matriz"
    ]
    assert consultas_matriz
    fatores = {
        elemento["fator_transito"]
        for consulta in consultas_matriz
        for elemento in consulta["resposta"]["dados"]["elementos"]
    }
    fator_esperado = fator or 1.15
    assert fator_esperado in fatores
    assert fatores <= {1.0, fator_esperado}

    # O snapshot não acompanha alterações posteriores dos cadastros ativos.
    with database.conectar() as conexao:
        conexao.execute(
            "UPDATE pedidos SET peso_kg = 999 WHERE id = ?",
            (pedido["id"],),
        )
        conexao.execute(
            "UPDATE bairros SET latitude = -12.5 WHERE id = ?",
            (pedido["bairro"]["id"],),
        )
    dados_apos_edicao = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    ).json()
    assert dados_apos_edicao["snapshot_pedidos"] == snapshot

    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                """
                UPDATE simulacao_pedidos_snapshot
                SET dados_json = '{}'
                WHERE simulacao_id = ?
                """,
                (simulacao_id,),
            )

    # A listagem continua compacta e não carrega o JSON experimental.
    simulacao_listada = next(
        item
        for item in cliente.get("/api/simulacoes").json()
        if item["id"] == simulacao_id
    )
    assert "parametros" not in simulacao_listada
    assert "snapshot_pedidos" not in simulacao_listada


def test_endpoint_parametros_nao_depende_do_registro_em_memoria(
    tmp_path,
    monkeypatch,
):
    diretorio = tmp_path / "reinicio"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("PROVEDOR_MAPAS", raising=False)
    monkeypatch.delenv("QUANTIDADE_ENTREGADORES", raising=False)
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    cenarios = inicializar_todos_cenarios()
    cenario = next(c for c in cenarios if c.codigo == "NORMAL")

    with TestClient(app) as cliente:
        criada = cliente.post(
            "/api/simulacoes",
            json={"cenario_id": cenario.id, "inicio": INICIO.isoformat()},
        )
        assert criada.status_code == 201
        simulacao_id = criada.json()["id"]

    # Recria o lifespan da aplicação e remove o estado operacional em memória.
    registro.limpar()
    with TestClient(app) as backend_reiniciado:
        resposta = backend_reiniciado.get(
            f"/api/simulacoes/{simulacao_id}/parametros"
        )
        assert resposta.status_code == 200
        assert resposta.json()["disponivel"] is True
    registro.limpar()


def test_revisao_e_build_confiaveis_ficam_registrados_quando_disponiveis(
    cliente_com_cenarios,
    monkeypatch,
):
    cliente = cliente_com_cenarios
    revisao = "0123456789abcdef" * 2 + "01234567"
    monkeypatch.setenv("PONTO_A_PONTO_GIT_REVISION", revisao)
    monkeypatch.setenv("PONTO_A_PONTO_BUILD_ID", "release-2026.11")
    cenario = cliente.cenarios_por_codigo["NORMAL"]
    criada = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario.id,
            "inicio": INICIO.isoformat(),
            "provedor": "simulado",
        },
    )
    assert criada.status_code == 201
    registro.limpar()

    dados = cliente.get(
        f"/api/simulacoes/{criada.json()['id']}/parametros"
    ).json()
    assert dados["parametros"]["aplicacao"] == {
        "revisao_git": revisao,
        "build_id": "release-2026.11",
    }


def test_simulacao_legada_retorna_parametros_indisponiveis(
    cliente_com_cenarios,
):
    cliente = cliente_com_cenarios
    cenario = cliente.cenarios_por_codigo["NORMAL"]
    with database.conectar() as conexao:
        cursor = conexao.execute(
            """
            INSERT INTO simulacoes (
                cenario_id, criada_em, inicio_simulado, centro_nome,
                estrategia, entregadores
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                cenario.id,
                INICIO.isoformat(),
                INICIO.isoformat(),
                "Centro legado",
                "DistribuicaoInsercaoMaisBarata",
                "CAM-01",
            ),
        )
        simulacao_id = cursor.lastrowid

    resposta = cliente.get(f"/api/simulacoes/{simulacao_id}/parametros")
    assert resposta.status_code == 200
    assert resposta.json() == {
        "simulacao_id": simulacao_id,
        "disponivel": False,
        "parametros": None,
        "snapshot_pedidos": None,
        "consultas_roteamento": [],
        "planejamento": {
            "estado": "desconhecido",
            "integridade": "desconhecida",
            "consultas_esperadas": None,
            "consultas_registradas": 0,
            "erro": None,
            "problemas": [],
        },
    }


def test_criacao_da_auditoria_e_snapshot_usa_uma_transacao(
    banco_temporario,
):
    with pytest.raises(KeyError, match="versao"):
        AuditoriaSimulacao.criar(
            INICIO,
            CENTRO,
            [Entregador("CAM-01")],
            "Teste",
            parametros={"versao": 1},
            snapshot_pedidos={"dados": []},
        )

    with database.conectar() as conexao:
        assert conexao.execute(
            "SELECT count(*) FROM simulacoes"
        ).fetchone()[0] == 0
        assert conexao.execute(
            "SELECT count(*) FROM simulacao_pedidos_snapshot"
        ).fetchone()[0] == 0


def test_api_interrompe_planejamento_com_erro_explicito_se_a_auditoria_falhar(
    cliente_com_cenarios,
    monkeypatch,
):
    cliente = cliente_com_cenarios

    def falhar_persistencia(self, **_):
        raise sqlite3.OperationalError("banco indisponível")

    monkeypatch.setattr(
        AuditoriaSimulacao,
        "registrar_consulta_roteamento",
        falhar_persistencia,
    )
    cenario = cliente.cenarios_por_codigo["NORMAL"]
    criada = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario.id,
            "inicio": INICIO.isoformat(),
            "provedor": "simulado",
        },
    )
    assert criada.status_code == 201

    resposta = cliente.post(
        f"/api/simulacoes/{criada.json()['id']}/proxima-etapa"
    )
    assert resposta.status_code == 503
    assert "interrompeu o planejamento" in resposta.json()["detail"]
    ativa = registro.obter(criada.json()["id"])
    assert ativa.simulacao.plano is None
    assert ativa.simulacao.historico == []
    with database.conectar() as conexao:
        assert conexao.execute(
            "SELECT count(*) FROM consultas_roteamento_simulacao"
        ).fetchone()[0] == 0


class TransporteGoogleFalso:
    def __init__(self):
        self.requisicoes = []

    def __call__(self, requisicao):
        self.requisicoes.append(requisicao)
        if requisicao.url.path.endswith("computeRouteMatrix"):
            dados_requisicao = json.loads(requisicao.content)
            corpo = [
                {
                    "originIndex": origem_indice,
                    "destinationIndex": destino_indice,
                    "condition": "ROUTE_EXISTS",
                    "distanceMeters": 1000 + origem_indice * 10 + destino_indice,
                    "duration": f"{100 + origem_indice * 10 + destino_indice}s",
                    "staticDuration": "80s",
                    "status": {},
                }
                for origem_indice in range(len(dados_requisicao["origins"]))
                for destino_indice in range(
                    len(dados_requisicao["destinations"])
                )
            ]
        else:
            corpo = {
                "routes": [
                    {
                        "distanceMeters": 1000,
                        "duration": "100s",
                        "staticDuration": "80s",
                        "polyline": {"encodedPolyline": "encoded-test"},
                        "legs": [
                            {
                                "distanceMeters": 1000,
                                "duration": "100s",
                                "staticDuration": "80s",
                            }
                        ],
                    }
                ]
            }
        return httpx.Response(200, json=corpo)


def test_matrizes_e_rotas_do_google_e_do_cache_sao_auditadas_e_deduplicadas(
    banco_temporario,
):
    transporte = TransporteGoogleFalso()
    cliente_http = httpx.Client(transport=httpx.MockTransport(transporte))
    google = ServicoRoteamentoGoogle(
        chave_api="SEGREDO-QUE-NAO-DEVE-PERSISTIR",
        cliente_http=cliente_http,
    )
    cache = ServicoRoteamentoComCache(google, janela_min=15)
    auditavel = ServicoRoteamentoAuditavel(cache, "google")
    entregadores = [Entregador("CAM-01")]
    auditoria = AuditoriaSimulacao.criar(
        INICIO,
        CENTRO,
        entregadores,
        "DistribuicaoInsercaoMaisBarata",
        parametros={"versao": 1},
        snapshot_pedidos={"versao": 1},
    )
    auditavel.conectar_auditoria(auditoria.registrar_consulta_roteamento)

    origens = [CENTRO.coordenada, BARRA]
    destinos = [BARRA, CENTRO.coordenada]
    primeira_matriz = auditavel.calcular_matriz(origens, destinos)
    segunda_matriz = auditavel.calcular_matriz(origens, destinos)
    primeira_rota = auditavel.calcular_rota(
        CENTRO.coordenada, CENTRO.coordenada, [BARRA]
    )
    segunda_rota = auditavel.calcular_rota(
        CENTRO.coordenada, CENTRO.coordenada, [BARRA]
    )

    assert primeira_matriz.elementos == segunda_matriz.elementos
    assert primeira_rota == segunda_rota
    # Só uma chamada externa de cada tipo; a segunda consulta veio do cache.
    assert len(transporte.requisicoes) == 2

    dados = obter_parametros_experimentais(auditoria.simulacao_id)
    consultas = dados["consultas_roteamento"]
    assert [consulta["sequencia"] for consulta in consultas] == [1, 2, 3, 4]
    assert [consulta["tipo"] for consulta in consultas] == [
        "matriz", "matriz", "rota", "rota"
    ]
    assert [consulta["origem_resultado"] for consulta in consultas] == [
        "provedor", "cache", "provedor", "cache"
    ]
    assert all(consulta["provedor"] == "google" for consulta in consultas)
    assert consultas[0]["resposta"]["hash_sha256"] == consultas[1]["resposta"]["hash_sha256"]
    assert consultas[2]["resposta"]["hash_sha256"] == consultas[3]["resposta"]["hash_sha256"]
    assert consultas[0]["resposta"]["dados"]["elementos"][0] == {
        "origem_indice": 0,
        "destino_indice": 0,
        "rota_existe": True,
        "distancia_m": 1000,
        "duracao_s": 100.0,
        "duracao_sem_transito_s": 80.0,
        "fator_transito": 1.25,
    }
    assert [
        (elemento["origem_indice"], elemento["destino_indice"])
        for elemento in consultas[0]["resposta"]["dados"]["elementos"]
    ] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert consultas[0]["requisicao"]["origens"] == [
        {"latitude": -12.971, "longitude": -38.501},
        {"latitude": -13.006, "longitude": -38.528},
    ]
    resposta_rota = consultas[2]["resposta"]["dados"]
    assert resposta_rota["polyline_codificada"] == "encoded-test"
    assert resposta_rota["trechos"] == [
        {
            "distancia_m": 1000,
            "duracao_s": 100.0,
            "duracao_sem_transito_s": 80.0,
        }
    ]

    with database.conectar() as conexao:
        quantidade_respostas = conexao.execute(
            "SELECT count(*) FROM respostas_roteamento"
        ).fetchone()[0]
        resposta_id = conexao.execute(
            """
            SELECT resposta_id FROM consultas_roteamento_simulacao
            WHERE simulacao_id = ? ORDER BY sequencia LIMIT 1
            """,
            (auditoria.simulacao_id,),
        ).fetchone()[0]
        quantidade_consultas = conexao.execute(
            """
            SELECT count(*) FROM consultas_roteamento_simulacao
            WHERE simulacao_id = ?
            """,
            (auditoria.simulacao_id,),
        ).fetchone()[0]
    assert quantidade_respostas == 2
    assert quantidade_consultas == 4
    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                "DELETE FROM respostas_roteamento WHERE id = ?",
                (resposta_id,),
            )
    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                "UPDATE respostas_roteamento SET dados_json = '{}' WHERE id = ?",
                (resposta_id,),
            )

    serialized = json.dumps(dados, ensure_ascii=False)
    assert "SEGREDO-QUE-NAO-DEVE-PERSISTIR" not in serialized
    assert "SEGREDO-QUE-NAO-DEVE-PERSISTIR" not in json.dumps(
        auditavel.parametros_auditoria(), ensure_ascii=False
    )
    configuracao_google = auditavel.parametros_auditoria()
    assert configuracao_google["api"]["preferencia_roteamento"] == "TRAFFIC_AWARE"
    assert configuracao_google["cache"]["janela_minutos"] == 15


def test_hash_canonico_deduplica_objetos_com_ordem_de_chaves_diferente(
    banco_temporario,
):
    auditoria = AuditoriaSimulacao.criar(
        INICIO,
        CENTRO,
        [Entregador("CAM-01")],
        "Teste",
        parametros={"versao": 1},
        snapshot_pedidos={"versao": 1},
    )
    consulta = {
        "tipo": "rota",
        "provedor": "google",
        "perfil": "google:TRAFFIC_AWARE",
        "origem_resultado": "provedor",
        "partida_em": INICIO,
        "consultada_em": datetime.now(timezone.utc),
        "requisicao": {"versao": 1, "origem": "A", "destino": "B"},
    }
    resposta_1 = {"distancia_m": 12, "duracao_s": 5.0}
    resposta_2 = {"duracao_s": 5.0, "distancia_m": 12}

    auditoria.registrar_consulta_roteamento(
        **consulta,
        resposta=resposta_1,
    )
    auditoria.registrar_consulta_roteamento(
        **consulta,
        resposta=resposta_2,
    )

    with database.conectar() as conexao:
        respostas = conexao.execute(
            "SELECT count(*) FROM respostas_roteamento"
        ).fetchone()[0]
        consultas = conexao.execute(
            """
            SELECT sequencia, resposta_id
            FROM consultas_roteamento_simulacao
            WHERE simulacao_id = ? ORDER BY sequencia
            """,
            (auditoria.simulacao_id,),
        ).fetchall()
    assert respostas == 1
    assert [consulta["sequencia"] for consulta in consultas] == [1, 2]
    assert consultas[0]["resposta_id"] == consultas[1]["resposta_id"]


def test_falha_de_persistencia_bloqueia_planejamento_e_nao_entrega_resultado(
    banco_temporario,
):
    pedido = Pedido(
        codigo="P-1",
        bairro=Bairro("Barra", -13.006, -38.528, id=1),
        categoria_produto=CategoriaProduto.ALIMENTO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=1,
        criado_em=datetime(2026, 10, 29, 9, 0, tzinfo=FUSO),
        prazo_entrega_em=datetime(2026, 10, 30, 17, 0, tzinfo=FUSO),
    )
    base = ServicoRoteamentoSimulado(fator_transito=2.0)
    auditavel = ServicoRoteamentoAuditavel(base, "simulado")

    def falhar_persistencia(**_):
        raise sqlite3.OperationalError("disco temporariamente indisponível")

    auditavel.conectar_auditoria(falhar_persistencia)
    simulacao = Simulacao(
        [pedido],
        DistribuidorPedidos(auditavel, CENTRO, [Entregador("CAM-01")]),
        INICIO,
    )

    with pytest.raises(
        FalhaPersistenciaAuditoriaRoteamento,
        match="interrompeu o planejamento",
    ):
        simulacao.iniciar()

    assert simulacao.iniciada is False
    assert simulacao.plano is None
    assert simulacao.historico == []
