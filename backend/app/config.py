from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"


def carregar_variaveis_ambiente() -> None:
    """
    Carrega as variaveis do arquivo backend/.env, se existir.

    Variaveis ja definidas no ambiente tem precedencia sobre o arquivo.
    """

    load_dotenv(ENV_PATH, override=False)


carregar_variaveis_ambiente()
