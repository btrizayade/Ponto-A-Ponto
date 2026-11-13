"""Executa e compara os cenarios F09 em um SQLite temporario isolado.

Uso: cd backend && python scripts/comparar_cenarios_f09.py
O resultado JSON vai para stdout; nenhum banco de desenvolvimento e alterado.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

from app.api.registro import registro
from app.infrastructure import database
from app.infrastructure.routing_factory import VARIAVEL_PROVEDOR
from app.infrastructure.seed import inicializar_todos_cenarios
from app.main import app


INICIO = "2026-10-30T10:00:00-03:00"
QUANTIDADE_ENTREGADORES = 2
ESTRATEGIAS = (
    "insercao_mais_barata",
    "ordem_da_fila",
    "equidade_sla",
)


def _resumo(estado: dict) -> dict:
    indicadores = estado["indicadores"]
    entregues = [
        pedido for pedido in estado["pedidos"]
        if pedido["entregue_em"] is not None
    ]
    tempos = [
        (
            datetime.fromisoformat(pedido["entregue_em"])
            - datetime.fromisoformat(pedido["criado_em"])
        ).total_seconds() / 60
        for pedido in entregues
    ]
    inicio_simulacao = datetime.fromisoformat(estado["inicio"])
    tempos_desde_inicio = [
        (
            datetime.fromisoformat(pedido["entregue_em"])
            - inicio_simulacao
        ).total_seconds() / 60
        for pedido in entregues
    ]
    atrasos = [
        pedido["atraso_min"]
        for pedido in entregues
        if pedido["atraso_min"] is not None and pedido["atraso_min"] > 0
    ]
    bairros = indicadores["por_bairro"]
    sla_valido = sum(b["entregues_com_sla_valido"] for b in bairros)
    no_prazo = sum(b["entregues_no_prazo"] for b in bairros)

    return {
        "pedidos": indicadores["total_pedidos"],
        "entregues": indicadores["entregues"],
        "atrasados": indicadores["entregues_atrasados"],
        "cumprimento_sla_pct": (
            round(100 * no_prazo / sla_valido, 2) if sla_valido else None
        ),
        "tempo_medio_entrega_min": (
            round(sum(tempos) / len(tempos), 2) if tempos else None
        ),
        "tempo_medio_desde_inicio_simulacao_min": (
            round(sum(tempos_desde_inicio) / len(tempos_desde_inicio), 2)
            if tempos_desde_inicio else None
        ),
        "atraso_medio_min": (
            round(sum(atrasos) / len(atrasos), 2) if atrasos else None
        ),
        "atraso_normalizado_por_bairro": {
            b["bairro"]: b["atraso_medio_normalizado_sla"]
            for b in bairros
        },
        "indice_equidade_territorial": indicadores["equidade_territorial"][
            "indice_equidade_territorial_real"
        ],
        "distancia_total_m": indicadores["distancia_percorrida_m"],
        "desempenho_entregadores": [
            {
                "codigo": e["codigo"],
                "entregas": e["entregas"],
                "entregas_atrasadas": e["entregas_atrasadas"],
                "distancia_percorrida_m": e["distancia_percorrida_m"],
            }
            for e in estado["entregadores"]
        ],
    }


def _executar(cliente, cenario_id: int, estrategia: str | None = None) -> dict:
    requisicao = {
        "cenario_id": cenario_id,
        "inicio": INICIO,
        "provedor": "simulado",
        "quantidade_entregadores": QUANTIDADE_ENTREGADORES,
    }
    if estrategia is not None:
        requisicao["estrategia"] = estrategia
    criada = cliente.post("/api/simulacoes", json=requisicao)
    if criada.status_code != 201:
        raise RuntimeError(f"Falha ao criar simulacao: {criada.text}")
    estado_resposta = cliente.post(
        f"/api/simulacoes/{criada.json()['id']}/executar"
    )
    if estado_resposta.status_code != 200:
        raise RuntimeError(f"Falha ao executar simulacao: {estado_resposta.text}")
    estado = estado_resposta.json()["estado"]
    if not estado["concluida"]:
        raise RuntimeError("A simulacao nao chegou ao fim.")
    return {"estrategia": criada.json()["estrategia"], **_resumo(estado)}


def _executar_em_banco_isolado(
    db_dir: Path,
    codigo_cenario: str,
    estrategia: str | None = None,
) -> tuple[dict, str]:
    """Executa uma única simulação após semear um banco limpo."""

    database.DATABASE_DIR = db_dir
    database.DATABASE_PATH = db_dir / "experimento.db"
    os.environ[VARIAVEL_PROVEDOR] = "simulado"
    cenarios = inicializar_todos_cenarios()
    ids = {cenario.codigo: cenario.id for cenario in cenarios}
    registro.limpar()

    try:
        with TestClient(app) as cliente:
            pedidos = cliente.get(
                f"/api/cenarios/{ids[codigo_cenario]}/pedidos"
            ).json()
            fingerprint = hashlib.sha256(
                json.dumps(
                    pedidos,
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            metricas = _executar(
                cliente,
                ids[codigo_cenario],
                estrategia,
            )
        return metricas, fingerprint
    finally:
        registro.limpar()


def _executar_experimentos() -> dict:
    with tempfile.TemporaryDirectory(prefix="ponto-a-ponto-f09-") as temp:
        raiz = Path(temp)
        por_cenario = {}
        hashes_cenarios = {}
        for codigo in ("NORMAL", "ALTA_DEMANDA", "EQUIDADE"):
            por_cenario[codigo], hashes_cenarios[codigo] = (
                _executar_em_banco_isolado(raiz / codigo, codigo)
            )

        comparacao = {}
        hashes_estrategias = {}
        for estrategia in ESTRATEGIAS:
            comparacao[estrategia], hashes_estrategias[estrategia] = (
                _executar_em_banco_isolado(
                    raiz / f"EQUIDADE-{estrategia}",
                    "EQUIDADE",
                    estrategia,
                )
            )

        contagens = {
            codigo: metricas["pedidos"]
            for codigo, metricas in por_cenario.items()
        }
        fingerprints = set(hashes_estrategias.values())
        if len(fingerprints) != 1:
            raise RuntimeError(
                "Os pedidos EQUIDADE mudaram entre execuções comparadas."
            )

        return {
            "metodologia": {
                "inicio": INICIO,
                "provedor": "simulado",
                "entregadores": QUANTIDADE_ENTREGADORES,
                "capacidade_por_entregador": {
                    "paradas_por_viagem": 6,
                    "peso_kg": 500,
                    "volume_l": 3000,
                },
                "pedido_count_por_cenario": contagens,
                "banco_sqlite": "temporario e reinicializado para cada execucao",
                "comparacao_estrategias_cenario": "EQUIDADE",
                "fingerprint_pedidos_equidade": next(iter(fingerprints)),
                "fingerprints_iguais": hashes_cenarios["EQUIDADE"]
                == next(iter(fingerprints)),
                "comparacao_normal_alta_demanda": (
                    "Massas distintas (10 pedidos NORMAL antigos; 24 pedidos "
                    "ALTA_DEMANDA criados entre 09:00 e 09:23 em 2026-10-30). "
                    "Interprete taxas e médias como perfis de operação, não "
                    "como efeito causal isolado."
                ),
            },
            "cenarios": por_cenario,
            "estrategias_no_mesmo_cenario": comparacao,
        }


if __name__ == "__main__":
    try:
        print(json.dumps(_executar_experimentos(), indent=2, ensure_ascii=False))
    finally:
        registro.limpar()
