# Arquitetura inicial

O sistema será dividido em frontend, backend, persistência e integração externa.

## Frontend

React e Vite serão responsáveis pela interface, pelos controles de simulação, pela visualização da fila e pela exibição do mapa e das rotas.

## Backend

Python e FastAPI exporão a API HTTP. A lógica de domínio será organizada com POO e separada das rotas HTTP.

## Persistência

SQLite armazenará os pedidos predefinidos, os dados dos entregadores, as simulações, as rotas e os eventos relevantes.

## Algoritmos

A fila de prioridade baseada em heap selecionará os pedidos para despacho. Um componente de distribuição decidirá qual entregador receberá cada pedido e qual sequência de paradas será utilizada.

## Integração geográfica

Um serviço de roteamento consultará a API de mapas para obter estimativas de deslocamento e geometrias dos trajetos. A lógica de negócio deverá permitir o uso de um provedor simulado em testes.

Implementação (F04):

- `app/domain/routing.py`: porta `ServicoRoteamento`, modelos `Coordenada`, `MatrizDistancias`, `RotaCalculada` e a função `estimar_tempo_entrega_min`, que alimenta o risco de SLA do motor de prioridade (F02).
- `app/domain/polyline.py`: codificação e decodificação de Encoded Polyline, usada na geometria das rotas.
- `app/infrastructure/google_routes.py`: adaptador da Google Routes API (`computeRouteMatrix` para a matriz de distâncias e `computeRoutes` para rota com paradas e geometria), considerando o trânsito (`TRAFFIC_AWARE`).
- `app/infrastructure/simulated_routing.py`: provedor offline e determinístico (distância haversine, velocidade média e fator de trânsito por horário ou fixo por cenário).
- `app/infrastructure/routing_factory.py`: escolhe o provedor pelas variáveis `PROVEDOR_MAPAS` e `GOOGLE_MAPS_API_KEY`.
- `app/infrastructure/cache_roteamento.py`: cache no SQLite (tabelas `cache_matriz_rotas` e `cache_rotas`) que reaproveita consultas iguais dentro da mesma faixa de horário e do mesmo perfil de consulta (provedor e preferência de roteamento). Na matriz, o cache é por par origem-destino e a consulta externa contém exclusivamente os pares ausentes: origens que precisam dos mesmos destinos são agrupadas em uma submatriz. Coordenadas repetidas viram um único ponto. Consultas atendidas pelo cache não consomem o limite diário.
- Os serviços de roteamento podem ser usados com `with` ou encerrados com `fechar()`, que libera o cliente HTTP da Google também quando ele está envolvido pelo cache.
- `app/infrastructure/controle_uso_api.py`: limite diário de consultas à Google, salvo no SQLite (tabela `uso_api_mapas`), que bloqueia novas chamadas ao atingir o teto.

Variáveis lidas de `backend/.env` (carregado por `app/config.py`, nunca commitado):

| Variável | Uso |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Chave da Google Routes API. |
| `PROVEDOR_MAPAS` | `google` ou `simulado`. Sem valor, usa `google` se houver chave. |
| `LIMITE_DIARIO_ELEMENTOS_MATRIZ` | Teto diário de elementos de matriz (padrão 150). |
| `LIMITE_DIARIO_ROTAS` | Teto diário de rotas (padrão 50). |
| `CACHE_ROTAS_JANELA_MIN` | Duração da faixa de horário do cache, em minutos (padrão 15). |
| `CENTRO_DISTRIBUICAO_NOME` | Nome do centro de distribuição (padrão `Comercio`). |
| `CENTRO_DISTRIBUICAO_LATITUDE` / `CENTRO_DISTRIBUICAO_LONGITUDE` | Coordenada do centro (padrão -12.971, -38.501). Devem ser definidas juntas. |
| `QUANTIDADE_ENTREGADORES` | Quantidade de caminhões criados por padrão (padrão 2). |

## Distribuição e montagem de rotas

Implementação (F05):

- `app/domain/distribution.py`: `DistribuidorPedidos` recebe os pedidos na ordem da fila de prioridade (F03), consulta uma única matriz de deslocamentos (F04) entre o centro de distribuição e os pedidos e aplica uma `EstrategiaDistribuicao`. O resultado é um `PlanoDistribuicao` com as viagens de cada entregador, os horários de chegada e saída de cada parada, as distâncias, os pedidos atrasados e os não atribuídos. `montar_rotas()` consulta a geometria de cada viagem.
- `DistribuicaoInsercaoMaisBarata` (padrão): insere cada pedido no entregador, viagem e posição de menor custo e depois realoca pedidos enquanto o custo diminuir. O custo soma a duração das viagens, o término da operação, penalidades por atraso de SLA e um peso que favorece entregar antes os pedidos mais prioritários.
- `DistribuicaoOrdemDaFila`: alterna os entregadores seguindo a ordem da fila, sem otimizar o trajeto. Serve como referência de comparação.
- `Entregador` (`app/domain/models.py`) passou a ter `max_paradas_por_viagem` (padrão 6), `capacidade_peso_kg` (500) e `capacidade_volume_l` (3000). Quando a carga não cabe, o caminhão volta ao centro e faz outra viagem.
- `app/infrastructure/distribution_config.py`: centro de distribuição e entregadores padrão a partir do `.env`.
- `backend/scripts/analisar_distribuicao.py`: compara estratégias e centros no cenário do seed usando o provedor simulado, sem consumir a API. Execute a partir de `backend/` com `python -m scripts.analisar_distribuicao --help`.

## Princípio de organização

A lógica de domínio não deve depender do React, nem realizar chamadas HTTP diretamente para o Google Maps. As dependências externas devem ser encapsuladas em serviços e adaptadores próprios.
