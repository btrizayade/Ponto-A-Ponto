"""Manifesto legado dos pedidos originais dos cenários."""

CODIGOS_REFERENCIA_LEGADOS = {
    "NORMAL": tuple(f"PED-{numero:03d}" for numero in range(1, 11)),
    "ALTA_DEMANDA": tuple(f"ALTA-{numero:03d}" for numero in range(1, 25)),
    # EQ-016 fazia parte do seed antigo de 16 pedidos e será arquivado.
    "EQUIDADE": tuple(f"EQ-{numero:03d}" for numero in range(1, 17)),
}