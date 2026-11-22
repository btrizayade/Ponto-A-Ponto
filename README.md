<p align="center">
  <img src="frontend/src/assets/logotipo-pontoaponto.jpeg" alt="Ponto a Ponto" width="220" />
</p><h3 align="center">Simulador de distribuição e roteirização de entregas urbanas</h3><p align="center">
  Um laboratório de logística urbana para estudar filas de prioridade, estratégias de distribuição, roteirização, cumprimento de SLA e equidade territorial.
</p><p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/Vite-Frontend-646CFF?style=flat-square&logo=vite&logoColor=white" alt="Vite" />
  <img src="https://img.shields.io/badge/SQLite-Database-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Leaflet-Maps-199900?style=flat-square&logo=leaflet&logoColor=white" alt="Leaflet" />
</p>


## Sobre o projeto

O Ponto a Ponto é um sistema de logística desenvolvido para representar e analisar a fila de prioridade em operações de entrega urbana na cidade de Salvador, Bahia.

A aplicação recebe pedidos com diferentes características que utiliza para calcular prioridades, organizar uma fila baseada em heap, distribuir entregas entre uma quantidade ajustável de entregadores e planejar viagens respeitando restrições de tempo e localização.

Além da execução da operação, o sistema permite acompanhar o estado dos pedidos e entregadores, visualizar rotas em um mapa interativo e consultar registros persistidos para analisar os resultados.

O projeto também funciona como um ambiente experimental: diferentes cenários e estratégias podem ser executados sob parâmetros pré-definidos com o objetivo de comparar decisões logísticas.

## Objetivos

- Modelar o despacho de pedidos por meio de uma fila de prioridade baseada em heap.
- Calcular prioridade operacional, envelhecimento do pedido (aging) e risco de descumprimento do SLA.
- Comparar estratégias de distribuição de pedidos entre número de entregadores disponível.
- Planejar viagens com  variadas restrições.
- Calcular deslocamentos por meio de provedores de roteamento intercambiáveis.
- Simular a passagem do tempo e acompanhar os eventos da operação.

## Funcionalidades

Cenários e pedidos
- Três cenários de operação disponíveis para teste: NORMAL, ALTA_DEMANDA e EQUIDADE.
- Pedidos com atributos variados pré-definidos.
- Cadastro de pedidos manuais.
- Snapshot dos pedidos.

Priorização
- Fila de prioridade implementada com estrutura de heap.
- Pontuação baseada nos atributos operacionais para cada pedido.
- Aging para considerar o tempo de espera de um pedido sem características de urgência prioritária.
- Consideração do risco de SLA a partir dos prazos.

## Distribuição e planejamento

O sistema disponibiliza três estratégias:
- insercao_mais_barata
  <br>
Insere pedidos na posição que representa o menor acréscimo de custo operacional, considerando duração, atrasos e prioridade.

- ordem_da_fila <br>
Distribui seguindo a ordem da fila de prioridade, servindo como estratégia de referência.

- equidade_sla <br>
Considera o desempenho de SLA entre bairros e adiciona uma penalidade territorial ao custo da distribuição.


A quantidade de entregadores é configurável pelo usuário de acordo com a simulação. Cada entregador respeita os limites definidos no domínio, incluindo quantidade máxima de paradas, peso e volume por viagem. Quando necessário, um entregador pode realizar múltiplas viagens com retorno ao centro de distribuição.

## Roteirização
- Contrato de serviço de roteamento independente do provedor.
- Provedor simulado para desenvolvimento, testes e experimentos controlados.
- Integração opcional com a Google Routes API.
- Cache persistente para resultados de roteamento.
- Registro das consultas e respostas utilizadas em cada simulação.
- Geometrias de rota conectadas ao frontend para visualização.
  
## Acompanhamento da simulação
- Relógio simulado independente do relógio civil do computador.
- Execução automática por etapas e eventos.
- Controles de pausa e retomada.
- Estados de execução e ciclo de vida de pedidos, viagens e entregadores.
- Mapa interativo com trajetos, paradas e veículos animados.
- Página de acompanhamento de rotas em aba independente, sincronizada com o painel principal.
  
## Indicadores
- Indicadores gerais da operação.
- Métricas por bairro.
- Cumprimento de SLA e atrasos observados.
- Distância percorrida e desempenho dos entregadores.
- Métricas de equidade territorial.
- Registro de eventos e mudanças de status.
- Snapshot versionado de entradas e parâmetros experimentais.
- Consultas SQL de apoio à análise.
  
## Cenários experimentais utilizados para a demonstração do sistema
- Cenário NORMAL	<br> Operação de referência, com condições usuais de trânsito. <br>	10 pedidos de referência.
- Cenário ALTA_DEMANDA <br>	Maior volume de pedidos e fator de trânsito simulado mais intenso. <br>	24 pedidos de referência.
- Cenário EQUIDADE <br>	Massa distribuída territorialmente para permitir avaliar a estratégia de equidade por SLA. <br>	15 pedidos de referência.


