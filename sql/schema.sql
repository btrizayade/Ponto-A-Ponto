
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bairros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL COLLATE NOCASE UNIQUE
        CHECK (length(trim(nome)) > 0),
    latitude REAL NOT NULL
        CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL
        CHECK (longitude BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS cenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE
        CHECK (length(trim(codigo)) > 0),
    nome TEXT NOT NULL
        CHECK (length(trim(nome)) > 0),
    descricao TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL
        CHECK (length(trim(codigo)) > 0),

    cenario_id INTEGER NOT NULL,
    bairro_id INTEGER NOT NULL,

    categoria_produto TEXT NOT NULL
        CHECK (
            categoria_produto IN (
                'alimento',
                'medicamento',
                'roupa',
                'eletronico',
                'outro'
            )
        ),

    cliente_clube INTEGER NOT NULL
        CHECK (cliente_clube IN (0, 1)),

    entrega_rapida INTEGER NOT NULL
        CHECK (entrega_rapida IN (0, 1)),

    sla_dias_uteis INTEGER NOT NULL
        CHECK (sla_dias_uteis > 0),

    criado_em TEXT NOT NULL,
    prazo_entrega_em TEXT NOT NULL,

    peso_kg REAL NOT NULL DEFAULT 0
        CHECK (peso_kg >= 0),

    volume_l REAL NOT NULL DEFAULT 0
        CHECK (volume_l >= 0),

    tempo_servico_min INTEGER NOT NULL DEFAULT 5
        CHECK (tempo_servico_min >= 0),

    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (
            status IN (
                'pendente',
                'na_fila',
                'atribuido',
                'em_rota',
                'entregue'
            )
        ),

    origem TEXT NOT NULL DEFAULT 'manual'
        CHECK (origem IN ('referencia', 'manual')),

    ativo INTEGER NOT NULL DEFAULT 1
        CHECK (ativo IN (0, 1)),

    FOREIGN KEY (cenario_id)
        REFERENCES cenarios(id)
        ON DELETE CASCADE,

    FOREIGN KEY (bairro_id)
        REFERENCES bairros(id)
        ON DELETE RESTRICT,

    UNIQUE (cenario_id, codigo)
);

CREATE INDEX IF NOT EXISTS idx_pedidos_cenario_status
    ON pedidos (cenario_id, status);

CREATE INDEX IF NOT EXISTS idx_pedidos_bairro
    ON pedidos (bairro_id);

CREATE TABLE IF NOT EXISTS uso_api_mapas (
    data TEXT NOT NULL,
    tipo TEXT NOT NULL
        CHECK (tipo IN ('elementos_matriz', 'rotas')),
    quantidade INTEGER NOT NULL DEFAULT 0
        CHECK (quantidade >= 0),

    PRIMARY KEY (data, tipo)
);

CREATE TABLE IF NOT EXISTS cache_matriz_rotas (
    perfil TEXT NOT NULL,
    origem TEXT NOT NULL,
    destino TEXT NOT NULL,
    faixa_horario TEXT NOT NULL,
    rota_existe INTEGER NOT NULL
        CHECK (rota_existe IN (0, 1)),
    distancia_m INTEGER NOT NULL DEFAULT 0,
    duracao_s REAL NOT NULL DEFAULT 0,
    duracao_sem_transito_s REAL NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL,

    PRIMARY KEY (perfil, origem, destino, faixa_horario)
);

CREATE TABLE IF NOT EXISTS cache_rotas (
    perfil TEXT NOT NULL,
    paradas TEXT NOT NULL,
    faixa_horario TEXT NOT NULL,
    dados TEXT NOT NULL,
    criado_em TEXT NOT NULL,

    PRIMARY KEY (perfil, paradas, faixa_horario)
);

