# API do backend

Guia para quem vai consumir a API no frontend (F08 e F09). A referência completa de cada campo fica no Swagger, gerado automaticamente pelo FastAPI. Este guia explica o fluxo, os conceitos e os cuidados.

## Como rodar

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
python -m app.infrastructure.seed   # cria o banco e os três cenários
uvicorn app.main:app --reload
```

| Endereço | Conteúdo |
| -- | -- |
| `http://localhost:8000/docs` | Swagger: todos os endpoints, com os campos e um botão para testar |
| `http://localhost:8000/redoc` | A mesma referência em outro formato |
| `http://localhost:8000/openapi.json` | Especificação OpenAPI, útil para gerar tipos no frontend |

O CORS libera `http://localhost:5173`, o endereço padrão do Vite.

O comando de seed cadastra `NORMAL`, `ALTA_DEMANDA` e `EQUIDADE`. Ele pode
ser executado novamente: cenários e pedidos existentes são recuperados pelos
códigos, sem duplicação. Os dois cenários novos reutilizam os oito bairros do
cenário NORMAL. `ALTA_DEMANDA` tem 24 pedidos (3 por bairro) e `EQUIDADE` tem
15 pedidos (2 por bairro em sete bairros e 1 no oitavo). A massa de cada cenário tem códigos próprios e
atributos variados de categoria, prioridade, SLA, peso, volume e serviço.

Pedidos cadastrados por `POST /api/pedidos` são persistidos com origem
`manual` e participam da próxima simulação daquele cenário. Quando a execução
chega ao evento `simulacao_concluida`, esses pedidos são arquivados (`ativo=0`)
e deixam as listas operacionais; os pedidos de referência permanecem ativos.
O histórico e os eventos da simulação continuam consultáveis. Pedidos manuais
criados depois da criação da simulação permanecem ativos para a operação
seguinte. A lista de cenários e o endpoint de pedidos consideram somente os
registros ativos.

### Provedor de mapas

Cada simulação usa um provedor de mapas:

- **`simulado`**: calcula distâncias em linha reta, com uma velocidade média e um fator de trânsito pelo horário (mais lento nos horários de pico). Não tem custo e responde na hora. Use este durante o desenvolvimento.
- **`google`**: usa a Google Routes API, com trânsito real. Precisa de `GOOGLE_MAPS_API_KEY` no `backend/.env` e consome uma cota diária.

O padrão é definido no `backend/.env` (`PROVEDOR_MAPAS`). O frontend pode escolher o provedor ao criar a simulação.

## Convenções

- **Horários** usam ISO 8601 e são devolvidos sempre no fuso de Salvador (`-03:00`), por exemplo `2026-10-30T16:30:00-03:00`. Ao enviar, um horário sem fuso (`2026-10-30T16:30:00`) é considerado de Salvador. Alguns horários calculados têm frações de segundo (`18:36:33.082209-03:00`); formate na exibição.
- **Distâncias** estão em metros (`_m`) e **atrasos** em minutos (`_min`).
- **Coordenadas** usam `latitude` e `longitude`. O caminho das viagens vem como uma lista de pares `[latitude, longitude]`, a mesma ordem usada pelo Leaflet.
- **Erros** seguem o padrão do FastAPI: `{"detail": "mensagem"}`. Nos erros de validação (`422`), `detail` é uma lista com o campo e o motivo.

## Fluxo típico

```
GET  /api/configuracao                    → valores padrão do formulário
GET  /api/cenarios                        → escolher o cenário
POST /api/simulacoes                      → criar e iniciar a execução automática
GET  /api/simulacoes/{id}                 → acompanhar o estado atualizado
POST /api/simulacoes/{id}/pausar          → pausar
POST /api/simulacoes/{id}/retomar         → retomar
GET  /api/simulacoes/{id}/rotas           → desenhar/atualizar o mapa
GET  /api/simulacoes/{id}/auditoria/...   → relatórios ao final
```

Após a criação, o backend avança automaticamente uma etapa por vez. O frontend consulta `GET /api/simulacoes/{id}` para atualizar pedidos, entregadores e indicadores; ele não avança o relógio. O intervalo real padrão entre etapas é 1 segundo e pode ser alterado com `INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS`. Esse intervalo controla a espera do servidor; o relógio simulado avança até o próximo evento, que pode representar vários minutos.

Todo endpoint de controle devolve os **eventos processados** e o **estado completo** depois da ação. Assim, a tela é atualizada com uma única requisição.

## Endpoints

### Configuração e cenários

#### `GET /api/configuracao`

Valores padrão e opções para o formulário de nova simulação.

```json
{
  "provedor_padrao": "simulado",
  "provedores": [
    { "nome": "google", "disponivel": false },
    { "nome": "simulado", "disponivel": true }
  ],
  "estrategia_padrao": "insercao_mais_barata",
  "estrategias": ["insercao_mais_barata", "ordem_da_fila", "equidade_sla"],
  "categorias_produto": ["alimento", "medicamento", "roupa", "eletronico", "outro"],
  "modalidades_entrega": ["entrega_rapida", "clube", "convencional"],
  "quantidade_entregadores_padrao": 2,
  "max_entregadores": 20,
  "centro": { "nome": "Comercio", "latitude": -12.971, "longitude": -38.501 },
  "expediente": { "inicio": "09:00", "fim": "17:00" }
}
```

