"""Serializacao imutavel de entradas e consultas de roteamento."""

import os
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.domain import aging, distribution, priority_scoring, sla, sla_risk
from app.domain.distribution import CentroDistribuicao, EstrategiaDistribuicao
from app.domain.models import (
    Bairro,
    Cenario,
    Entregador,
    Pedido,
    StatusPedido,
)
from app.domain.priority_scoring import calcular_prioridade
from app.domain.routing import (
    Coordenada,
    MatrizDistancias,
    RotaCalculada,
    ServicoRoteamento,
)
VERSAO_PARAMETROS = 1
VERSAO_SNAPSHOT_PEDIDOS = 2
VERSAO_REQUISICAO_ROTEAMENTO = 1
VERSAO_RESPOSTA_ROTEAMENTO = 1

_REVISAO_GIT_VALIDA = re.compile(r"^[0-9a-fA-F]{7,64}$")
_BUILD_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class FalhaPersistenciaAuditoriaExperimental(RuntimeError):
    """A execucao nao pode prosseguir sem estado experimental consistente."""


class FalhaPersistenciaAuditoriaRoteamento(
    FalhaPersistenciaAuditoriaExperimental
):
    """O roteamento nao pode ser consumido sem sua auditoria persistida."""


def serializar_snapshot_pedidos(
    cenario: Cenario,
    pedidos: Sequence[Pedido],
    inicio: datetime,
    *,
    pedidos_historicos: Sequence[Pedido] | None = None,
    metadados_temporais: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Registra os dados persistidos e os efetivamente usados pelo motor."""

    historicos = (
        pedidos_historicos if pedidos_historicos is not None else pedidos
    )
    historicos_por_chave = {_chave_pedido(pedido): pedido for pedido in historicos}
    chaves_efetivas = [_chave_pedido(pedido) for pedido in pedidos]
    if len(chaves_efetivas) != len(set(chaves_efetivas)):
        raise ValueError("O snapshot contém pedidos efetivos duplicados.")
    if pedidos_historicos is not None and (
        len(historicos_por_chave) != len(historicos)
        or set(historicos_por_chave) != set(chaves_efetivas)
    ):
        raise ValueError(
            "Os pedidos históricos e efetivos do snapshot não correspondem."
        )

    return {
        "versao": VERSAO_SNAPSHOT_PEDIDOS,
        "cenario": {
            "id": cenario.id,
            "codigo": cenario.codigo,
            "nome": cenario.nome,
            "descricao": cenario.descricao,
        },
        "temporalidade": dict(metadados_temporais or {}),
        "pedidos": [
            _serializar_pedido_snapshot(
                pedido,
                historicos_por_chave.get(_chave_pedido(pedido), pedido),
                inicio,
            )
            for pedido in pedidos
        ],
    }


def _chave_pedido(pedido: Pedido) -> tuple[int | None, str]:
    return pedido.id, pedido.codigo


def _serializar_pedido_snapshot(
    pedido: Pedido,
    historico: Pedido,
    inicio: datetime,
) -> dict[str, Any]:
    """Mantém as chaves v1 efetivas e adiciona a proveniência v2."""

    criado_efetivo = pedido.criado_em.isoformat()
    prazo_efetivo = (
        pedido.prazo_entrega_em.isoformat()
        if pedido.prazo_entrega_em is not None
        else None
    )
    criado_historico = historico.criado_em.isoformat()
    prazo_historico = (
        historico.prazo_entrega_em.isoformat()
        if historico.prazo_entrega_em is not None
        else None
    )
    return {
        "id": pedido.id,
        "codigo": pedido.codigo,
        "bairro": _serializar_bairro(pedido.bairro),
        "categoria_produto": pedido.categoria_produto.value,
        "cliente_clube": pedido.cliente_clube,
        "entrega_rapida": pedido.entrega_rapida,
        "sla_dias_uteis": pedido.sla_dias_uteis,
        # As chaves originais do snapshot representam os dados efetivos.
        "criado_em": criado_efetivo,
        "prazo_entrega_em": prazo_efetivo,
        "datas_historicas": {
            "criado_em": criado_historico,
            "prazo_entrega_em": prazo_historico,
        },
        "datas_efetivas": {
            "criado_em": criado_efetivo,
            "prazo_entrega_em": prazo_efetivo,
        },
        "peso_kg": pedido.peso_kg,
        "volume_l": pedido.volume_l,
        "tempo_servico_min": pedido.tempo_servico_min,
        "status_inicial_motor": StatusPedido.PENDENTE.value,
        "prioridade_inicial": calcular_prioridade(pedido, agora=inicio),
        "origem": pedido.origem.value,
        "ativo": pedido.ativo,
    }


def montar_parametros_efetivos(
    *,
    inicio: datetime,
    centro: CentroDistribuicao,
    entregadores: Sequence[Entregador],
    estrategia: EstrategiaDistribuicao,
    servico: ServicoRoteamento,
    segundos_reais_por_hora_simulada: int,
    disponibilidade: Mapping[str, datetime] | None,
    intervalo_execucao_automatica_s: float | None = None,
) -> dict[str, Any]:
    """Captura opcoes e constantes efetivamente ligadas ao motor atual."""

    identificador_build = _identificador_build()
    parametros_servico = servico.parametros_auditoria()

    return {
        "versao": VERSAO_PARAMETROS,
        "aplicacao": identificador_build,
        "inicio": {
            "instante": inicio.isoformat(),
            "fuso_horario": sla.FUSO_HORARIO.key,
            "expediente": {
                "inicio": sla.HORA_INICIO.isoformat(),
                "fim": sla.HORA_FIM.isoformat(),
                "horas_por_dia_util": sla.HORAS_POR_DIA_UTIL,
            },
        },
        "roteamento": parametros_servico,
        "distribuicao": {
            "estrategia": {
                "DistribuicaoInsercaoMaisBarata": "insercao_mais_barata",
                "DistribuicaoOrdemDaFila": "ordem_da_fila",
                "DistribuicaoEquidadeSLA": "equidade_sla",
            }.get(
                type(estrategia).__name__,
                type(estrategia).__name__,
            ),
            "classe_estrategia": type(estrategia).__name__,
            "centro": {
                "nome": centro.nome,
                "latitude": centro.coordenada.latitude,
                "longitude": centro.coordenada.longitude,
            },
            "entregadores": [
                {
                    "codigo": entregador.codigo,
                    "max_paradas_por_viagem": (
                        entregador.max_paradas_por_viagem
                    ),
                    "capacidade_peso_kg": entregador.capacidade_peso_kg,
                    "capacidade_volume_l": entregador.capacidade_volume_l,
                }
                for entregador in entregadores
            ],
            "pesos_otimizacao": {
                "penalidade_atraso_min": distribution.PENALIDADE_ATRASO_MIN,
                "peso_minuto_atraso": distribution.PESO_MINUTO_ATRASO,
                "peso_prioridade": distribution.PESO_PRIORIDADE,
                "fator_peso_prioridade": distribution.FATOR_PESO_PRIORIDADE,
                "penalidade_inversao_min": (
                    distribution.PENALIDADE_INVERSAO_MIN
                ),
                "peso_termino": distribution.PESO_TERMINO,
                "peso_equidade_por_sla": distribution.PESO_EQUIDADE_POR_SLA,
                "peso_pior_bairro": distribution.PESO_PIOR_BAIRRO,
                "peso_disparidade_bairro": (
                    distribution.PESO_DISPARIDADE_BAIRRO
                ),
                "max_rodadas_melhoria": distribution.MAX_RODADAS_MELHORIA,
                "tolerancia_melhoria": distribution.TOLERANCIA_MELHORIA,
            },
        },
        "prioridade": {
            "bonus_cliente_clube": priority_scoring.BONUS_CLIENTE_CLUBE,
            "bonus_entrega_rapida": priority_scoring.BONUS_ENTREGA_RAPIDA,
            "bonus_produto_prioritario": (
                priority_scoring.BONUS_PRODUTO_PRIORITARIO
            ),
            "bonus_cliente_comum_sla_longo": (
                priority_scoring.BONUS_CLIENTE_COMUM_SLA_LONGO
            ),
            "aging": {
                "intervalo_horas": aging.INTERVALO_AGING_HORAS,
                "pontos_por_intervalo": aging.PONTOS_POR_INTERVALO,
                "pontuacao_maxima": aging.PONTUACAO_AGING_MAXIMA,
            },
            "risco_sla": {
                "pontos_atrasado": sla_risk.PONTOS_SLA_ATRASADO,
                "pontos_ate_30_min": sla_risk.PONTOS_SLA_ATE_30_MIN,
                "pontos_ate_1_hora": sla_risk.PONTOS_SLA_ATE_1_HORA,
                "pontos_ate_2_horas": sla_risk.PONTOS_SLA_ATE_2_HORAS,
                "pontos_ate_4_horas": sla_risk.PONTOS_SLA_ATE_4_HORAS,
            },
        },
        "relogio": {
            "segundos_reais_por_hora_simulada": (
                segundos_reais_por_hora_simulada
            ),
            "intervalo_execucao_automatica_s": (
                intervalo_execucao_automatica_s
            ),
        },
        "disponibilidade_entregadores": (
            {
                codigo: instante.isoformat()
                for codigo, instante in sorted(disponibilidade.items())
            }
            if disponibilidade is not None
            else None
        ),
    }


class ServicoRoteamentoAuditavel(ServicoRoteamento):
    """Persiste cada resultado antes de entregá-lo ao motor de simulação."""

    def __init__(
        self,
        servico: ServicoRoteamento,
        provedor: str,
    ) -> None:
        self._servico = servico
        self._provedor = provedor
        self._registrar: Callable[..., None] | None = None
        self._trava = Lock()

    @property
    def perfil_consulta(self) -> str:
        return self._servico.perfil_consulta

    def parametros_auditoria(self) -> dict[str, object]:
        parametros = self._servico.parametros_auditoria()
        provedor_real = parametros.get("provedor")
        return {
            **parametros,
            "provedor": (
                self._provedor
                if provedor_real in (None, "desconhecido")
                else provedor_real
            ),
        }

    def conectar_auditoria(self, registrar: Callable[..., None]) -> None:
        """Liga o gravador depois que a linha da simulação recebe seu ID."""

        self._registrar = registrar

    def fechar(self) -> None:
        self._servico.fechar()

    def calcular_matriz(
        self,
        origens: Sequence[Coordenada],
        destinos: Sequence[Coordenada],
        partida_em: datetime | None = None,
    ) -> MatrizDistancias:
        with self._trava:
            consultada_em = datetime.now(timezone.utc)
            matriz = self._servico.calcular_matriz(
                origens, destinos, partida_em=partida_em
            )
            requisicao = {
                "versao": VERSAO_REQUISICAO_ROTEAMENTO,
                "origens": [_serializar_coordenada(ponto) for ponto in origens],
                "destinos": [
                    _serializar_coordenada(ponto) for ponto in destinos
                ],
                "partida_em": _instante_iso(partida_em),
            }
            resposta = {
                "elementos": [
                    {
                        "origem_indice": elemento.origem_indice,
                        "destino_indice": elemento.destino_indice,
                        "rota_existe": elemento.rota_existe,
                        "distancia_m": elemento.distancia_m,
                        "duracao_s": elemento.duracao_s,
                        "duracao_sem_transito_s": (
                            elemento.duracao_sem_transito_s
                        ),
                        "fator_transito": elemento.fator_transito,
                    }
                    for _, elemento in sorted(matriz.elementos.items())
                ]
            }
            self._persistir(
                "matriz", partida_em, consultada_em, requisicao, resposta
            )
            return matriz

    def calcular_rota(
        self,
        origem: Coordenada,
        destino: Coordenada,
        paradas: Sequence[Coordenada] = (),
        partida_em: datetime | None = None,
    ) -> RotaCalculada:
        with self._trava:
            consultada_em = datetime.now(timezone.utc)
            rota = self._servico.calcular_rota(
                origem,
                destino,
                paradas=paradas,
                partida_em=partida_em,
            )
            requisicao = {
                "versao": VERSAO_REQUISICAO_ROTEAMENTO,
                "origem": _serializar_coordenada(origem),
                "destino": _serializar_coordenada(destino),
                "paradas": [_serializar_coordenada(ponto) for ponto in paradas],
                "partida_em": _instante_iso(partida_em),
            }
            resposta = {
                "distancia_m": rota.distancia_m,
                "duracao_s": rota.duracao_s,
                "duracao_sem_transito_s": rota.duracao_sem_transito_s,
                "polyline_codificada": rota.polyline_codificada,
                "trechos": [
                    {
                        "distancia_m": trecho.distancia_m,
                        "duracao_s": trecho.duracao_s,
                        "duracao_sem_transito_s": (
                            trecho.duracao_sem_transito_s
                        ),
                    }
                    for trecho in rota.trechos
                ],
            }
            self._persistir(
                "rota", partida_em, consultada_em, requisicao, resposta
            )
            return rota

    def _persistir(
        self,
        tipo: str,
        partida_em: datetime | None,
        consultada_em: datetime,
        requisicao: dict[str, Any],
        resposta: dict[str, Any],
    ) -> None:
        if self._registrar is None:
            raise FalhaPersistenciaAuditoriaRoteamento(
                "A auditoria experimental não foi ligada à simulação; "
                "o resultado de roteamento não foi entregue ao motor."
            )

        try:
            self._registrar(
                tipo=tipo,
                provedor=self._provedor,
                perfil=str(self.parametros_auditoria()["perfil"]),
                origem_resultado=getattr(
                    self._servico,
                    "ultima_origem_consulta",
                    "provedor",
                ),
                partida_em=partida_em,
                consultada_em=consultada_em,
                requisicao=requisicao,
                resposta=resposta,
            )
        except Exception as erro:
            raise FalhaPersistenciaAuditoriaRoteamento(
                "Não foi possível persistir a auditoria do resultado de "
                f"roteamento ({tipo}); o motor interrompeu o planejamento."
            ) from erro


def _serializar_bairro(bairro: Bairro) -> dict[str, Any]:
    return {
        "id": bairro.id,
        "nome": bairro.nome,
        "latitude": bairro.latitude,
        "longitude": bairro.longitude,
    }


def _serializar_coordenada(coordenada: Coordenada) -> dict[str, float]:
    return {
        "latitude": coordenada.latitude,
        "longitude": coordenada.longitude,
    }


def _instante_iso(instante: datetime | None) -> str | None:
    return instante.isoformat() if instante is not None else None


def _identificador_build() -> dict[str, str | None]:
    revisao = os.environ.get("PONTO_A_PONTO_GIT_REVISION", "").strip()
    build = os.environ.get("PONTO_A_PONTO_BUILD_ID", "").strip()
    return {
        "revisao_git": (
            revisao.lower() if _REVISAO_GIT_VALIDA.fullmatch(revisao) else None
        ),
        "build_id": (
            build if _BUILD_ID_VALIDO.fullmatch(build) else None
        ),
    }
