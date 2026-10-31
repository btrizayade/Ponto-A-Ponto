import json
import os
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.domain.routing import (
    Coordenada,
    ElementoMatriz,
    MatrizDistancias,
    RotaCalculada,
    ServicoRoteamento,
    TrechoRota,
    validar_partida,
    validar_pontos,
)
from app.infrastructure.database import conectar, inicializar_banco


VARIAVEL_JANELA_CACHE = "CACHE_ROTAS_JANELA_MIN"
JANELA_PADRAO_MIN = 15

FUSO_HORARIO = ZoneInfo("America/Bahia")

# Cinco casas decimais equivalem a cerca de 1 metro.
CASAS_DECIMAIS_CHAVE = 5


class ServicoRoteamentoComCache(ServicoRoteamento):
    """
    Envolve um servico de roteamento e reaproveita consultas iguais.

    O transito muda ao longo do dia, entao cada resultado vale para
    uma faixa de horario (padrao de 15 minutos). Na matriz, o cache
    e por par origem-destino: so os pares ausentes sao consultados,
    e coordenadas repetidas (pedidos no mesmo bairro) viram um unico
    ponto na consulta.
    """

    def __init__(
        self,
        servico: ServicoRoteamento,
        janela_min: int = JANELA_PADRAO_MIN,
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(janela_min, bool) or not isinstance(janela_min, int):
            raise TypeError("A janela do cache deve ser inteira.")

        if not 1 <= janela_min <= 24 * 60:
            raise ValueError(
                "A janela do cache deve estar entre 1 e 1440 minutos."
            )

        self._servico = servico
        self._janela_min = janela_min
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self._banco_pronto = False

        self.acertos = 0
        self.consultas_externas = 0

    @classmethod
    def do_ambiente(
        cls,
        servico: ServicoRoteamento,
    ) -> "ServicoRoteamentoComCache":
        """Cria o cache com a janela definida no ambiente."""

        valor = os.environ.get(VARIAVEL_JANELA_CACHE, "").strip()

        if not valor:
            return cls(servico)

        try:
            janela = int(valor)
        except ValueError as erro:
            raise ValueError(
                f"A variavel {VARIAVEL_JANELA_CACHE} deve ser inteira."
            ) from erro

        return cls(servico, janela_min=janela)

    def calcular_matriz(
        self,
        origens: Sequence[Coordenada],
        destinos: Sequence[Coordenada],
        partida_em: datetime | None = None,
    ) -> MatrizDistancias:
        """Monta a matriz com o cache e consulta so os pares ausentes."""

        validar_pontos(origens, "origem")
        validar_pontos(destinos, "destino")
        validar_partida(partida_em)

        faixa = self._faixa_horario(partida_em)
        chaves_origem = [_chave(ponto) for ponto in origens]
        chaves_destino = [_chave(ponto) for ponto in destinos]

        conhecidos = self._buscar_pares(
            set(chaves_origem),
            set(chaves_destino),
            faixa,
        )

        faltantes = [
            (origem, destino)
            for origem in dict.fromkeys(chaves_origem)
            for destino in dict.fromkeys(chaves_destino)
            if (origem, destino) not in conhecidos
        ]

        if faltantes:
            novos = self._consultar_pares(
                faltantes,
                dict(zip(chaves_origem, origens)),
                dict(zip(chaves_destino, destinos)),
                partida_em,
            )
            self._salvar_pares(novos, faixa)
            conhecidos.update(novos)
        else:
            self.acertos += 1

        matriz = MatrizDistancias(
            origens=list(origens),
            destinos=list(destinos),
        )

        for i, origem in enumerate(chaves_origem):
            for j, destino in enumerate(chaves_destino):
                dados = conhecidos[(origem, destino)]
                matriz.elementos[(i, j)] = ElementoMatriz(
                    origem_indice=i,
                    destino_indice=j,
                    rota_existe=dados.rota_existe,
                    distancia_m=dados.distancia_m,
                    duracao_s=dados.duracao_s,
                    duracao_sem_transito_s=dados.duracao_sem_transito_s,
                )

        return matriz

    def calcular_rota(
        self,
        origem: Coordenada,
        destino: Coordenada,
        paradas: Sequence[Coordenada] = (),
        partida_em: datetime | None = None,
    ) -> RotaCalculada:
        """Reaproveita a rota com as mesmas paradas na mesma faixa."""

        pontos = [origem, *paradas, destino]
        validar_pontos(pontos, "parada")
        validar_partida(partida_em)

        faixa = self._faixa_horario(partida_em)
        chave = ";".join(_chave(ponto) for ponto in pontos)

        self._garantir_banco()

        with conectar() as conexao:
            registro = conexao.execute(
                """
                SELECT dados
                FROM cache_rotas
                WHERE paradas = ? AND faixa_horario = ?
                """,
                (chave, faixa),
            ).fetchone()

        if registro is not None:
            self.acertos += 1
            return _rota_de_json(registro["dados"])

        rota = self._servico.calcular_rota(
            origem,
            destino,
            paradas=paradas,
            partida_em=partida_em,
        )
        self.consultas_externas += 1

        with conectar() as conexao:
            conexao.execute(
                """
                INSERT OR REPLACE INTO cache_rotas
                    (paradas, faixa_horario, dados, criado_em)
                VALUES (?, ?, ?, ?)
                """,
                (chave, faixa, _rota_para_json(rota), self._agora_iso()),
            )

        return rota

    def limpar(self) -> None:
        """Remove todas as consultas guardadas no cache."""

        self._garantir_banco()

        with conectar() as conexao:
            conexao.execute("DELETE FROM cache_matriz_rotas")
            conexao.execute("DELETE FROM cache_rotas")

    def _consultar_pares(
        self,
        faltantes: list[tuple[str, str]],
        origens_por_chave: dict[str, Coordenada],
        destinos_por_chave: dict[str, Coordenada],
        partida_em: datetime | None,
    ) -> dict[tuple[str, str], ElementoMatriz]:
        """Consulta o servico real apenas com os pontos necessarios."""

        chaves_origem = list(dict.fromkeys(o for o, _ in faltantes))
        chaves_destino = list(dict.fromkeys(d for _, d in faltantes))

        submatriz = self._servico.calcular_matriz(
            [origens_por_chave[chave] for chave in chaves_origem],
            [destinos_por_chave[chave] for chave in chaves_destino],
            partida_em=partida_em,
        )
        self.consultas_externas += 1

        return {
            (chaves_origem[i], chaves_destino[j]): elemento
            for (i, j), elemento in submatriz.elementos.items()
        }

    def _buscar_pares(
        self,
        origens: set[str],
        destinos: set[str],
        faixa: str,
    ) -> dict[tuple[str, str], ElementoMatriz]:
        """Le do cache os pares ja consultados nesta faixa."""

        self._garantir_banco()

        marcadores_origem = ", ".join("?" * len(origens))
        marcadores_destino = ", ".join("?" * len(destinos))

        with conectar() as conexao:
            registros = conexao.execute(
                f"""
                SELECT origem, destino, rota_existe, distancia_m,
                       duracao_s, duracao_sem_transito_s
                FROM cache_matriz_rotas
                WHERE faixa_horario = ?
                  AND origem IN ({marcadores_origem})
                  AND destino IN ({marcadores_destino})
                """,
                (faixa, *origens, *destinos),
            ).fetchall()

        return {
            (registro["origem"], registro["destino"]): ElementoMatriz(
                origem_indice=0,
                destino_indice=0,
                rota_existe=bool(registro["rota_existe"]),
                distancia_m=registro["distancia_m"],
                duracao_s=registro["duracao_s"],
                duracao_sem_transito_s=registro["duracao_sem_transito_s"],
            )
            for registro in registros
        }

    def _salvar_pares(
        self,
        pares: dict[tuple[str, str], ElementoMatriz],
        faixa: str,
    ) -> None:
        """Guarda os pares consultados para reaproveitamento."""

        agora = self._agora_iso()

        with conectar() as conexao:
            conexao.executemany(
                """
                INSERT OR REPLACE INTO cache_matriz_rotas (
                    origem, destino, faixa_horario, rota_existe,
                    distancia_m, duracao_s, duracao_sem_transito_s,
                    criado_em
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        origem,
                        destino,
                        faixa,
                        int(elemento.rota_existe),
                        elemento.distancia_m,
                        elemento.duracao_s,
                        elemento.duracao_sem_transito_s,
                        agora,
                    )
                    for (origem, destino), elemento in pares.items()
                ],
            )

    def _faixa_horario(self, partida_em: datetime | None) -> str:
        """Arredonda o horario de partida para o inicio da janela."""

        momento = (partida_em or self._relogio()).astimezone(FUSO_HORARIO)
        minutos_do_dia = momento.hour * 60 + momento.minute
        inicio = minutos_do_dia - minutos_do_dia % self._janela_min

        return momento.replace(
            hour=inicio // 60,
            minute=inicio % 60,
            second=0,
            microsecond=0,
        ).isoformat()

    def _agora_iso(self) -> str:
        return self._relogio().astimezone(timezone.utc).isoformat()

    def _garantir_banco(self) -> None:
        """Cria as tabelas no primeiro uso, e nao na construcao."""

        if not self._banco_pronto:
            inicializar_banco()
            self._banco_pronto = True


def _chave(ponto: Coordenada) -> str:
    """Identifica uma coordenada com precisao de cerca de 1 metro."""

    return (
        f"{ponto.latitude:.{CASAS_DECIMAIS_CHAVE}f},"
        f"{ponto.longitude:.{CASAS_DECIMAIS_CHAVE}f}"
    )


def _rota_para_json(rota: RotaCalculada) -> str:
    return json.dumps(
        {
            "distancia_m": rota.distancia_m,
            "duracao_s": rota.duracao_s,
            "duracao_sem_transito_s": rota.duracao_sem_transito_s,
            "polyline_codificada": rota.polyline_codificada,
            "trechos": [
                {
                    "distancia_m": trecho.distancia_m,
                    "duracao_s": trecho.duracao_s,
                    "duracao_sem_transito_s": trecho.duracao_sem_transito_s,
                }
                for trecho in rota.trechos
            ],
        }
    )


def _rota_de_json(dados: str) -> RotaCalculada:
    valores = json.loads(dados)

    return RotaCalculada(
        distancia_m=valores["distancia_m"],
        duracao_s=valores["duracao_s"],
        duracao_sem_transito_s=valores["duracao_sem_transito_s"],
        polyline_codificada=valores["polyline_codificada"],
        trechos=[TrechoRota(**trecho) for trecho in valores["trechos"]],
    )
