import os
from collections.abc import Callable
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.domain.routing import ErroRoteamento
from app.infrastructure.database import conectar, inicializar_banco


TIPO_ELEMENTOS_MATRIZ = "elementos_matriz"
TIPO_ROTAS = "rotas"

VARIAVEL_LIMITE_ELEMENTOS_MATRIZ = "LIMITE_DIARIO_ELEMENTOS_MATRIZ"
VARIAVEL_LIMITE_ROTAS = "LIMITE_DIARIO_ROTAS"

LIMITE_PADRAO_ELEMENTOS_MATRIZ = 150
LIMITE_PADRAO_ROTAS = 50

# As cotas diarias da Google reiniciam a meia-noite do horario do Pacifico.
FUSO_COTA_GOOGLE = ZoneInfo("America/Los_Angeles")


class LimiteUsoExcedido(ErroRoteamento):
    """O limite diario de consultas a API de mapas foi atingido."""


class ControleUsoApi:
    """
    Limita o uso diario da API de mapas pelo proprio backend.

    O consumo fica salvo no SQLite, entao o limite continua valendo
    apos reiniciar o servidor. O uso e reservado antes da chamada,
    inclusive quando a API falha, para errar a favor da economia.
    """

    def __init__(
        self,
        limites: dict[str, int],
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        for tipo, limite in limites.items():
            if tipo not in (TIPO_ELEMENTOS_MATRIZ, TIPO_ROTAS):
                raise ValueError(f"Tipo de uso desconhecido: {tipo}.")

            if isinstance(limite, bool) or not isinstance(limite, int):
                raise TypeError("O limite diario deve ser inteiro.")

            if limite < 1:
                raise ValueError("O limite diario deve ser positivo.")

        self._limites = dict(limites)
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self._banco_pronto = False

    @classmethod
    def do_ambiente(cls) -> "ControleUsoApi":
        """Cria o controle com os limites definidos no ambiente."""

        return cls(
            {
                TIPO_ELEMENTOS_MATRIZ: _ler_limite(
                    VARIAVEL_LIMITE_ELEMENTOS_MATRIZ,
                    LIMITE_PADRAO_ELEMENTOS_MATRIZ,
                ),
                TIPO_ROTAS: _ler_limite(
                    VARIAVEL_LIMITE_ROTAS,
                    LIMITE_PADRAO_ROTAS,
                ),
            }
        )

    def reservar(self, tipo: str, quantidade: int) -> None:
        """Registra o uso ou falha se ultrapassar o limite do dia."""

        if tipo not in self._limites:
            raise ValueError(f"Tipo de uso sem limite definido: {tipo}.")

        if quantidade < 1:
            raise ValueError("A quantidade reservada deve ser positiva.")

        limite = self._limites[tipo]

        if quantidade > limite:
            raise LimiteUsoExcedido(
                f"A consulta exige {quantidade} {tipo}, acima do "
                f"limite diario de {limite}."
            )

        self._garantir_banco()

        # Uma unica instrucao garante a reserva atomica no SQLite.
        with conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO uso_api_mapas (data, tipo, quantidade)
                VALUES (?, ?, ?)
                ON CONFLICT (data, tipo) DO UPDATE
                SET quantidade = quantidade + excluded.quantidade
                WHERE quantidade + excluded.quantidade <= ?
                """,
                (self._data_atual().isoformat(), tipo, quantidade, limite),
            )

        if cursor.rowcount == 0:
            raise LimiteUsoExcedido(
                f"Limite diario de {limite} {tipo} atingido. "
                f"Uso atual: {self.uso_do_dia(tipo)}."
            )

    def uso_do_dia(self, tipo: str) -> int:
        """Quantidade ja consumida hoje para o tipo informado."""

        self._garantir_banco()

        with conectar() as conexao:
            registro = conexao.execute(
                """
                SELECT quantidade
                FROM uso_api_mapas
                WHERE data = ? AND tipo = ?
                """,
                (self._data_atual().isoformat(), tipo),
            ).fetchone()

        return 0 if registro is None else registro["quantidade"]

    def restante_do_dia(self, tipo: str) -> int:
        """Quantidade ainda disponivel hoje para o tipo informado."""

        return max(0, self._limites[tipo] - self.uso_do_dia(tipo))

    def _garantir_banco(self) -> None:
        """Cria as tabelas no primeiro uso, e nao na construcao."""

        if not self._banco_pronto:
            inicializar_banco()
            self._banco_pronto = True

    def _data_atual(self) -> date:
        """Dia corrente no fuso em que a cota da Google reinicia."""

        return self._relogio().astimezone(FUSO_COTA_GOOGLE).date()


def _ler_limite(variavel: str, padrao: int) -> int:
    """Le um limite inteiro do ambiente ou usa o valor padrao."""

    valor = os.environ.get(variavel, "").strip()

    if not valor:
        return padrao

    try:
        return int(valor)
    except ValueError as erro:
        raise ValueError(
            f"A variavel {variavel} deve ser um numero inteiro."
        ) from erro
