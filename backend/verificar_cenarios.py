from app.infrastructure.database import conectar

with conectar() as db:
    resultado = db.execute("""
        SELECT
            c.codigo,
            COUNT(p.id) AS total_pedidos
        FROM cenarios c
        LEFT JOIN pedidos p
            ON p.cenario_id = c.id
            AND p.ativo = 1
        GROUP BY c.id, c.codigo
        ORDER BY c.codigo
    """)

    for linha in resultado:
        print(dict(linha))