Os cenários utilizam calendários temporais configurados no backend. As datas efetivas dos pedidos de referência são pré-definidas, enquanto os registros históricos do banco são preservados.

O cenário ALTA_DEMANDA utiliza o roteador simulado com fator de trânsito fixo de peso 2.0. <br> A estratégia padrão de EQUIDADE é equidade_sla; os demais cenários utilizam insercao_mais_barata por padrão. <br> As estratégias também podem ser selecionadas explicitamente na criação da simulação. <br>
Os cenários possuem características, datas e condições diferentes. Os indicadores devem ser interpretados considerando essas condições. A comparação entre resultados não demonstra, por si só, causalidade ou superioridade geral de uma estratégia sobre a outra.

## Tecnologias
Backend
- Python: implementação do domínio, algoritmos e infraestrutura.
- FastAPI: API HTTP e documentação OpenAPI.
- SQLite: persistência de cenários, pedidos, simulações, eventos, cache e auditoria.
- pytest: testes automatizados.
- httpx: suporte a testes e comunicação HTTP.
- zoneinfo / tzdata: tratamento de fusos horários.

Frontend
- React 19: construção da interface.
- Vite: servidor de desenvolvimento e build.
- React Leaflet + Leaflet: mapa interativo.
- OpenStreetMap: camada cartográfica.
- Lucide React: ícones.
- Node.js Test Runner: execução dos testes de frontend.
- Oxlint: análise estática do frontend.

Integrações de roteamento
- Google Routes API: provedor externo opcional para estimativas de rotas.
- Roteador simulado: alternativa local e determinística, sem necessidade de chave externa.

## Arquitetura
O projeto separa interface, API, domínio e infraestrutura. Essa divisão mantém as regras logísticas independentes dos detalhes de apresentação e dos provedores externos.

Para mais detalhes, consulte [architecture.md](docs/architecture.md).

## Como executar o Ponto a Ponto localmente
Pré-requisitos
- Python 3.10 ou superior.
- Node.js 20.19 ou superior (ou 22.12 ou superior), conforme os requisitos do Vite utilizado.
- npm.
- Git.

A integração com Google Routes é opcional, pois o projeto pode ser executado com o roteador simulado, sem chave de API.
1. Clonar o repositório
git clone https://github.com/btrizayade/Ponto-A-Ponto.git
cd Ponto-A-Ponto

2. Configurar o backend
Crie e ative um ambiente virtual dentro de backend. <br>
Windows PowerShell <br>
cd backend <br>
python -m venv .venv <br>
.\.venv\Scripts\Activate.ps1 <br>
Linux / macOS <br>
cd backend <br>
python -m venv .venv <br>
source .venv/bin/activate <br>
Instale as dependências: <br>
python -m pip install --upgrade pip <br>
pip install -r requirements.txt <br>
Inicialize o banco e cadastre os cenários de referência: <br>
python -m app.infrastructure.seed <br>
Inicie a API: <br>
uvicorn app.main:app --reload <br>
A API estará disponível em: <br>
- http://127.0.0.1:8000 <br>
- Swagger UI: http://127.0.0.1:8000/docs <br>
- ReDoc: http://127.0.0.1:8000/redoc <br>
- Health check: http://127.0.0.1:8000/api/health <br>
Mantenha esse terminal aberto. <br>
3. Configurar o frontend
Em outro terminal, na raiz do repositório:
cd frontend
npm install
npm run dev
A interface ficará disponível em http://localhost:5173.

O frontend utiliza VITE_API_URL para definir a URL da API. Sem configuração, utiliza http://127.0.0.1:8000, que corresponde à execução local padrão.

4. Executar a aplicação
Com backend e frontend ativos:
1. Acesse http://localhost:5173.
2. Selecione um cenário.
3. Defina a quantidade de entregadores e a velocidade do relógio simulado.
4. Inicie a simulação.
5. Acompanhe pedidos, indicadores e estado dos entregadores.
6. Abra Rotas para visualizar os trajetos e o movimento dos veículos em outra aba.

Configuração por variáveis de ambiente
O backend carrega o arquivo backend/.env, quando existente. Variáveis já definidas no ambiente do sistema têm precedência sobre o arquivo.

Exemplo de configuração local:
# Provedor de roteamento: simulado ou google
PROVEDOR_MAPAS=simulado

# Google Routes API (opcional)
GOOGLE_MAPS_API_KEY=

# Banco SQLite (prefira caminho absoluto)
PONTO_A_PONTO_DATABASE_PATH=C:\\caminho\\para\\pontoaponto.db

# Configuração do centro de distribuição (opcional)
CENTRO_DISTRIBUICAO_NOME=Comercio
CENTRO_DISTRIBUICAO_LATITUDE=-12.971
CENTRO_DISTRIBUICAO_LONGITUDE=-38.501