Desabilite no formulário os provedores com `disponivel: false`.

`categorias_produto` e `modalidades_entrega` também são geradas a partir dos
valores válidos do backend e alimentam o formulário de novo pedido.

#### `GET /api/cenarios`

```json
[
  {
    "id": 1,
    "codigo": "NORMAL",
    "nome": "Operacao normal",
    "descricao": "Condicoes normais de transito e 10 pedidos predefinidos para simulacao.",
    "quantidade_pedidos": 10
  },
  {
    "id": 2,
    "codigo": "ALTA_DEMANDA",
    "nome": "Alta Demanda e Trânsito Intenso",
    "descricao": "24 pedidos próprios, distribuídos em 3 pedidos por bairro nos oito bairros atendidos.",
    "quantidade_pedidos": 24
  },
  {
    "id": 3,
    "codigo": "EQUIDADE",
    "nome": "Distribuição com Equidade",
    "descricao": "15 pedidos próprios, distribuídos de forma equilibrada pelos oito bairros atendidos.",
    "quantidade_pedidos": 15
  }
]
```

Os IDs são atribuídos pelo SQLite e podem variar conforme o banco. Use o
`id` retornado por `GET /api/cenarios` ao criar uma simulação.

Ao criar uma simulação de `ALTA_DEMANDA`, a API seleciona automaticamente o
provedor `simulado` com fator fixo 2.0, mesmo que o provedor padrão do ambiente
seja outro. Se a requisição informar explicitamente `"provedor": "google"`,
a API responde `400`, pois o trânsito do Google não pode receber esse fator.
Os cenários `NORMAL` e `EQUIDADE` mantêm o comportamento de provedor existente.

#### `GET /api/cenarios/{cenario_id}/pedidos`

Pedidos do cenário, antes de qualquer simulação: código, bairro, coordenadas, categoria, cliente clube, entrega rápida, SLA, criação, prazo, peso, volume e tempo de serviço. Use para mostrar o cenário antes de simular. Devolve `404` se o cenário não existir.

### Cadastro de pedidos

#### `GET /api/bairros`

Lista os bairros cadastrados, incluindo os IDs reais usados no POST. O
formulário usa esta resposta e não mantém uma cópia local da lista.

#### `POST /api/pedidos`

Cria um pedido associado somente ao cenário informado. Os quatro campos do
formulário são os únicos enviados pelo frontend:

```json
{
  "cenario_id": 3,
  "bairro_id": 2,
  "categoria_produto": "medicamento",
  "modalidade": "entrega_rapida"
}
```

`cenario_id` e `bairro_id` são IDs obtidos da API. A categoria deve ser um dos
valores de `GET /api/configuracao`; `modalidade` é `entrega_rapida`, `clube`
ou `convencional`.
O backend gera um código `PED-MAN-...`, a data de criação no fuso de Salvador,
o SLA, o prazo calculado pelas regras de expediente e os dados de peso, volume
e serviço por categoria. Os perfis operacionais reutilizam combinações dos
pedidos de referência: alimento (2,5 kg, 5 L, 8 min), medicamento (1,2 kg,
2 L, 7 min), roupa (1 kg, 4 L, 5 min), eletrônico (3 kg, 8 L, 10 min) e outro
(0,5 kg, 1 L, 5 min).

`entrega_rapida` define `entrega_rapida: true`, `cliente_clube: false` e SLA de
1 dia útil. `clube` define `cliente_clube: true`, `entrega_rapida: false` e
SLA de 3 dias úteis. `convencional` define as duas flags como `false` e usa
SLA de 5 dias úteis, conforme os pedidos de referência PED-002 e PED-010.
Essas combinações alimentam as regras existentes de prioridade; não foi criada
uma regra separada para a modalidade convencional. O campo `prioridade_inicial` da resposta é
calculado pelo backend no momento do cadastro; a fila recalcula a prioridade
quando a simulação começa, usando o estado e as estimativas daquele momento.

Resposta observada em uma execução de demonstração (`id`, código e horários
são gerados pelo backend e variam por cadastro):

```json
{
  "id": 57,
  "codigo": "PED-MAN-043C3E217F714B3F85979C643E1E43A2",
  "bairro": "Barra",
  "latitude": -13.006,
  "longitude": -38.528,
  "categoria_produto": "medicamento",
  "cliente_clube": false,
  "entrega_rapida": true,
  "sla_dias_uteis": 1,
  "criado_em": "2026-11-12T19:29:00.528613-03:00",
  "prazo_entrega_em": "2026-11-13T17:00:00-03:00",
  "peso_kg": 1.2,
  "volume_l": 2.0,
  "tempo_servico_min": 7,
  "id": 51,
  "prioridade_inicial": 12
}
```

O código e o ID são gerados no backend. O registro é persistido no SQLite e
`cenario_id` é a chave estrangeira de associação; pedidos dos outros cenários
não são alterados. Antes de criar a simulação, o pedido fará parte da massa
carregada para a próxima execução.

