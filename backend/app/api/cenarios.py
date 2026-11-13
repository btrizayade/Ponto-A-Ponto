from fastapi import APIRouter, HTTPException

from app.api.estado import centro_resposta, pedido_resposta
from app.api.schemas import (
    MAX_ENTREGADORES,
    CenarioResposta,
    Configuracao,
    Expediente,
    PedidoResposta,
    ProvedorDisponivel,
)
from app.api.simulacoes import ESTRATEGIA_PADRAO, ESTRATEGIAS
from app.domain.sla import HORA_FIM, HORA_INICIO
from app.domain.models import CategoriaProduto, ModalidadeEntrega
from app.infrastructure.cenario_repository import listar_cenarios, obter_cenario
from app.infrastructure.distribution_config import (
    criar_entregadores_padrao,
    obter_centro_distribuicao,
)
from app.infrastructure.pedido_repository import listar_pedidos_por_cenario
from app.infrastructure.routing_factory import (
    PROVEDOR_GOOGLE,
    PROVEDOR_SIMULADO,
    google_disponivel,
    provedor_padrao,
)


router = APIRouter(prefix="/api", tags=["cenarios"])


@router.get("/configuracao", response_model=Configuracao)
def obter_configuracao():
    """Valores padrao e opcoes para o formulario de nova simulacao."""

    return Configuracao(
        provedor_padrao=provedor_padrao(),
        provedores=[
            ProvedorDisponivel(
                nome=PROVEDOR_GOOGLE, disponivel=google_disponivel()
            ),
            ProvedorDisponivel(nome=PROVEDOR_SIMULADO, disponivel=True),
        ],
        estrategia_padrao=ESTRATEGIA_PADRAO,
        estrategias=list(ESTRATEGIAS),
        categorias_produto=list(CategoriaProduto),
        modalidades_entrega=list(ModalidadeEntrega),
        quantidade_entregadores_padrao=len(criar_entregadores_padrao()),
        max_entregadores=MAX_ENTREGADORES,
        centro=centro_resposta(obter_centro_distribuicao()),
        expediente=Expediente(
            inicio=f"{HORA_INICIO:%H:%M}", fim=f"{HORA_FIM:%H:%M}"
        ),
    )


@router.get("/cenarios", response_model=list[CenarioResposta])
def listar():
    return [
        CenarioResposta(
            id=cenario.id,
            codigo=cenario.codigo,
            nome=cenario.nome,
            descricao=cenario.descricao,
            quantidade_pedidos=len(listar_pedidos_por_cenario(cenario.id)),
        )
        for cenario in listar_cenarios()
    ]


@router.get(
    "/cenarios/{cenario_id}/pedidos",
    response_model=list[PedidoResposta],
)
def listar_pedidos(cenario_id: int):
    if obter_cenario(cenario_id) is None:
        raise HTTPException(404, f"Cenario {cenario_id} nao encontrado.")

    return [
        pedido_resposta(pedido)
        for pedido in listar_pedidos_por_cenario(cenario_id)
    ]