# Quantidade padrão de entregadores
QUANTIDADE_ENTREGADORES=2

# Execução automática
EXECUCAO_AUTOMATICA_ATIVA=true <br>
INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS=0.05 <br>
O exemplo é ilustrativo; configure somente as variáveis necessárias ao seu ambiente. Para PONTO_A_PONTO_DATABASE_PATH, prefira um caminho absoluto para evitar que o diretório de execução do processo determine qual arquivo SQLite será utilizado.

PROVEDOR_MAPAS <br>	Define o provedor padrão (simulado ou google). <br>
GOOGLE_MAPS_API_KEY <br> Chave para habilitar Google Routes API. <br>
PONTO_A_PONTO_DATABASE_PATH <br> Caminho do banco SQLite. <br>
CENTRO_DISTRIBUICAO_NOME <br> Nome do centro de distribuição. <br>
CENTRO_DISTRIBUICAO_LATITUDE / CENTRO_DISTRIBUICAO_LONGITUDE <br> Coordenadas do centro; devem ser configuradas em conjunto. <br>
QUANTIDADE_ENTREGADORES <br> Quantidade padrão quando não informada na requisição. <br>
EXECUCAO_AUTOMATICA_ATIVA <br> Habilita ou desabilita o executor automático. <br>
INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS <br> Intervalo real entre ciclos do executor. <br>


O frontend também aceita:
VITE_API_URL <br> URL base do backend.
VITE_INTERVALO_ATUALIZACAO_SIMULACAO_MS <br> Intervalo de consulta do estado da simulação em milissegundos.


## Testes e qualidade
Backend <br>
Com o ambiente virtual ativado, dentro da pasta backend: <br>
pytest <br>
Para executar um arquivo específico: <br>
pytest tests/test_priority_queue.py <br>
Frontend <br>
Dentro da pasta frontend: <br>
npm test <br>
npm run lint <br>
npm run build <br>
- npm test: executa os testes com o Node.js Test Runner. <br>
- npm run lint: executa o Oxlint. <br>
- npm run build: gera a versão de produção em frontend/dist. <br>

## Comparação experimental
O repositório contém um script para repetir a validação comparativa dos cenários:
cd backend
python scripts/comparar_cenarios_f09.py
O script utiliza bancos SQLite temporários para isolar a execução e preservar o banco de desenvolvimento. Consulte [f09-validacao-comparativa.md](docs/f09-validacao-comparativa.md) para condições, métricas e interpretação dos resultados.

## API
A API REST é documentada automaticamente pelo FastAPI. <br>
Método	Endpoint	Finalidade <br>
GET	/api/health	Verificar disponibilidade da API. <br>
GET	/api/configuracao	Obter opções e valores padrão. <br>
GET	/api/cenarios	Listar cenários e suas configurações temporais. <br>
GET	/api/bairros	Listar bairros cadastrados. <br>
GET	/api/cenarios/{id}/pedidos	Consultar pedidos ativos de um cenário. <br>
POST	/api/pedidos	Cadastrar um pedido manual. <br>
POST	/api/simulacoes	Criar uma simulação. <br>
GET	/api/simulacoes/{id}	Consultar estado operacional em memória. <br>
GET	/api/simulacoes/{id}/rotas	Consultar viagens, paradas e geometrias. <br>
GET	/api/simulacoes/{id}/parametros	Consultar parâmetros e snapshot persistidos. <br>
POST	/api/simulacoes/{id}/pausar	Pausar uma simulação. <br>
POST	/api/simulacoes/{id}/retomar	Retomar uma simulação pausada. <br>
GET	/api/simulacoes/{id}/eventos	Consultar eventos persistidos. <br>


A lista acima resume os principais endpoints e não substitui o contrato OpenAPI. Para parâmetros, exemplos de payload, respostas, códigos de erro e demais rotas, consulte [api.md](docs/api.md) ou http://127.0.0.1:8000/docs.

Documentação adicional
- [Arquitetura](docs/architecture.md)
- [Guia da API](docs/api.md)
- [Validação comparativa dos cenários — F09](docs/f09-validacao-comparativa.md)
- [Contribuição e fluxo de trabalho](docs/contributing.md)

## Contexto acadêmico e experimental
O Ponto a Ponto é um projeto de engenharia de software que reúne estruturas de dados, algoritmos de otimização, modelagem de domínio, APIs, persistência, integração geográfica e análise de desempenho.

Além de construir uma aplicação funcional, o projeto busca criar uma base reproduzível para investigar como diferentes políticas de priorização e distribuição afetam o tempo de entrega, o cumprimento de SLA e a distribuição dos resultados entre bairros.

A estratégia de equidade é uma hipótese operacional a ser avaliada por experimentos. Seu desempenho deve ser medido com cenários e massas adequados, e não presumido a partir do nome ou do objetivo da estratégia.
<p align="center">
 🚛 Desenvolvido como um laboratório de algoritmos e simulação logística urbana.
</p><p align="center">
