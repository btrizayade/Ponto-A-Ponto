from datetime import datetime, timedelta, timezone

import pytest

from app.domain.routing import Coordenada, ErroRoteamento
from app.infrastructure import database
from app.infrastructure.cache_roteamento import ServicoRoteamentoComCache
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


AGORA = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)

CENTRO_DISTRIBUICAO = Coordenada(-12.971, -38.501)
BARRA = Coordenada(-13.006, -38.528)
PITUBA = Coordenada(-12.999, -38.460)
ITAPUA = Coordenada(-12.940, -38.358)


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    """Prepara um banco isolado para cada teste."""

    diretorio = tmp_path / "data"

    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")


class ServicoContador(ServicoRoteamentoSimulado):
    """Provedor simulado que registra cada consulta recebida."""

    def __init__(self) -> None:
        super().__init__(relogio=lambda: AGORA)
        self.matrizes: list[tuple[list, list]] = []
        self.rotas: list[list] = []
        self.falhar = False

    def calcular_matriz(self, origens, destinos, partida_em=None):
        if self.falhar:
            raise ErroRoteamento("API indisponivel.")

        self.matrizes.append((list(origens), list(destinos)))
        return super().calcular_matriz(origens, destinos, partida_em)

    def calcular_rota(self, origem, destino, paradas=(), partida_em=None):
        self.rotas.append([origem, *paradas, destino])
        return super().calcular_rota(origem, destino, paradas, partida_em)


def criar_cache(servico, janela_min=15):
    return ServicoRoteamentoComCache(
        servico,
        janela_min=janela_min,
        relogio=lambda: AGORA,
    )


# Matriz


def test_matriz_repetida_nao_consulta_de_novo(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico)

    primeira = cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA, PITUBA])
    segunda = cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA, PITUBA])

    assert len(servico.matrizes) == 1
    assert cache.pares_do_cache == 2
    assert cache.pares_consultados == 2
    assert segunda.elementos == primeira.elementos


def test_cache_persiste_entre_instancias(banco_temporario):
    servico = ServicoContador()

    criar_cache(servico).calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA])
    criar_cache(servico).calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA])

    assert len(servico.matrizes) == 1


def test_so_os_pares_novos_sao_consultados(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico)

    cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA, PITUBA])
    matriz = cache.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA, PITUBA, ITAPUA]
    )

    assert servico.matrizes[1] == ([CENTRO_DISTRIBUICAO], [ITAPUA])
    assert matriz.esta_completa()
    assert matriz.obter(0, 2).destino_indice == 2


def elementos_pedidos(servico) -> int:
    return sum(len(o) * len(d) for o, d in servico.matrizes)


def test_cache_parcial_com_varias_origens_consulta_so_os_ausentes(
    banco_temporario,
):
    servico = ServicoContador()
    cache = criar_cache(servico)
    o1, o2, d1, d2 = CENTRO_DISTRIBUICAO, BARRA, PITUBA, ITAPUA

    # O1-D1 e O2-D2 ja estao no cache.
    cache.calcular_matriz([o1], [d1])
    cache.calcular_matriz([o2], [d2])
    servico.matrizes.clear()

    matriz = cache.calcular_matriz([o1, o2], [d1, d2])

    # Somente O1-D2 e O2-D1 sao consultados.
    assert elementos_pedidos(servico) == 2
    assert sorted(servico.matrizes, key=str) == sorted(
        [([o1], [d2]), ([o2], [d1])], key=str
    )
    assert matriz.esta_completa()

    direta = ServicoRoteamentoSimulado(relogio=lambda: AGORA)
    esperada = direta.calcular_matriz([o1, o2], [d1, d2])
    for par, elemento in esperada.elementos.items():
        assert matriz.obter(*par).distancia_m == elemento.distancia_m


