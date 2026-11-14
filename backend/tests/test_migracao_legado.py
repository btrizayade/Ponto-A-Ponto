import sqlite3
from pathlib import Path

import pytest

from app.domain.models import OrigemPedido
from app.infrastructure import database
from app.infrastructure.pedido_repository import (
    listar_pedidos_por_cenario,
    obter_ou_criar_pedido,
)


SCHEMA_PRE_F09 = (
    Path(__file__).parent / "fixtures" / "schema_pre_f09.sql"
)


def _preparar_banco_legado(tmp_path, monkeypatch):
    diretorio = tmp_path / "dados_legados"
    caminho = diretorio / "pontoaponto_legado.db"
    diretorio.mkdir()
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", caminho)

    conexao = sqlite3.connect(caminho)
    try:
        conexao.executescript(SCHEMA_PRE_F09.read_text(encoding="utf-8"))
        conexao.executescript(
            """
            INSERT INTO bairros (id, nome, latitude, longitude)
            VALUES (7, 'Bairro legado', -12.98, -38.50);

            INSERT INTO cenarios (id, codigo, nome, descricao)
            VALUES
                (4, 'NORMAL', 'Operação normal', 'Cenário legado'),
                (5, 'EQUIDADE', 'Distribuição com Equidade', 'Legado');

            INSERT INTO pedidos (
                id, codigo, cenario_id, bairro_id, categoria_produto,
                cliente_clube, entrega_rapida, sla_dias_uteis, criado_em,
                prazo_entrega_em, peso_kg, volume_l, tempo_servico_min, status
            )
            VALUES
                (101, 'PED-001', 4, 7, 'alimento', 0, 1, 1,
                 '2025-02-03T09:00:00-03:00', '2025-02-04T09:00:00-03:00',
                 1.25, 2.5, 5, 'entregue'),
                (102, 'PED-LEGADO-EXTRA', 4, 7, 'roupa', 0, 0, 3,
                 '2025-02-04T09:00:00-03:00', '2025-02-07T09:00:00-03:00',
                 0.75, 1.5, 7, 'pendente'),
                (103, 'EQ-016', 5, 7, 'medicamento', 1, 1, 1,
                 '2025-02-05T09:00:00-03:00', '2025-02-06T09:00:00-03:00',
                 0.25, 0.5, 4, 'entregue');

            INSERT INTO simulacoes (
                id, cenario_id, criada_em, inicio_simulado, fim_simulado,
                centro_nome, estrategia, entregadores, status
            )
            VALUES (
                71, 4, '2025-02-03T08:55:00-03:00',
                '2025-02-03T09:00:00-03:00', '2025-02-03T10:15:00-03:00',
                'Centro legado', 'DistribuicaoFila', 'ENT-01', 'concluida'
            );

            INSERT INTO eventos_simulacao (
                id, simulacao_id, sequencia, instante, tipo, pedido_codigo,
                entregador_codigo, viagem_numero, atraso_min, distancia_m, detalhe
            )
            VALUES (
                81, 71, 1, '2025-02-03T10:00:00-03:00', 'pedido_entregue',
                'PED-001', 'ENT-01', 1, 2.5, 1800, 'Evento histórico legado'
            );

            INSERT INTO mudancas_status_pedido (
                id, simulacao_id, evento_id, pedido_codigo, instante,
                status_anterior, status_novo
            )
            VALUES (
                91, 71, 81, 'PED-001', '2025-02-03T10:00:00-03:00',
                'em_rota', 'entregue'
            );
            """
        )
        conexao.commit()
    finally:
        conexao.close()

    return caminho


def _linhas(caminho, consulta, parametros=()):
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    try:
        return [dict(linha) for linha in conexao.execute(consulta, parametros)]
    finally:
        conexao.close()


