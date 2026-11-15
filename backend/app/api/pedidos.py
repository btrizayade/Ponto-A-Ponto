from fastapi import APIRouter, HTTPException

from app.api.estado import pedido_resposta
from app.api.schemas import BairroResposta, NovoPedido, PedidoCriado
from app.domain.priority_scoring import calcular_prioridade
from app.domain.models import OrigemPedido
from app.infrastructure.bairro_repository import listar_bairros
from app.infrastructure.cenario_repository import obter_cenario
from app.infrastructure.pedido_factory import criar_pedido_do_formulario
from app.infrastructure.pedido_repository import obter_ou_criar_pedido


router = APIRouter(prefix="/api", tags=["pedidos"])


@router.get("/bairros", response_model=list[BairroResposta])
def listar():
    """Bairros existentes para selecao no formulario de pedidos."""

    return listar_bairros()


@router.post("/pedidos", response_model=PedidoCriado, status_code=201)
def criar(dados: NovoPedido):
    """Cadastra um pedido em um unico cenario, gerando dados operacionais."""

    cenario = obter_cenario(dados.cenario_id)
    if cenario is None:
        raise HTTPException(404, f"Cenario {dados.cenario_id} nao encontrado.")

    bairro = next(
        (item for item in listar_bairros() if item.id == dados.bairro_id),
        None,
    )
    if bairro is None:
        raise HTTPException(404, f"Bairro {dados.bairro_id} nao encontrado.")

    pedido = criar_pedido_do_formulario(
        bairro,
        dados.categoria_produto,
        dados.modalidade,
    )

    try:
        salvo = obter_ou_criar_pedido(
            pedido, cenario.id, origem=OrigemPedido.MANUAL
        )
    except ValueError as erro:
        raise HTTPException(400, str(erro)) from erro

    return PedidoCriado(
        **pedido_resposta(salvo).model_dump(),
        id=salvo.id,
        prioridade_inicial=calcular_prioridade(
            salvo,
            agora=salvo.criado_em,
        ),
    )
