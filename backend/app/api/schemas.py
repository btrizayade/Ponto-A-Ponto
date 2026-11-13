from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models import CategoriaProduto, ModalidadeEntrega, StatusPedido
from app.domain.simulation import EstadoExecucao, TipoEvento


Provedor = Literal["simulado", "google"]
VelocidadeSimulacao = Literal[5, 15, 30, 60]
Estrategia = Literal[
    "insercao_mais_barata",
    "ordem_da_fila",
    "equidade_sla",
]
SituacaoViagem = Literal["planejada", "em_andamento", "concluida", "cancelada"]
SituacaoEntregador = Literal["no_centro", "em_viagem"]

MAX_ENTREGADORES = 20


# Configuracao e cenarios


class Ponto(BaseModel):
    latitude: float
    longitude: float


class Centro(Ponto):
    nome: str


class BairroResposta(Ponto):
    id: int
    nome: str


class ProvedorDisponivel(BaseModel):
    nome: Provedor
    disponivel: bool


class Expediente(BaseModel):
    inicio: str
    fim: str


class Configuracao(BaseModel):
    """Valores padrao e opcoes para criar uma simulacao."""

    provedor_padrao: str
    provedores: list[ProvedorDisponivel]
    estrategia_padrao: Estrategia
    estrategias: list[Estrategia]
    categorias_produto: list[CategoriaProduto]
    modalidades_entrega: list[ModalidadeEntrega]
    quantidade_entregadores_padrao: int
    max_entregadores: int
    centro: Centro
    expediente: Expediente


class CenarioResposta(BaseModel):
    id: int
    codigo: str
    nome: str
    descricao: str
    quantidade_pedidos: int


class PedidoResposta(BaseModel):
    codigo: str
    bairro: str
    latitude: float
    longitude: float
    categoria_produto: CategoriaProduto
    cliente_clube: bool
    entrega_rapida: bool
    sla_dias_uteis: int
    criado_em: datetime
    prazo_entrega_em: datetime | None
    peso_kg: float
    volume_l: float
    tempo_servico_min: int


class NovoPedido(BaseModel):
    """Campos escolhidos pelo usuario para cadastrar um pedido."""

    cenario_id: int = Field(gt=0)
    bairro_id: int = Field(gt=0)
    categoria_produto: CategoriaProduto
    modalidade: ModalidadeEntrega


class PedidoCriado(PedidoResposta):
    """Pedido persistido, com identificador e prioridade inicial."""

    id: int
    prioridade_inicial: int


# Criacao e controle


class NovaSimulacao(BaseModel):
    """
    Dados para criar uma simulacao.

    Um inicio sem fuso horario e interpretado no horario de Salvador.
    Os campos omitidos usam a configuracao do backend/.env.
    """

    cenario_id: int
    inicio: datetime
    quantidade_entregadores: int | None = Field(
        default=None, ge=1, le=MAX_ENTREGADORES
    )
    estrategia: Estrategia | None = None
    provedor: Provedor | None = None
    segundos_reais_por_hora_simulada: VelocidadeSimulacao = 15


class Avanco(BaseModel):
    """Avanco do relogio: informe minutos ou um horario (ate)."""

    minutos: float | None = Field(default=None, ge=0, le=24 * 60)
    ate: datetime | None = None

    @model_validator(mode="after")
    def _um_dos_dois(self) -> "Avanco":
        if (self.minutos is None) == (self.ate is None):
            raise ValueError("Informe minutos ou ate, e apenas um deles.")

        return self


# Estado da simulacao


class EventoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequencia: int
    instante: datetime
    tipo: TipoEvento
    pedido_codigo: str | None
    entregador_codigo: str | None
    viagem_numero: int | None
    status_anterior: StatusPedido | None
    status_novo: StatusPedido | None
    atraso_min: float | None
    distancia_m: int | None
    detalhe: str


class PedidoSimulacao(PedidoResposta):
    status: StatusPedido
    posicao_fila: int | None = Field(
        description="Posicao na fila usada no planejamento (1 = primeiro)."
    )
    prioridade: int | None = Field(
        description="Pontuacao de prioridade no inicio da simulacao."
    )
    entregador_codigo: str | None
    viagem_numero: int | None
    previsao_entrega_em: datetime | None
    entregue_em: datetime | None
    atualizado_em: datetime | None = Field(
        default=None,
        description="Instante do evento mais recente registrado para o pedido.",
    )
    atraso_min: float | None
    observacao: str = Field(description="Detalhe do ultimo evento do pedido.")


