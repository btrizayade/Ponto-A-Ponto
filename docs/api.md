# API do backend

Guia para quem vai consumir a API no frontend (F08 e F09). A referência completa de cada campo fica no Swagger, gerado automaticamente pelo FastAPI. Este guia explica o fluxo, os conceitos e os cuidados.

## Como rodar

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
python -m app.infrastructure.seed   # cria o banco e o cenário NORMAL
uvicorn app.main:app --reload
```

| Endereço | Conteúdo |
| -- | -- |
| `http://localhost:8000/docs` | Swagger: todos os endpoints, com os campos e um botão para testar |
| `http://localhost:8000/redoc` | A mesma referência em outro formato |
| `http://localhost:8000/openapi.json` | Especificação OpenAPI, útil para gerar tipos no frontend |

O CORS libera `http://localhost:5173`, o endereço padrão do Vite.

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
POST /api/simulacoes                      → criar (a simulação começa parada)
POST /api/simulacoes/{id}/proxima-etapa   → iniciar: monta a fila e planeja as viagens
GET  /api/simulacoes/{id}/rotas           → desenhar o mapa
POST /api/simulacoes/{id}/proxima-etapa   → avançar etapa por etapa
POST /api/simulacoes/{id}/avancar         → ou avançar alguns minutos
POST /api/simulacoes/{id}/executar        → ou ir direto até o fim
GET  /api/simulacoes/{id}/auditoria/...   → relatórios ao final
```

O relógio da simulação **só anda quando o frontend pede**. Não há atualização automática pelo servidor. Para um modo "play", chame `proxima-etapa` ou `avancar` em intervalos (por exemplo, `avancar` com `minutos: 5` a cada segundo) até `estado.concluida` ser `true`.

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
  "estrategias": ["insercao_mais_barata", "ordem_da_fila"],
  "quantidade_entregadores_padrao": 2,
  "max_entregadores": 20,
  "centro": { "nome": "Comercio", "latitude": -12.971, "longitude": -38.501 },
  "expediente": { "inicio": "09:00", "fim": "17:00" }
}
```

Desabilite no formulário os provedores com `disponivel: false`.

#### `GET /api/cenarios`

```json
[
  {
    "id": 1,
    "codigo": "NORMAL",
    "nome": "Operacao normal",
    "descricao": "Condicoes normais de transito e 10 pedidos predefinidos para simulacao.",
    "quantidade_pedidos": 10
  }
]
```

#### `GET /api/cenarios/{cenario_id}/pedidos`

Pedidos do cenário, antes de qualquer simulação: código, bairro, coordenadas, categoria, cliente clube, entrega rápida, SLA, criação, prazo, peso, volume e tempo de serviço. Use para mostrar o cenário antes de simular. Devolve `404` se o cenário não existir.

### Criação e consulta

#### `POST /api/simulacoes`

```json
{
  "cenario_id": 1,
  "inicio": "2026-10-30T09:00:00",
  "quantidade_entregadores": 2,
  "estrategia": "insercao_mais_barata",
  "provedor": "simulado"
}
```

Só `cenario_id` e `inicio` são obrigatórios. Os outros campos usam a configuração do backend quando omitidos.

O `inicio` deve cair em um **dia útil, entre 9h e 17h** (horário de Salvador). Caso contrário, a resposta é `400`.