CREATE TABLE IF NOT EXISTS simulacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cenario_id INTEGER,
    criada_em TEXT NOT NULL,
    inicio_simulado TEXT NOT NULL,
    fim_simulado TEXT,
    centro_nome TEXT NOT NULL,
    estrategia TEXT NOT NULL,
    entregadores TEXT NOT NULL,
    parametros_json TEXT,
    planejamento_status TEXT
        CHECK (
            planejamento_status IS NULL
            OR planejamento_status IN (
                'aguardando', 'planejando', 'concluido', 'falhou',
                'interrompido'
            )
        ),
    consultas_roteamento_contagem INTEGER
        CHECK (
            consultas_roteamento_contagem IS NULL
            OR consultas_roteamento_contagem >= 0
        ),
    planejamento_erro TEXT,
    segundos_reais_por_hora_simulada INTEGER NOT NULL DEFAULT 15
        CHECK (segundos_reais_por_hora_simulada IN (5, 15, 30, 60)),
    limite_pedido_manual_id INTEGER,
    status TEXT NOT NULL DEFAULT 'em_andamento'
        CHECK (status IN ('em_andamento', 'concluida')),

    FOREIGN KEY (cenario_id)
        REFERENCES cenarios(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS simulacao_pedidos_snapshot (
    simulacao_id INTEGER PRIMARY KEY,
    versao INTEGER NOT NULL CHECK (versao > 0),
    dados_json TEXT NOT NULL,

    FOREIGN KEY (simulacao_id)
        REFERENCES simulacoes(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS respostas_roteamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('matriz', 'rota')),
    versao INTEGER NOT NULL CHECK (versao > 0),
    hash_sha256 TEXT NOT NULL UNIQUE,
    dados_json TEXT NOT NULL,
    criada_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consultas_roteamento_simulacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulacao_id INTEGER NOT NULL,
    sequencia INTEGER NOT NULL CHECK (sequencia > 0),
    tipo TEXT NOT NULL CHECK (tipo IN ('matriz', 'rota')),
    provedor TEXT NOT NULL,
    perfil TEXT NOT NULL,
    origem_resultado TEXT NOT NULL
        CHECK (origem_resultado IN ('provedor', 'cache', 'misto', 'desconhecido')),
    partida_em TEXT,
    consultada_em TEXT NOT NULL,
    requisicao_json TEXT NOT NULL,
    resposta_id INTEGER NOT NULL,

    FOREIGN KEY (simulacao_id)
        REFERENCES simulacoes(id)
        ON DELETE CASCADE,
    FOREIGN KEY (resposta_id)
        REFERENCES respostas_roteamento(id)
        ON DELETE RESTRICT,
    UNIQUE (simulacao_id, sequencia)
);

CREATE INDEX IF NOT EXISTS idx_consultas_roteamento_simulacao
    ON consultas_roteamento_simulacao (simulacao_id, sequencia);

CREATE TRIGGER IF NOT EXISTS trg_simulacao_pedidos_snapshot_immutable
BEFORE UPDATE ON simulacao_pedidos_snapshot
BEGIN
    SELECT RAISE(ABORT, 'O snapshot de pedidos e imutavel.');
END;

CREATE TRIGGER IF NOT EXISTS trg_simulacoes_parametros_immutable
BEFORE UPDATE OF parametros_json ON simulacoes
WHEN OLD.parametros_json IS NOT NEW.parametros_json
BEGIN
    SELECT RAISE(ABORT, 'Os parametros experimentais sao imutaveis.');
END;

CREATE TRIGGER IF NOT EXISTS trg_simulacao_pedidos_snapshot_no_delete
BEFORE DELETE ON simulacao_pedidos_snapshot
WHEN EXISTS (
    SELECT 1 FROM simulacoes WHERE id = OLD.simulacao_id
)
BEGIN
    SELECT RAISE(ABORT, 'O snapshot so pode ser removido com a simulacao.');
END;

CREATE TRIGGER IF NOT EXISTS trg_respostas_roteamento_immutable
BEFORE UPDATE ON respostas_roteamento
BEGIN
    SELECT RAISE(ABORT, 'A resposta de roteamento e imutavel.');
END;

CREATE TRIGGER IF NOT EXISTS trg_consultas_roteamento_immutable
BEFORE UPDATE ON consultas_roteamento_simulacao
BEGIN
    SELECT RAISE(ABORT, 'A consulta de roteamento e imutavel.');
END;

CREATE TRIGGER IF NOT EXISTS trg_consultas_roteamento_no_delete
BEFORE DELETE ON consultas_roteamento_simulacao
WHEN EXISTS (
    SELECT 1 FROM simulacoes WHERE id = OLD.simulacao_id
)
BEGIN
    SELECT RAISE(ABORT, 'A consulta so pode ser removida com a simulacao.');
END;

CREATE TABLE IF NOT EXISTS eventos_simulacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulacao_id INTEGER NOT NULL,
    sequencia INTEGER NOT NULL
        CHECK (sequencia > 0),
    instante TEXT NOT NULL,
    tipo TEXT NOT NULL
        CHECK (
            tipo IN (
                'simulacao_iniciada',
                'pedido_na_fila',
                'pedido_atribuido',
                'pedido_nao_atribuido',
                'pedido_entregue',
                'viagem_concluida',
                'viagem_cancelada',
                'pedido_devolvido_a_fila',
                'viagem_iniciada',
                'pedido_em_rota',
                'simulacao_concluida'
            )
        ),
    pedido_codigo TEXT,
    entregador_codigo TEXT,
    viagem_numero INTEGER,
    atraso_min REAL,
    distancia_m INTEGER,
    detalhe TEXT NOT NULL DEFAULT '',

    FOREIGN KEY (simulacao_id)
        REFERENCES simulacoes(id)
        ON DELETE CASCADE,

    UNIQUE (simulacao_id, sequencia)
);

