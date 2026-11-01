import app.config  # noqa: F401  Carrega o backend/.env.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Simulador de Filas de Prioridade",
    description="API para simular o despacho de entregas em Salvador.",
    version="0.1.0",
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