def test_migracao_pre_f09_preserva_historico_e_e_idempotente(
    tmp_path, monkeypatch
):
    caminho = _preparar_banco_legado(tmp_path, monkeypatch)

    colunas_legadas = {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(pedidos)")
    }
    colunas_simulacao_legadas = {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(simulacoes)")
    }
    assert "origem" not in colunas_legadas
    assert "ativo" not in colunas_legadas
    assert "segundos_reais_por_hora_simulada" not in colunas_simulacao_legadas
    assert "limite_pedido_manual_id" not in colunas_simulacao_legadas
    assert "parametros_json" not in colunas_simulacao_legadas

    pedidos_antes = _linhas(
        caminho,
        """
        SELECT id, codigo, cenario_id, bairro_id, criado_em,
               prazo_entrega_em, status
        FROM pedidos ORDER BY id
        """,
    )
    simulacao_antes = _linhas(
        caminho,
        """
        SELECT id, cenario_id, criada_em, inicio_simulado, fim_simulado,
               centro_nome, estrategia, entregadores, status
        FROM simulacoes
        """,
    )
    eventos_antes = _linhas(
        caminho,
        "SELECT * FROM eventos_simulacao ORDER BY id",
    )
    mudancas_antes = _linhas(
        caminho,
        "SELECT * FROM mudancas_status_pedido ORDER BY id",
    )

    # Este é o mesmo inicializador chamado no lifespan da aplicação. O
    # DATABASE_PATH foi redirecionado para o arquivo legado temporário.
    database.inicializar_banco()

    pedidos_depois = _linhas(
        caminho,
        """
        SELECT id, codigo, cenario_id, bairro_id, criado_em,
               prazo_entrega_em, status, origem, ativo
        FROM pedidos ORDER BY id
        """,
    )
    assert len(pedidos_depois) == len(pedidos_antes) == 3
    por_codigo = {linha["codigo"]: linha for linha in pedidos_depois}
    assert por_codigo["PED-001"]["origem"] == "referencia"
    assert por_codigo["PED-LEGADO-EXTRA"]["origem"] == "referencia"
    assert por_codigo["PED-LEGADO-EXTRA"]["ativo"] == 1
    assert por_codigo["EQ-016"]["origem"] == "referencia"
    assert por_codigo["EQ-016"]["ativo"] == 0
    assert [
        {
            chave: linha[chave]
            for chave in (
                "id", "codigo", "cenario_id", "bairro_id", "criado_em",
                "prazo_entrega_em", "status",
            )
        }
        for linha in pedidos_depois
    ] == pedidos_antes

    simulacao_depois = _linhas(
        caminho,
        """
        SELECT id, cenario_id, criada_em, inicio_simulado, fim_simulado,
               centro_nome, estrategia, entregadores, status,
               segundos_reais_por_hora_simulada, limite_pedido_manual_id,
               parametros_json, planejamento_status,
               consultas_roteamento_contagem, planejamento_erro
        FROM simulacoes
        """,
    )
    assert [
        {
            chave: linha[chave]
            for chave in (
                "id", "cenario_id", "criada_em", "inicio_simulado",
                "fim_simulado", "centro_nome", "estrategia", "entregadores",
                "status",
            )
        }
        for linha in simulacao_depois
    ] == simulacao_antes
    assert simulacao_depois[0]["segundos_reais_por_hora_simulada"] == 15
    assert simulacao_depois[0]["limite_pedido_manual_id"] is None
    assert simulacao_depois[0]["parametros_json"] is None
    assert simulacao_depois[0]["planejamento_status"] is None
    assert simulacao_depois[0]["consultas_roteamento_contagem"] is None
    assert simulacao_depois[0]["planejamento_erro"] is None
    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                "UPDATE simulacoes SET parametros_json = '{}' WHERE id = 71"
            )
    tabelas_auditoria_experimental = {
        linha["name"]
        for linha in _linhas(
            caminho,
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                  'simulacao_pedidos_snapshot', 'respostas_roteamento',
                  'consultas_roteamento_simulacao'
              )
            """,
        )
    }
    assert tabelas_auditoria_experimental == {
        "simulacao_pedidos_snapshot",
        "respostas_roteamento",
        "consultas_roteamento_simulacao",
    }
    assert _linhas(caminho, "SELECT * FROM eventos_simulacao ORDER BY id") == eventos_antes
    assert _linhas(
        caminho,
        "SELECT * FROM mudancas_status_pedido ORDER BY id",
    ) == mudancas_antes

    # O schema legado não permitia identificar pedidos manuais. Uma linha
    # manual criada após a migração, contudo, deve permanecer manual ao repetir
    # a inicialização.
    with database.conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO pedidos (
                codigo, cenario_id, bairro_id, categoria_produto,
                cliente_clube, entrega_rapida, sla_dias_uteis, criado_em,
                prazo_entrega_em, peso_kg, volume_l, tempo_servico_min,
                status, origem, ativo
            )
            SELECT
                'MANUAL-POS-MIGRACAO', cenario_id, bairro_id,
                categoria_produto, cliente_clube, entrega_rapida,
                sla_dias_uteis, criado_em, prazo_entrega_em, peso_kg,
                volume_l, tempo_servico_min, 'pendente', 'manual', 1
            FROM pedidos WHERE id = 102
            """
        )

    database.inicializar_banco()

    pedidos_repetidos = _linhas(
        caminho,
        "SELECT codigo, origem, ativo FROM pedidos ORDER BY id",
    )
    assert len(pedidos_repetidos) == 4
    assert pedidos_repetidos[-1] == {
        "codigo": "MANUAL-POS-MIGRACAO",
        "origem": "manual",
        "ativo": 1,
    }
    assert _linhas(
        caminho,
        "SELECT * FROM eventos_simulacao ORDER BY id",
    ) == eventos_antes
    simulacao_historica = _linhas(
        caminho,
        """
        SELECT parametros_json, planejamento_status,
               consultas_roteamento_contagem, planejamento_erro
        FROM simulacoes WHERE id = 71
        """,
    )[0]
    assert simulacao_historica == {
        "parametros_json": None,
        "planejamento_status": None,
        "consultas_roteamento_contagem": None,
        "planejamento_erro": None,
    }


