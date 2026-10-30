
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
