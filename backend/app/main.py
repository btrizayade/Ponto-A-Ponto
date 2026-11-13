import os
from contextlib import asynccontextmanager

import app.config  # noqa: F401  Carrega o backend/.env.
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import cenarios, pedidos, simulacoes
from app.domain.routing import ErroRoteamento
from app.infrastructure.controle_uso_api import LimiteUsoExcedido
from app.infrastructure.execucao_automatica import ExecucaoAutomatica
from app.infrastructure.database import inicializar_banco

VARIAVEL_INTERVALO_EXECUCAO = "INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS"
VARIAVEL_EXECUCAO_AUTOMATICA = "EXECUCAO_AUTOMATICA_ATIVA"


def _booleano_ambiente(nome: str, padrao: bool) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return padrao

    return valor.strip().lower() not in {
        "0",
        "false",
        "nao",
        "não",
        "no",
        "off",
    }


@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    inicializar_banco()
    intervalo = float(os.getenv(VARIAVEL_INTERVALO_EXECUCAO, "0.05"))
    executor = ExecucaoAutomatica(
        intervalo_segundos=intervalo,
        habilitada=_booleano_ambiente(VARIAVEL_EXECUCAO_AUTOMATICA, True),
    )
    app.state.execucao_automatica = executor
    try:
        yield
    finally:
        await executor.encerrar()


app = FastAPI(
    title="Simulador de Filas de Prioridade",
    description="API para simular o despacho de entregas em Salvador.",
    version="0.1.0",
    lifespan=ciclo_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "simulador-filas-prioridade",
    }


app.include_router(cenarios.router)
app.include_router(pedidos.router)
app.include_router(simulacoes.router)


@app.exception_handler(LimiteUsoExcedido)
def limite_uso_excedido(_: Request, erro: LimiteUsoExcedido):
    return JSONResponse(status_code=429, content={"detail": str(erro)})


@app.exception_handler(ErroRoteamento)
def erro_roteamento(_: Request, erro: ErroRoteamento):
    """Falha do provedor de mapas: a simulacao nao muda de estado."""

    return JSONResponse(
        status_code=502,
        content={"detail": f"Falha no servico de mapas: {erro}"},
    )