def test_migracao_recupera_estado_interrompido_apos_adicionar_origem(
    tmp_path, monkeypatch
):
    caminho = _preparar_banco_legado(tmp_path, monkeypatch)

    # Reproduz o primeiro DDL da migração anterior, que não tinha transação
    # explícita: a coluna foi persistida, mas as demais alterações não rodaram.
    conexao = sqlite3.connect(caminho)
    try:
        conexao.execute(
            """
            ALTER TABLE pedidos
            ADD COLUMN origem TEXT NOT NULL DEFAULT 'manual'
                CHECK (origem IN ('referencia', 'manual'))
            """
        )
        conexao.commit()
    finally:
        conexao.close()

    colunas_pedidos_parciais = {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(pedidos)")
    }
    colunas_simulacoes_parciais = {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(simulacoes)")
    }
    assert "origem" in colunas_pedidos_parciais
    assert "ativo" not in colunas_pedidos_parciais
    assert "segundos_reais_por_hora_simulada" not in colunas_simulacoes_parciais
    assert "limite_pedido_manual_id" not in colunas_simulacoes_parciais

    database.inicializar_banco()

    pedidos = _linhas(
        caminho,
        "SELECT codigo, origem, ativo FROM pedidos ORDER BY id",
    )
    por_codigo = {linha["codigo"]: linha for linha in pedidos}
    assert por_codigo["PED-001"] == {
        "codigo": "PED-001", "origem": "referencia", "ativo": 1
    }
    assert por_codigo["PED-LEGADO-EXTRA"] == {
        "codigo": "PED-LEGADO-EXTRA",
        "origem": "referencia",
        "ativo": 1,
    }
    assert por_codigo["EQ-016"] == {
        "codigo": "EQ-016", "origem": "referencia", "ativo": 0
    }
    assert {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(pedidos)")
    } >= {"origem", "ativo"}
    assert {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(simulacoes)")
    } >= {
        "segundos_reais_por_hora_simulada",
        "limite_pedido_manual_id",
    }


def test_colunas_de_simulacao_ausentes_nao_reclassificam_pedidos_manuais(
    tmp_path, monkeypatch
):
    caminho = _preparar_banco_legado(tmp_path, monkeypatch)
    conexao = sqlite3.connect(caminho)
    try:
        # Simula um formato anterior válido com origem/atividade e pedidos
        # manuais, mas ainda sem os campos mais novos da tabela simulacoes.
        conexao.execute(
            """
            ALTER TABLE pedidos
            ADD COLUMN origem TEXT NOT NULL DEFAULT 'manual'
                CHECK (origem IN ('referencia', 'manual'))
            """
        )
        conexao.execute(
            """
            ALTER TABLE pedidos
            ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1
                CHECK (ativo IN (0, 1))
            """
        )
        conexao.execute(
            "UPDATE pedidos SET origem = 'referencia', ativo = 1"
        )
        conexao.execute(
            """
            INSERT INTO pedidos (
                codigo, cenario_id, bairro_id, categoria_produto,
                cliente_clube, entrega_rapida, sla_dias_uteis, criado_em,
                prazo_entrega_em, peso_kg, volume_l, tempo_servico_min,
                status, origem, ativo
            )
            SELECT
                'MANUAL-VERSAO-ANTERIOR', cenario_id, bairro_id,
                categoria_produto, cliente_clube, entrega_rapida,
                sla_dias_uteis, criado_em, prazo_entrega_em, peso_kg,
                volume_l, tempo_servico_min, 'pendente', 'manual', 1
            FROM pedidos WHERE id = 102
            """
        )
        conexao.commit()
    finally:
        conexao.close()

    database.inicializar_banco()

    manual = _linhas(
        caminho,
        """
        SELECT origem, ativo FROM pedidos
        WHERE codigo = 'MANUAL-VERSAO-ANTERIOR'
        """,
    )
    assert manual == [{"origem": "manual", "ativo": 1}]
    assert "segundos_reais_por_hora_simulada" in {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(simulacoes)")
    }