Uma simulação ativa mantém um snapshot dos pedidos e um plano de distribuição.
Não há inserção dinâmica segura na fila, no plano de rotas e na auditoria desta
versão. Se um pedido for cadastrado durante uma simulação, ele permanece salvo
e aparece na listagem com o estado “Próxima simulação”; não altera a execução
em andamento. O formulário informa essa regra, e a listagem é atualizada após
a confirmação do cadastro.

### Criação e consulta

#### `POST /api/simulacoes`

```json
{
  "cenario_id": 1,
  "inicio": "2026-10-30T10:00:00",
  "quantidade_entregadores": 2,
  "estrategia": "insercao_mais_barata",
  "segundos_reais_por_hora_simulada": 15,
  "provedor": "simulado"
}
```

Só `cenario_id` e `inicio` são obrigatórios. Os outros campos usam a configuração do backend quando omitidos. A velocidade aceita somente `5`, `15`, `30` ou `60`; quando omitida, usa `15`.

Use o `id` obtido em `GET /api/cenarios`. Com `estrategia` omitida,
`NORMAL` usa `insercao_mais_barata`, `ALTA_DEMANDA` força roteamento simulado
com fator 2.0, e `EQUIDADE` usa `equidade_sla`. A criação inicia a execução
automática; não é necessário chamar outro endpoint para iniciar o motor. As três
estratégias também podem ser escolhidas explicitamente pelo campo `estrategia`.

O `inicio` representa o relógio simulado, não o relógio real do computador.
O controle do frontend permite selecionar data e horário e sugere um início
posterior à criação mais recente dos pedidos daquele cenário. O valor enviado
é `YYYY-MM-DDTHH:mm:ss`, sem offset; a API interpreta esse horário local em
`America/Bahia` e devolve os estados com o offset correspondente. Assim, por
exemplo, `2026-10-30T10:00:00` é interpretado como
`2026-10-30T10:00:00-03:00`.

O `inicio` deve cair em um **dia útil, entre 09:00 inclusive e 17:00 exclusive**
(horário de Salvador). Caso contrário, a resposta é `400`. O frontend mostra a
validação antes do envio e o backend continua aplicando a mesma validação.

Todos os pedidos recuperados para o cenário formam o snapshot inicial da
operação e entram no planejamento, mesmo quando `criado_em` for anterior ou
posterior à data escolhida. `criado_em` e `prazo_entrega_em` continuam sendo os
valores históricos persistidos; a data de início define o relógio da operação
e o expediente usado para autorizar partidas. Um cenário sem pedidos retorna
erro de validação, em vez de criar uma simulação vazia.