class EntregadorSimulacao(BaseModel):
    codigo: str
    situacao: SituacaoEntregador
    viagem_atual: int | None
    retorno_previsto_em: datetime | None
    proxima_partida_em: datetime | None
    viagens_planejadas: int
    viagens_concluidas: int
    viagens_canceladas: int
    entregas: int
    entregas_atrasadas: int
    distancia_percorrida_m: int


class IndicadoresBairro(BaseModel):
    bairro: str
    total_pedidos: int
    entregues: int
    entregues_com_sla_valido: int
    entregues_no_prazo: int
    entregues_atrasados: int
    pendentes: int
    pendentes_vencidos: int
    em_andamento: int
    em_risco_sla: int
    tempo_medio_entrega_min: float | None
    atraso_medio_min: float | None = Field(
        description="Media do atraso real entre as entregas atrasadas."
    )
    percentual_cumprimento_sla: float | None
    taxa_atraso: float | None
    atraso_medio_normalizado_sla: float | None = Field(
        description=(
            "Media do atraso real dividido pela duracao do SLA, incluindo "
            "zero para entregas no prazo."
        )
    )


class IndicadoresEquidadeTerritorial(BaseModel):
    melhor_bairro: str | None
    atraso_normalizado_melhor_bairro: float | None
    pior_bairro: str | None
    atraso_normalizado_pior_bairro: float | None
    diferenca_melhor_pior: float | None
    indice_equidade_territorial_real: float | None = Field(
        description=(
            "Indice da F09.3 calculado sobre atrasos reais de entregas "
            "concluidas, sem usar previsoes."
        )
    )
    bairros_com_amostras_validas: int


class Indicadores(BaseModel):
    total_pedidos: int
    por_status: dict[StatusPedido, int]
    entregues: int
    entregues_no_prazo: int
    entregues_atrasados: int
    atraso_medio_min: float | None = Field(
        description="Media entre as entregas atrasadas."
    )
    nao_atribuidos: int
    devolvidos_a_fila: int
    viagens_planejadas: int
    viagens_concluidas: int
    viagens_canceladas: int
    distancia_planejada_m: int
    distancia_percorrida_m: int
    por_bairro: list[IndicadoresBairro]
    equidade_territorial: IndicadoresEquidadeTerritorial


class EstadoSimulacao(BaseModel):
    id: int
    cenario_id: int
    provedor: str
    estrategia: Estrategia
    segundos_reais_por_hora_simulada: VelocidadeSimulacao = 15
    estado_execucao: EstadoExecucao
    erro_execucao: str | None = None
    inicio: datetime
    agora: datetime
    proximo_instante: datetime | None
    fim_expediente: datetime
    iniciada: bool
    concluida: bool
    centro: Centro
    indicadores: Indicadores
    fila: list[str] = Field(
        description="Pedidos na fila, na ordem de atendimento."
    )
    pedidos: list[PedidoSimulacao]
    entregadores: list[EntregadorSimulacao]


class RespostaControleExecucao(BaseModel):
    id: int
    estado_execucao: EstadoExecucao
    mensagem: str
    simulacao: EstadoSimulacao


class ResultadoEtapa(BaseModel):
    """Eventos processados em uma acao e o estado resultante."""

    eventos: list[EventoResposta]
    estado: EstadoSimulacao


class SimulacaoGravada(BaseModel):
    """Execucao registrada na auditoria."""

    id: int
    cenario_id: int | None
    criada_em: datetime
    inicio_simulado: datetime
    fim_simulado: datetime | None
    centro_nome: str
    estrategia: str
    segundos_reais_por_hora_simulada: VelocidadeSimulacao = 15
    entregadores: list[str]
    status: Literal["em_andamento", "concluida"]
    ativa: bool = Field(
        description="Se esta em memoria e pode ser controlada pela API."
    )


# Rotas para o mapa


class ParadaMapa(Ponto):
    ordem: int
    pedido_codigo: str
    bairro: str
    chegada_em: datetime
    saida_em: datetime
    status: StatusPedido
    atrasada: bool


class ViagemMapa(BaseModel):
    numero: int
    situacao: SituacaoViagem
    partida_em: datetime
    retorno_em: datetime
    distancia_m: int
    caminho: list[tuple[float, float]] = Field(
        description="Pontos [latitude, longitude] do trajeto, ida e volta."
    )
    paradas: list[ParadaMapa]


class RotaMapa(BaseModel):
    entregador_codigo: str
    viagens: list[ViagemMapa]


class RotasSimulacao(BaseModel):
    centro: Centro
    rotas: list[RotaMapa]
    nao_atribuidos: list[str]