Devolve `201` com o estado da simulação (ver [Estado](#estado-da-simulação)), ainda com `iniciada: false`. A fila e o plano são montados na primeira chamada de controle.

| Estratégia | Como distribui os pedidos |
| -- | -- |
| `insercao_mais_barata` | Insere cada pedido onde ele menos aumenta o custo total (duração, atrasos e ordem da fila). A prioridade pesa, mas um pedido pode passar à frente se isso economizar trajeto ou evitar atraso. Padrão. |
| `ordem_da_fila` | Alterna os caminhões seguindo a ordem da fila, sem otimizar o trajeto. Serve de referência para comparação. |

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
    "entregadores": ["CAM-01", "CAM-02"],
    "status": "concluida",
    "ativa": true
  }
]
```

#### `GET /api/simulacoes/{id}`

Estado atual da simulação, sem avançar o relógio.

### Controle

Os três endpoints devolvem `{ "eventos": [...], "estado": {...} }`.

| Endpoint | Corpo | O que faz |
| -- | -- | -- |
| `POST /api/simulacoes/{id}/proxima-etapa` | nenhum | Na primeira chamada, inicia a simulação. Depois, avança até o próximo instante em que algo acontece e processa os eventos desse instante. |
| `POST /api/simulacoes/{id}/avancar` | `{"minutos": 30}` ou `{"ate": "2026-10-30T12:00:00"}` | Avança o relógio e processa os eventos do intervalo. O relógio anda o intervalo inteiro, mesmo sem eventos. Informe **apenas um** dos dois campos; `minutos` vai de 0 a 1440. |
| `POST /api/simulacoes/{id}/executar` | nenhum | Processa tudo até o fim. |

Depois que a simulação termina, o relógio para no horário do último evento e as chamadas de controle devolvem `eventos: []`.

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
- O trajeto é calculado na primeira chamada e reaproveitado. A `situacao` das viagens e o `status` das paradas mudam com o relógio, então **chame de novo após cada avanço** para atualizar as cores. As chamadas seguintes não consultam o serviço de mapas.
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

Resposta de `GET /api/simulacoes/{id}` e campo `estado` dos endpoints de controle. Exemplo de uma simulação iniciada às 16h30, avançada 45 minutos (a lista de pedidos foi reduzida):

```json
{
  "id": 1,
  "cenario_id": 1,
  "provedor": "simulado",
  "estrategia": "insercao_mais_barata",
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
| `agora` | Horário atual do relógio da simulação |
| `proximo_instante` | Quando acontece o próximo evento; `null` quando a simulação terminou |
| `fila` | Códigos dos pedidos com status `na_fila`, na ordem em que seriam atendidos |
| `pedidos[].posicao_fila` e `prioridade` | Posição e pontuação de prioridade usadas no planejamento; `null` antes de iniciar e para pedidos criados depois do início |
| `pedidos[].previsao_entrega_em` | Quando a entrega deve ser concluída, pelo plano; `null` se já foi entregue, se voltou para a fila ou se a viagem sairia depois das 17h |
| `pedidos[].atraso_min` | Minutos de atraso na conclusão (0 se no prazo); preenchido após a entrega |
| `pedidos[].observacao` | Detalhe do último evento do pedido, como `"viagem cancelada pelo fim do expediente"` |
| `entregadores[].proxima_partida_em` | Próxima viagem que ainda vai sair; `null` se não houver |
| `indicadores.distancia_percorrida_m` | Soma das viagens já concluídas (só aumenta quando o caminhão retorna) |

Os pedidos `PED-001`, `PED-003` e `PED-004` do cenário NORMAL já estão com o prazo vencido em qualquer horário de 30/10. Por isso, os atrasos médios são grandes.

### Status dos pedidos

```
pendente → na_fila → atribuido → em_rota → entregue
```

| Status | Significado |
| -- | -- |
| `pendente` | A simulação ainda não começou ou o pedido ainda não foi criado |
| `na_fila` | Aguardando: não coube em nenhum caminhão, foi criado depois do início ou voltou para a fila |
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

- **Plano único**: as viagens são planejadas uma vez, na primeira etapa. Pedidos criados depois do início (até as 17h) entram na fila no horário de criação, mas não são atribuídos. Pedidos criados depois das 17h ficam fora da simulação.
- **Expediente**: um caminhão pode sair até as 17h, mesmo que volte depois. A viagem que sairia depois das 17h é cancelada às 17h.
- **Várias viagens**: um caminhão pode fazer mais de uma viagem, respeitando o limite de paradas, peso e volume.
- O status da simulação fica só nas tabelas de auditoria. Os pedidos do cenário não mudam, então o mesmo cenário pode ser simulado várias vezes.

## Erros

| Código | Quando | O que fazer no frontend |
| -- | -- | -- |
| `400` | Início fora do expediente ou em fim de semana, Google sem chave, avanço para um horário anterior ao atual, consulta sem `pedido_codigo` | Mostrar a mensagem de `detail` |
| `404` | Cenário, simulação ou consulta inexistente | Voltar para a lista |
| `409` | `/rotas` antes de iniciar a simulação | Chamar `proxima-etapa` antes |
| `410` | A simulação existe, mas não está mais em memória (o servidor reiniciou) | Oferecer criar uma nova; eventos e auditoria continuam disponíveis |
| `422` | Corpo inválido (campo faltando, valor fora do limite, estratégia ou provedor desconhecidos) | Corrigir o formulário |
| `429` | Limite diário da Google Routes API atingido | Sugerir o provedor `simulado` |
| `502` | Falha do serviço de mapas | Tentar de novo: a simulação não muda quando há falha |

## Limitações

- As simulações ativas ficam na memória do servidor. Se ele reiniciar, só é possível consultar eventos e auditoria das simulações anteriores.
- Não há endpoint para remover simulações da memória nem para alterar cenários e pedidos.
- Mudanças de trânsito durante a simulação não alteram o plano.