def test_novo_pedido_em_matriz_quadrada_consulta_linha_e_coluna(
    banco_temporario,
):
    servico = ServicoContador()
    cache = criar_cache(servico)
    pontos = [CENTRO_DISTRIBUICAO, BARRA, PITUBA, ITAPUA]
    novo = Coordenada(-12.986, -38.482)

    cache.calcular_matriz(pontos, pontos)
    servico.matrizes.clear()

    matriz = cache.calcular_matriz([*pontos, novo], [*pontos, novo])

    # 4 origens antigas ate o novo ponto e o novo ate os 5 pontos.
    assert elementos_pedidos(servico) == 2 * len(pontos) + 1
    assert len(servico.matrizes) == 2
    # Os 16 pares antigos vieram do cache na segunda consulta.
    assert cache.pares_do_cache == 16
    assert matriz.esta_completa()


def test_coordenadas_repetidas_viram_um_ponto(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico)

    # Dois pedidos no mesmo bairro.
    matriz = cache.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA, BARRA, PITUBA]
    )

    assert servico.matrizes[0] == ([CENTRO_DISTRIBUICAO], [BARRA, PITUBA])
    assert matriz.esta_completa()
    assert matriz.distancia_m(0, 0) == matriz.distancia_m(0, 1)


def test_cache_respeita_a_faixa_de_horario(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico, janela_min=15)
    partida = datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc)

    cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA], partida)
    cache.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA], partida + timedelta(minutes=14)
    )
    cache.calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA], partida + timedelta(minutes=15)
    )

    assert len(servico.matrizes) == 2


def test_falha_da_api_nao_grava_cache(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico)
    servico.falhar = True

    with pytest.raises(ErroRoteamento):
        cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA])

    servico.falhar = False
    cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA])

    assert len(servico.matrizes) == 1


def test_limpar_cache(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico)

    cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA])
    cache.limpar()
    cache.calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA])

    assert len(servico.matrizes) == 2


# Rotas


def test_rota_repetida_vem_do_cache(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico)

    primeira = cache.calcular_rota(
        CENTRO_DISTRIBUICAO, CENTRO_DISTRIBUICAO, paradas=[BARRA, PITUBA]
    )
    segunda = cache.calcular_rota(
        CENTRO_DISTRIBUICAO, CENTRO_DISTRIBUICAO, paradas=[BARRA, PITUBA]
    )

    assert len(servico.rotas) == 1
    assert cache.rotas_do_cache == 1
    assert segunda == primeira
    assert segunda.pontos == primeira.pontos


def test_ordem_diferente_das_paradas_e_outra_rota(banco_temporario):
    servico = ServicoContador()
    cache = criar_cache(servico)

    cache.calcular_rota(
        CENTRO_DISTRIBUICAO, CENTRO_DISTRIBUICAO, paradas=[BARRA, PITUBA]
    )
    cache.calcular_rota(
        CENTRO_DISTRIBUICAO, CENTRO_DISTRIBUICAO, paradas=[PITUBA, BARRA]
    )

    assert len(servico.rotas) == 2


# Perfil e ciclo de vida


def test_perfis_diferentes_nao_compartilham_cache(banco_temporario):
    normal = ServicoContador()
    intenso = ServicoContador()
    intenso._fator_transito = 2.0

    criar_cache(normal).calcular_matriz([CENTRO_DISTRIBUICAO], [BARRA])
    matriz = criar_cache(intenso).calcular_matriz(
        [CENTRO_DISTRIBUICAO], [BARRA]
    )

    assert len(intenso.matrizes) == 1
    assert matriz.obter(0, 0).fator_transito == pytest.approx(2.0)


def test_fechar_repassa_para_o_servico_envolvido():
    servico = ServicoContador()
    fechados = []
    servico.fechar = lambda: fechados.append(True)

    with criar_cache(servico):
        pass

    assert fechados == [True]


# Configuracao


@pytest.mark.parametrize("janela", [0, 1441])
def test_janela_invalida(janela):
    with pytest.raises(ValueError):
        ServicoRoteamentoComCache(ServicoContador(), janela_min=janela)


def test_janela_lida_do_ambiente(monkeypatch):
    monkeypatch.setenv("CACHE_ROTAS_JANELA_MIN", "abc")

    with pytest.raises(ValueError):
        ServicoRoteamentoComCache.do_ambiente(ServicoContador())