Devolve `201` com o estado da simulação (ver [Estado](#estado-da-simulação)) e agenda um executor em segundo plano. O estado operacional passa a `executando`; a primeira etapa monta a fila e planeja as viagens. A resposta de criação pode chegar antes dessa primeira etapa.

No executor automático, o relógio usa tempo monotônico e a velocidade é
individual de cada execução: `5`, `15`, `30` ou `60` segundos reais por hora
simulada (padrão `15`). A conversão é acumulada continuamente e processa, em
ordem, todos os eventos planejados alcançados; cada evento mantém o horário
exato calculado pela rota. A velocidade escolhida fica registrada no estado e
na auditoria. Pausar sincroniza e congela o relógio. Retomar reinicia a
referência monotônica sem contar o intervalo pausado e mantém a velocidade
selecionada. O intervalo do executor é configurável por
`INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS` (padrão `0.05`). O frontend consulta o
estado a cada 100 ms por padrão; pode ser configurado com
`VITE_INTERVALO_ATUALIZACAO_SIMULACAO_MS`.

| Estratégia | Como distribui os pedidos |
| -- | -- |
| `insercao_mais_barata` | Insere cada pedido onde ele menos aumenta o custo total (duração, atrasos e ordem da fila). A prioridade pesa, mas um pedido pode passar à frente se isso economizar trajeto ou evitar atraso. Padrão geral. |
| `ordem_da_fila` | Alterna os caminhões seguindo a ordem da fila, sem otimizar o trajeto. Serve de referência para comparação. |
| `equidade_sla` | Usa duração, prioridade e atrasos de SLA, somados a uma penalidade pelos atrasos normalizados por bairro. É o padrão de `EQUIDADE`; também pode ser selecionada nos outros cenários. |

Quando `estrategia` é omitida, `EQUIDADE` escolhe `equidade_sla`; os demais
cenários mantêm `insercao_mais_barata`. Uma estratégia válida informada na
requisição tem precedência sobre o padrão do cenário.

A estratégia `equidade_sla` mede, para cada pedido válido, o atraso positivo
dividido pela duração do SLA (prazo menos criação). Calcula a média desses
valores em cada bairro e dá o mesmo peso a cada bairro com amostras, sem
atribuir zero aos bairros sem pedidos. Seu custo soma o custo operacional e
de SLA já utilizado por `insercao_mais_barata` a uma parcela territorial:
`240 × (média dos bairros + 0,5 × pior bairro + 0,5 × amplitude territorial)`.
Os 240 minutos equivalem à penalidade base de um pedido atrasado; os dois
termos com peso 0,5 dividem igualmente a atenção ao pior resultado e à
diferença entre bairros. Pedidos sem prazo ou com duração de SLA inválida não
entram na métrica territorial, mas continuam sujeitos às demais regras da
distribuição.

#### `GET /api/simulacoes`

Simulações gravadas, da mais recente para a mais antiga. `ativa` indica se ela ainda está em memória e pode ser controlada.

```json
[
  {
    "id": 1,
    "cenario_id": 1,
    "criada_em": "2026-11-02T22:37:26.589882Z",
    "inicio_simulado": "2026-10-30T16:30:00-03:00",
    "fim_simulado": "2026-10-30T18:36:33.082209-03:00",
    "centro_nome": "Comercio",
    "estrategia": "insercao_mais_barata",
    "segundos_reais_por_hora_simulada": 15,
    "entregadores": ["CAM-01", "CAM-02"],
    "status": "concluida",
    "ativa": true
  }
]
```

#### `GET /api/simulacoes/{id}`

Estado atual da simulação, sem avançar o relógio.

O estado em execução fica em memória. Se o backend reiniciar, esse endpoint e
os endpoints de controle devolvem `410` para uma simulação gravada que saiu da
memória. Os endpoints `/eventos` e `/auditoria/{consulta}` continuam lendo os
dados persistidos. Comparações que precisam do estado final devem consumir o
campo `estado` devolvido por `POST /executar`; não dependem de reconstruir o
estado após reiniciar o backend.

### Controle

Os endpoints de avanço devolvem `{ "eventos": [...], "estado": {...} }`.

| Endpoint | Corpo | O que faz |
| -- | -- | -- |
| `POST /api/simulacoes/{id}/proxima-etapa` | nenhum | Na primeira chamada, inicia a simulação. Depois, avança até o próximo instante em que algo acontece e processa os eventos desse instante. |
| `POST /api/simulacoes/{id}/avancar` | `{"minutos": 30}` ou `{"ate": "2026-10-30T12:00:00"}` | Avança o relógio e processa os eventos do intervalo. O relógio anda o intervalo inteiro, mesmo sem eventos. Informe **apenas um** dos dois campos; `minutos` vai de 0 a 1440. |
| `POST /api/simulacoes/{id}/executar` | nenhum | Processa todos os eventos; libera o controle entre instantes de evento para permitir pausa concorrente. |
| `POST /api/simulacoes/{id}/pausar` | nenhum | Muda o estado operacional para `pausada` e bloqueia avanços até a retomada. |
| `POST /api/simulacoes/{id}/retomar` | nenhum | Muda de `pausada` para `executando`; a próxima etapa continua do estado atual. |

Pausar e retomar devolvem `id`, `estado_execucao`, `mensagem` e o estado atualizado em `simulacao`. Exemplo abreviado:

```json
{
  "id": 7,
  "estado_execucao": "pausada",
  "mensagem": "Simulação pausada.",
  "simulacao": {
    "id": 7,
    "estado_execucao": "pausada",
    "agora": "2026-10-30T10:12:00-03:00",
    "iniciada": true,
    "concluida": false
  }
}
```

O ciclo operacional usa `aguardando` quando a execução automática está
desabilitada, `executando` durante o ciclo, `pausada` após confirmação do
endpoint de pausa, `concluida` após o último evento e `falhou` se uma etapa
lançar uma exceção. O campo `erro_execucao` descreve uma falha automática.
Pausar antes da primeira etapa, repetir pausa,
retomar sem estar pausada, ou pausar/retomar uma simulação concluída retorna
`409`. Simulações inexistentes retornam `404`.

O lock por simulação serializa avanços, pausa, retomada e consulta de estado.
Uma chamada de avanço manual termina seu intervalo antes que uma pausa
concorrente seja confirmada. `/executar` processa um instante de evento por
vez e libera o lock entre eles; se uma pausa concorrente for aceita, interrompe
o ciclo e devolve o estado pausado. Enquanto pausada, `/proxima-etapa`,
`/avancar` e uma nova chamada a `/executar` retornam `409` sem alterar relógio,
pedidos, indicadores ou eventos. Depois de concluída, chamadas de avanço
continuam sem processar novos eventos.

Depois que a simulação termina, o relógio para no horário do último evento e os endpoints de avanço devolvem `eventos: []`. Pausa e retomada retornam `409` para uma simulação concluída. O ciclo automático e os controles manuais usam o mesmo método de avanço; os endpoints manuais continuam disponíveis para compatibilidade e testes, embora a interface não os use.

O frontend consulta o estado enquanto ele estiver `executando`, com intervalo
configurável por `VITE_INTERVALO_ATUALIZACAO_SIMULACAO_MS` (padrão: 500 ms).
Depois da inicialização, também consulta `/rotas` para atualizar a situação das
viagens e paradas mostradas no painel dos entregadores. Há no máximo um ciclo
de consulta em andamento por simulação; ele para ao concluir, pausar, desmontar
a tela ou receber `410`. O botão de pausa só muda para `Continuar` após
confirmação do backend.

### Execução automática e operação

```env
# backend/.env (os valores do ambiente do processo têm precedência)
INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS=1.0
EXECUCAO_AUTOMATICA_ATIVA=true
```

O intervalo é tempo real entre etapas, não a quantidade de minutos simulados.
Para ajustar a frequência de atualização do navegador, configure no frontend:

```env
VITE_INTERVALO_ATUALIZACAO_SIMULACAO_MS=500
```

Exemplo abreviado de uma criação automática:

```json
{
  "id": 18,
  "estado_execucao": "executando",
  "iniciada": false,
  "agora": "2026-10-30T10:00:00-03:00",
  "concluida": false
}
```

Consulte `GET /api/simulacoes/18` para receber o estado atualizado. A pausa
espera a etapa síncrona que já começou terminar e, depois da resposta, nenhum
novo evento é gravado até a retomada. O plano, o relógio e os pedidos são
mantidos para a execução continuar do mesmo ponto.

O executor é mantido em memória e existe um por simulação no processo atual.
O encerramento do servidor aguarda a etapa em andamento e termina as tarefas.
Uma reinicialização perde o executor e o estado em memória: a consulta de
estado retorna `410`, enquanto eventos e auditoria persistidos continuam
disponíveis. Em execução com múltiplos processos, cada worker mantém memória
separada; use um único worker para esta versão. Execução automática persistente
e coordenação distribuída não fazem parte desta etapa.

O frontend não usa framework de testes de componentes. `npm test` usa o runner
nativo do Node para verificar os endpoints REST de pausa/retomada, as respostas
confirmadas e erros HTTP. Nesta etapa também foram executados `npm run lint` e
`npm run build`. A suíte do backend verifica as transições, os bloqueios e a
concorrência; os cliques e a renderização dos componentes React não têm testes
automatizados de DOM.

### Mapa

#### `GET /api/simulacoes/{id}/rotas`

Rotas planejadas, com o trajeto de cada viagem. Disponível depois de iniciar a simulação (antes disso, `409`).

```json
{
  "centro": { "nome": "Comercio", "latitude": -12.971, "longitude": -38.501 },
  "rotas": [
    {
      "entregador_codigo": "CAM-01",
      "viagens": [
        {
          "numero": 1,
          "situacao": "em_andamento",
          "partida_em": "2026-10-30T16:30:00-03:00",
          "retorno_em": "2026-10-30T18:36:33.082209-03:00",
          "distancia_m": 44152,
          "caminho": [[-12.971, -38.501], [-12.963, -38.507], [-12.94, -38.358]],
          "paradas": [
            {
              "ordem": 1,
              "pedido_codigo": "PED-001",
              "bairro": "Comercio",
              "latitude": -12.963,
              "longitude": -38.507,
              "chegada_em": "2026-10-30T16:33:17.667481-03:00",
              "saida_em": "2026-10-30T16:40:17.667481-03:00",
              "status": "entregue",
              "atrasada": true
            }
          ]
        }
      ]
    }
  ],
  "nao_atribuidos": []
}
```

- `caminho` é o trajeto completo da viagem: sai do centro, passa pelas paradas e volta ao centro. Com o provedor simulado, é uma linha reta entre os pontos; com o Google, segue as ruas.
- `ordem` é o número do marcador da parada dentro da viagem.
- O trajeto é calculado na primeira chamada e reaproveitado. A `situacao` das viagens e o `status` das paradas mudam com o relógio, então consulte o endpoint novamente durante a execução para obter as cores atuais. As chamadas seguintes não consultam de novo o serviço de mapas.
- Com o Google, a primeira chamada faz uma consulta de rota por viagem.

### Eventos e auditoria

Estes endpoints leem o SQLite e funcionam para **qualquer simulação gravada**, inclusive as que não estão mais em memória.

#### `GET /api/simulacoes/{id}/eventos?apos=N`

Eventos gravados, em ordem. Com `apos`, devolve só os eventos com `sequencia` maior que `N`, útil para atualizar um log de forma incremental.

```json
{
  "sequencia": 2,
  "instante": "2026-10-30T16:30:00-03:00",
  "tipo": "pedido_na_fila",
  "pedido_codigo": "PED-001",
  "entregador_codigo": null,
  "viagem_numero": null,
  "status_anterior": "pendente",
  "status_novo": "na_fila",
  "atraso_min": null,
  "distancia_m": null,
  "detalhe": "posicao 1 na fila"
}
```

#### `GET /api/simulacoes/{id}/auditoria/{consulta}`

Executa uma das consultas prontas de `sql/auditoria/`. A resposta é uma lista de linhas.

| Consulta | Parâmetros | Resultado |
| -- | -- | -- |
| `linha_do_tempo_pedido` | `?pedido_codigo=PED-001` (obrigatório) | Eventos e mudanças de status de um pedido |
| `atrasos` | | Pedidos entregues após o prazo, do maior para o menor atraso |
| `desempenho_por_caminhao` | | Viagens, entregas, atrasos, distância em km, primeira saída e último retorno de cada caminhão |
| `pedidos_nao_entregues` | | Pedidos que terminaram sem entrega, com o último status e o motivo |

```json
[
  {
    "entregador_codigo": "CAM-01",
    "viagens_concluidas": 1,
    "viagens_canceladas": 0,
    "pedidos_entregues": 4,
    "pedidos_atrasados": 2,
    "distancia_km": 57.2,
    "primeira_saida": "2026-10-30T16:30:00-03:00",
    "ultimo_retorno": "2026-10-30T18:24:31-03:00"
  }
]
```

## Estado da simulação

Resposta de `GET /api/simulacoes/{id}` e campo `estado` dos endpoints de controle. Exemplo abreviado de uma simulação iniciada às 16h30 e avançada 45 minutos: a lista de pedidos e os novos campos `por_bairro` e `equidade_territorial` foram omitidos aqui; eles estão detalhados abaixo.

```json
{
  "id": 1,
  "cenario_id": 1,
  "provedor": "simulado",
  "estrategia": "insercao_mais_barata",
  "estado_execucao": "executando",
  "inicio": "2026-10-30T16:30:00-03:00",
  "agora": "2026-10-30T17:15:00-03:00",
  "proximo_instante": "2026-10-30T17:19:38.479112-03:00",
  "fim_expediente": "2026-10-30T17:00:00-03:00",
  "iniciada": true,
  "concluida": false,
  "centro": { "nome": "Comercio", "latitude": -12.971, "longitude": -38.501 },
  "indicadores": {
    "total_pedidos": 10,
    "por_status": { "pendente": 0, "na_fila": 1, "atribuido": 0, "em_rota": 6, "entregue": 3 },
    "entregues": 3,
    "entregues_no_prazo": 0,
    "entregues_atrasados": 3,
    "atraso_medio_min": 3208.5,
    "nao_atribuidos": 0,
    "devolvidos_a_fila": 1,
    "viagens_planejadas": 3,
    "viagens_concluidas": 0,
    "viagens_canceladas": 1,
    "distancia_planejada_m": 70311,
    "distancia_percorrida_m": 0
  },
  "fila": ["PED-009"],
  "pedidos": [
    {
      "codigo": "PED-002",
      "bairro": "Barra",
      "latitude": -13.006,
      "longitude": -38.528,
      "categoria_produto": "roupa",
      "cliente_clube": false,
      "entrega_rapida": false,
      "sla_dias_uteis": 5,
      "criado_em": "2026-10-26T11:30:00-03:00",
      "prazo_entrega_em": "2026-11-02T11:30:00-03:00",
      "peso_kg": 1.0,
      "volume_l": 4.0,
      "tempo_servico_min": 5,
      "status": "em_rota",
      "posicao_fila": 5,
      "prioridade": 22,
      "entregador_codigo": "CAM-02",
      "viagem_numero": 1,
      "previsao_entrega_em": "2026-10-30T17:38:06-03:00",
      "entregue_em": null,
      "atraso_min": null,
      "observacao": ""
    }
  ],
  "entregadores": [
    {
      "codigo": "CAM-01",
      "situacao": "em_viagem",
      "viagem_atual": 1,
      "retorno_previsto_em": "2026-10-30T18:36:33.082209-03:00",
      "proxima_partida_em": null,
      "viagens_planejadas": 1,
      "viagens_concluidas": 0,
      "viagens_canceladas": 0,
      "entregas": 1,
      "entregas_atrasadas": 1,
      "distancia_percorrida_m": 0
    }
  ]
}
```

### Campos principais

| Campo | Significado |
| -- | -- |
| `estado_execucao` | Estado operacional controlado pelo backend: `aguardando`, `executando`, `pausada`, `concluida` ou `falhou`. |
| `agora` | Horário atual do relógio da simulação |
| `proximo_instante` | Quando acontece o próximo evento; `null` quando a simulação terminou |
| `fila` | Códigos dos pedidos com status `na_fila`, na ordem em que seriam atendidos |
| `pedidos[].posicao_fila` e `prioridade` | Posição e pontuação de prioridade usadas no planejamento; `null` antes do planejamento ou quando não houve atribuição |
| `pedidos[].previsao_entrega_em` | Quando a entrega deve ser concluída, pelo plano; `null` se já foi entregue, se voltou para a fila ou se a viagem sairia depois das 17h |
| `pedidos[].criado_em` | Data original de criação, preservada do pedido cadastrado. |
| `pedidos[].prazo_entrega_em` | Prazo original do SLA, calculado no cadastro e não reescrito pela simulação. |
| `pedidos[].entregue_em` | Instante do evento real de entrega no relógio simulado; `null` até a entrega. |
| `pedidos[].atualizado_em` | Instante do evento mais recente registrado para o pedido; `null` antes de entrar na simulação. |
| `pedidos[].atraso_min` | Minutos de atraso na conclusão (0 se no prazo); preenchido após a entrega |
| `pedidos[].observacao` | Detalhe do último evento do pedido, como `"viagem cancelada pelo fim do expediente"` |
| `entregadores[].proxima_partida_em` | Próxima viagem que ainda vai sair; `null` se não houver |
| `indicadores.distancia_percorrida_m` | Soma das viagens já concluídas (só aumenta quando o caminhão retorna) |

### Indicadores territoriais

`indicadores.por_bairro` contém uma linha para cada bairro cadastrado, mesmo
quando não há pedidos ou entregas para ele. Os valores abaixo usam o histórico
real de eventos de entrega (`pedido_entregue`); previsões só são usadas para
marcar risco nos pedidos ainda em andamento.

| Campo | Unidade e regra |
| -- | -- |
| `total_pedidos` | Contagem de todos os pedidos daquele bairro incluídos na simulação. |
| `entregues` | Contagem com estado `entregue` e horário real de entrega. |
| `entregues_com_sla_valido` | Entregas reais com prazo posterior à criação; é o denominador dos percentuais de SLA. |
| `entregues_no_prazo`, `entregues_atrasados` | Contagens entre as entregas com SLA válido, comparando o horário real com o prazo. |
| `pendentes` | Contagem nos estados `pendente` e `na_fila`. |
| `pendentes_vencidos` | Pedidos pendentes com prazo anterior ao relógio atual da simulação. Não são contabilizados como atrasos efetivos. |
| `em_andamento` | Contagem nos estados `atribuido` e `em_rota`. |
| `em_risco_sla` | Pedidos em andamento cujo prazo já passou ou cuja previsão do plano ultrapassa o prazo. É um sinal de risco, não um atraso observado. |
| `tempo_medio_entrega_min` | Média de `entregue_em - criado_em`, em minutos corridos, para entregas com horário real. |
| `atraso_medio_min` | Média dos atrasos positivos reais, em minutos, considerando somente entregas atrasadas com SLA válido; `null` quando não há atraso. |
| `percentual_cumprimento_sla` | `entregues_no_prazo / entregues_com_sla_valido × 100`; `null` sem amostras válidas. |
| `taxa_atraso` | `entregues_atrasados / entregues_com_sla_valido × 100`; `null` sem amostras válidas. |
| `atraso_medio_normalizado_sla` | Média, por entrega real válida, de `max(0, entregue_em - prazo) / (prazo - criado_em)`. Entregas no prazo contribuem com zero; pedidos sem SLA válido são excluídos. |

`indicadores.equidade_territorial` resume os resultados reais. Melhor e pior
bairro são definidos pelo menor e maior atraso médio normalizado; a diferença
é `pior - melhor`. O índice reutiliza a função da F09.3 sobre as amostras reais
de entregas concluídas: `média das médias por bairro + 0,5 × pior média + 0,5
× (pior média - melhor média)`. Cada bairro com amostra tem peso igual;
bairros sem entregas válidas não entram na fórmula. Se nenhuma entrega tiver
SLA válido, o índice e os bairros melhor/pior são `null` e
`bairros_com_amostras_validas` é zero.

O índice F09.3 usado durante o planejamento é uma previsão; este índice mede
somente entregas concluídas. `em_risco_sla` também pode usar previsão, mas não
altera as contagens de entregas atrasadas. O SQLite persiste o instante e o
código do pedido em cada evento de entrega; o cenário e os pedidos persistidos
permitem recuperar bairro, criação e prazo para auditoria.

Exemplo real abreviado: resposta de uma execução de teste com o cenário
`NORMAL` (10 pedidos), roteador `simulado` e início às 09:00. Os números vêm
dos eventos da simulação executada; outros bairros foram omitidos neste trecho.

```json
{
  "por_bairro": [
    {
      "bairro": "Barra",
      "total_pedidos": 2,
      "entregues": 2,
      "entregues_com_sla_valido": 2,
      "entregues_no_prazo": 2,
      "entregues_atrasados": 0,
      "pendentes": 0,
      "pendentes_vencidos": 0,
      "em_andamento": 0,
      "em_risco_sla": 0,
      "tempo_medio_entrega_min": 3393.5,
      "atraso_medio_min": null,
      "percentual_cumprimento_sla": 100.0,
      "taxa_atraso": 0.0,
      "atraso_medio_normalizado_sla": 0.0
    },
    {
      "bairro": "Pituba",
      "total_pedidos": 1,
      "entregues": 1,
      "entregues_com_sla_valido": 1,
      "entregues_no_prazo": 0,
      "entregues_atrasados": 1,
      "pendentes": 0,
      "pendentes_vencidos": 0,
      "em_andamento": 0,
      "em_risco_sla": 0,
      "tempo_medio_entrega_min": 4327.8,
      "atraso_medio_min": 2887.8,
      "percentual_cumprimento_sla": 0.0,
      "taxa_atraso": 100.0,
      "atraso_medio_normalizado_sla": 2.0054
    }
  ],
  "equidade_territorial": {
    "melhor_bairro": "Barra",
    "atraso_normalizado_melhor_bairro": 0.0,
    "pior_bairro": "Pituba",
    "atraso_normalizado_pior_bairro": 2.0054,
    "diferenca_melhor_pior": 2.0054,
    "indice_equidade_territorial_real": 2.4752,
    "bairros_com_amostras_validas": 8
  }
}
```

Os pedidos `PED-001`, `PED-003` e `PED-004` do cenário NORMAL já estão com o prazo vencido em qualquer horário de 30/10. Por isso, os atrasos médios são grandes.

Exemplo real abreviado do estado final de `ALTA_DEMANDA`, executado às 10:00
com dois entregadores e roteador simulado. A resposta foi obtida em
`POST /api/simulacoes/{id}/executar`; os 24 eventos de entrega foram
registrados:

```json
{
  "provedor": "simulado",
  "estrategia": "insercao_mais_barata",
  "concluida": true,
  "indicadores": {
    "total_pedidos": 24,
    "por_status": {
      "pendente": 0,
      "na_fila": 0,
      "atribuido": 0,
      "em_rota": 0,
      "entregue": 24
    },
    "entregues": 24,
    "entregues_no_prazo": 24,
    "entregues_atrasados": 0,
    "atraso_medio_min": null,
    "distancia_percorrida_m": 102988,
    "por_bairro": [
      {
        "bairro": "Barra",
        "total_pedidos": 3,
        "entregues": 3,
        "entregues_no_prazo": 3,
        "entregues_atrasados": 0,
        "atraso_medio_normalizado_sla": 0.0
      }
    ],
    "equidade_territorial": {
      "indice_equidade_territorial_real": 0.0,
      "bairros_com_amostras_validas": 8
    }
  }
}
```

Os demais bairros também tiveram três entregas no prazo e atraso normalizado
zero. O relatório F09.5 reúne a tabela das três estratégias e as medições dos
três cenários em [f09-validacao-comparativa.md](f09-validacao-comparativa.md).

### Status dos pedidos

```
pendente → na_fila → atribuido → em_rota → entregue
```

| Status | Significado |
| -- | -- |
| `pendente` | A simulação ainda não começou ou o pedido ainda não foi criado |
| `na_fila` | Aguardando: não coube em nenhum caminhão ou voltou para a fila |
| `atribuido` | Tem caminhão e viagem definidos, aguardando a partida |
| `em_rota` | O caminhão saiu com o pedido |
| `entregue` | Entrega concluída |

### Situação das viagens e dos caminhões

| Viagem | Significado |
| -- | -- |
| `planejada` | Ainda não saiu |
| `em_andamento` | Saiu do centro e não voltou |
| `concluida` | Voltou ao centro |
| `cancelada` | Sairia depois das 17h e não saiu; os pedidos voltaram para a fila |

O caminhão está `em_viagem` ou `no_centro`.

### Tipos de evento

| Tipo | Quando ocorre |
| -- | -- |
| `simulacao_iniciada` / `simulacao_concluida` | Início e fim; o `detalhe` traz um resumo |
| `pedido_na_fila` | Pedido entra na fila (com a posição no `detalhe`) |
| `pedido_atribuido` / `pedido_nao_atribuido` | Resultado do planejamento |
| `viagem_iniciada` / `pedido_em_rota` | Caminhão sai do centro |
| `pedido_entregue` | Entrega concluída, com `atraso_min` |
| `viagem_concluida` | Retorno ao centro, com `distancia_m` |
| `viagem_cancelada` / `pedido_devolvido_a_fila` | Viagem que sairia depois das 17h |

Eventos de pedido que mudam o status trazem `status_anterior` e `status_novo`.

## Regras da simulação

- **Snapshot do cenário**: todos os pedidos recuperados ao criar a simulação são considerados no plano, sem filtrar pela data histórica de criação. O horário de criação e o prazo SLA originais são preservados. Pedidos cadastrados depois que a simulação foi criada pertencem à próxima execução.
- **Plano único**: as viagens do snapshot são planejadas uma vez, na primeira etapa.
- **Expediente**: um caminhão pode sair até as 17h, mesmo que volte depois. A viagem que sairia depois das 17h é cancelada às 17h.
- **Várias viagens**: um caminhão pode fazer mais de uma viagem, respeitando o limite de paradas, peso e volume.
- Os estados operacionais das simulações ativas (inclusive pausa) ficam em memória; a auditoria persiste o histórico de eventos e o status geral. Os pedidos do cenário não mudam, então o mesmo cenário pode ser simulado várias vezes.

## Erros

| Código | Quando | O que fazer no frontend |
| -- | -- | -- |
| `400` | Início fora do expediente ou em fim de semana, Google sem chave, avanço para um horário anterior ao atual, consulta sem `pedido_codigo` | Mostrar a mensagem de `detail` |
| `404` | Cenário, simulação ou consulta inexistente | Voltar para a lista |
| `409` | `/rotas` antes da inicialização; pausa/retomada inválida; avanço enquanto pausada | Iniciar a simulação ou seguir a transição indicada pelo estado atual |
| `410` | A simulação existe, mas não está mais em memória (o servidor reiniciou) | Oferecer criar uma nova; eventos e auditoria continuam disponíveis |
| `422` | Corpo inválido (campo faltando, valor fora do limite, estratégia ou provedor desconhecidos) | Corrigir o formulário |
| `429` | Limite diário da Google Routes API atingido | Sugerir o provedor `simulado` |
| `502` | Falha do serviço de mapas | Tentar de novo: a simulação não muda quando há falha |

## Limitações

- As simulações ativas ficam na memória do servidor. Se ele reiniciar, só é possível consultar eventos e auditoria das simulações anteriores.
- Não há endpoint para remover simulações da memória nem para alterar cenários e pedidos.
- Mudanças de trânsito durante a simulação não alteram o plano.