CREATE INDEX IF NOT EXISTS idx_eventos_simulacao_pedido
    ON eventos_simulacao (simulacao_id, pedido_codigo);

CREATE INDEX IF NOT EXISTS idx_eventos_simulacao_entregador
    ON eventos_simulacao (simulacao_id, entregador_codigo);

CREATE TRIGGER IF NOT EXISTS trg_eventos_simulacao_no_delete
BEFORE DELETE ON eventos_simulacao
WHEN EXISTS (
    SELECT 1 FROM simulacoes WHERE id = OLD.simulacao_id
)
BEGIN
    SELECT RAISE(ABORT, 'Eventos de simulacoes existentes sao imutaveis.');
END;

CREATE TRIGGER IF NOT EXISTS trg_simulacoes_no_delete_com_eventos
BEFORE DELETE ON simulacoes
WHEN EXISTS (
    SELECT 1 FROM eventos_simulacao WHERE simulacao_id = OLD.id
)
BEGIN
    SELECT RAISE(ABORT, 'Simulacoes com eventos nao podem ser excluidas.');
END;

CREATE TABLE IF NOT EXISTS mudancas_status_pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulacao_id INTEGER NOT NULL,
    evento_id INTEGER NOT NULL UNIQUE,
    pedido_codigo TEXT NOT NULL,
    instante TEXT NOT NULL,
    status_anterior TEXT
        CHECK (
            status_anterior IN (
                'pendente',
                'na_fila',
                'atribuido',
                'em_rota',
                'entregue'
            )
        ),
    status_novo TEXT NOT NULL
        CHECK (
            status_novo IN (
                'pendente',
                'na_fila',
                'atribuido',
                'em_rota',
                'entregue'
            )
        ),

    FOREIGN KEY (simulacao_id)
        REFERENCES simulacoes(id)
        ON DELETE CASCADE,

    FOREIGN KEY (evento_id)
        REFERENCES eventos_simulacao(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mudancas_status_pedido
    ON mudancas_status_pedido (simulacao_id, pedido_codigo);
