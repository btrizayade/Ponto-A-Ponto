
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

class CategoriaProduto(str, Enum):
    """Categorias de produtos aceitas pelo sistema."""

    ALIMENTO = "alimento"
    MEDICAMENTO = "medicamento"
    ROUPA = "roupa"
    ELETRONICO = "eletronico"
    OUTRO = "outro"


class StatusPedido(str, Enum):
    """Estados possíveis de um pedido durante o atendimento."""

    PENDENTE = "pendente"
    NA_FILA = "na_fila"
    ATRIBUIDO = "atribuido"
    EM_ROTA = "em_rota"
    ENTREGUE = "entregue"


@dataclass
class Bairro:
    """Representa uma zona de entrega com coordenadas de referência."""

    nome: str
    latitude: float
    longitude: float
    id: int | None = None

    def __post_init__(self) -> None:
        """Valida os dados geográficos do bairro."""

        if not self.nome.strip():
            raise ValueError("O nome do bairro não pode ser vazio.")

        if not -90 <= self.latitude <= 90:
            raise ValueError("A latitude deve estar entre -90 e 90.")

        if not -180 <= self.longitude <= 180:
            raise ValueError("A longitude deve estar entre -180 e 180.")


@dataclass
class Cenario:
    """Representa um cenário de simulação."""

    codigo: str
    nome: str
    descricao: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        """Valida os dados essenciais do cenário."""

        if not self.codigo.strip():
            raise ValueError("O código do cenário não pode ser vazio.")

        if not self.nome.strip():
            raise ValueError("O nome do cenário não pode ser vazio.")


@dataclass
class Pedido:
    """Representa um pedido destinado a um bairro."""

    codigo: str
    bairro: Bairro
    categoria_produto: CategoriaProduto
    cliente_clube: bool
    entrega_rapida: bool
    sla_dias_uteis: int
    criado_em: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    prazo_entrega_em: datetime | None = None
    peso_kg: float = 0.0
    volume_l: float = 0.0
    tempo_servico_min: int = 5
    id: int | None = None

    def __post_init__(self) -> None:
        """Valida os dados essenciais do pedido."""

        if not self.codigo.strip():
            raise ValueError("O codigo do pedido nao pode ser vazio.")

        if not isinstance(self.bairro, Bairro):
            raise TypeError("O pedido deve referenciar um objeto Bairro.")

        if self.sla_dias_uteis <= 0:
            raise ValueError("O SLA deve ser maior que zero.")

        if self.peso_kg < 0 or self.volume_l < 0:
            raise ValueError("Peso e volume nao podem ser negativos.")

        if self.tempo_servico_min < 0:
            raise ValueError(
                "O tempo de servico nao pode ser negativo."
            )

        if (
            self.criado_em.tzinfo is None
            or self.criado_em.utcoffset() is None
        ):
            raise ValueError(
                "A data de criacao deve ter fuso horario."
            )

        if self.prazo_entrega_em is not None:
            if (
                self.prazo_entrega_em.tzinfo is None
                or self.prazo_entrega_em.utcoffset() is None
            ):
                raise ValueError(
                    "O prazo de entrega deve ter fuso horario."
                )

            if self.prazo_entrega_em <= self.criado_em:
                raise ValueError(
                    "O prazo de entrega deve ser posterior a criacao."
                )

    @property
    def produto_prioritario(self) -> bool:
        """Indica se a categoria do produto e prioritaria."""

        return self.categoria_produto in {
            CategoriaProduto.ALIMENTO,
            CategoriaProduto.MEDICAMENTO,
        }


@dataclass
class Entregador:
    """Representa um caminhão disponível para as entregas."""

    codigo: str
    id: int | None = None

    def __post_init__(self) -> None:
        """Valida os dados essenciais do entregador."""

        if not self.codigo.strip():
            raise ValueError("O código do entregador não pode ser vazio.")