def test_reinicializacao_nao_reclassifica_manual_com_codigo_de_referencia(
    tmp_path, monkeypatch
):
    caminho = _preparar_banco_legado(tmp_path, monkeypatch)
    database.inicializar_banco()

    # O banco permite um pedido manual com código conhecido quando a linha de
    # referência daquele código não existe mais. A unicidade só vale para a
    # combinação cenário/código.
    with database.conectar() as conexao:
        conexao.execute(
            "DELETE FROM pedidos WHERE cenario_id = 4 AND codigo = 'PED-001'"
        )
    pedido_manual = next(
        pedido
        for pedido in listar_pedidos_por_cenario(4)
        if pedido.codigo == "PED-LEGADO-EXTRA"
    )
    pedido_manual.codigo = "PED-001"
    pedido_manual.id = None
    obter_ou_criar_pedido(
        pedido_manual,
        4,
        origem=OrigemPedido.MANUAL,
    )

    database.inicializar_banco()

    pedido = _linhas(
        caminho,
        """
        SELECT origem, ativo FROM pedidos
        WHERE cenario_id = 4 AND codigo = 'PED-001'
        """,
    )
    assert pedido == [{"origem": "manual", "ativo": 1}]


def test_migracao_pre_f09_reverte_schema_e_dados_se_falhar(
    tmp_path, monkeypatch
):
    caminho = _preparar_banco_legado(tmp_path, monkeypatch)
    migracao_original = database._migrar_origem_e_atividade_pedidos

    def migrar_e_falhar(conexao):
        migracao_original(conexao)
        raise RuntimeError("falha simulada durante a migração")

    monkeypatch.setattr(
        database, "_migrar_origem_e_atividade_pedidos", migrar_e_falhar
    )
    with pytest.raises(RuntimeError, match="falha simulada"):
        database.inicializar_banco()

    colunas_pedidos = {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(pedidos)")
    }
    colunas_simulacoes = {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(simulacoes)")
    }
    assert "origem" not in colunas_pedidos
    assert "ativo" not in colunas_pedidos
    assert "segundos_reais_por_hora_simulada" not in colunas_simulacoes
    assert "limite_pedido_manual_id" not in colunas_simulacoes
    assert _linhas(caminho, "SELECT id, codigo FROM pedidos ORDER BY id") == [
        {"id": 101, "codigo": "PED-001"},
        {"id": 102, "codigo": "PED-LEGADO-EXTRA"},
        {"id": 103, "codigo": "EQ-016"},
    ]

    monkeypatch.setattr(
        database, "_migrar_origem_e_atividade_pedidos", migracao_original
    )
    database.inicializar_banco()
    assert "origem" in {
        linha["name"]
        for linha in _linhas(caminho, "PRAGMA table_info(pedidos)")
    }


def test_conectar_fecha_conexao_se_pragma_falhar(tmp_path, monkeypatch):
    class ConexaoFalsa:
        row_factory = None
        fechada = False
        rollback_chamado = False

        def execute(self, *_args):
            raise sqlite3.OperationalError("falha ao configurar PRAGMA")

        def rollback(self):
            self.rollback_chamado = True

        def close(self):
            self.fechada = True

    conexao_falsa = ConexaoFalsa()
    monkeypatch.setattr(database, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "fake.db")
    monkeypatch.setattr(
        database.sqlite3,
        "connect",
        lambda _caminho: conexao_falsa,
    )

    with pytest.raises(sqlite3.OperationalError, match="configurar PRAGMA"):
        with database.conectar():
            pytest.fail("A conexão não deveria chegar ao yield.")

    assert conexao_falsa.rollback_chamado is True
    assert conexao_falsa.fechada is True
