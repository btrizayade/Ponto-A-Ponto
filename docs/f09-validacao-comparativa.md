# F09.5 — Validação comparativa dos cenários

O cadastro, os atributos e os exemplos de consulta e execução dos três
cenários, bem como as estratégias e os indicadores da F09, estão descritos no
[guia da API](api.md#endpoints). Consulte também a seção de indicadores
territoriais desse guia para as definições dos campos.

## Como repetir

Na pasta `backend`, execute:

```bash
python scripts/comparar_cenarios_f09.py
```

O script cria SQLite temporários separados por execução, executa o seed e apaga
os bancos ao terminar. Ele não altera `backend/data/pontoaponto.db`. A resposta
JSON contém indicadores calculados após a execução real, condições do
experimento e uma impressão digital dos pedidos EQUIDADE usados nas três
estratégias.

Condições: início às 10:00 de 30/10/2026 (America/Bahia), roteamento simulado,
dois entregadores, centro e capacidades padrão (seis paradas por viagem,
500 kg e 3.000 L). Os pedidos EQUIDADE foram criados entre 09:00 e 09:45 do
mesmo dia. Os pedidos ALTA_DEMANDA foram criados entre 09:00 e 09:23. Os dez
pedidos NORMAL são a massa legada, criada entre 26 e 29/10; o início das
simulações foi posterior a todas as criações.

## Execução dos cenários

Resultados de uma execução reproduzível do script:

| Cenário | Pedidos | Entregues | Atrasados / taxa | Cumprimento SLA | Tempo médio criação até entrega | Tempo médio após início da simulação | Distância | Distância por pedido |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NORMAL | 10 | 10 (100%) | 4 (40%) | 60% | 3.528,94 min | 65,44 min | 72.547 m | 7.254,7 m |
| ALTA_DEMANDA | 24 | 24 (100%) | 0 (0%) | 100% | 196,66 min | 148,16 min | 102.988 m | 4.291,2 m |
| EQUIDADE | 16 | 16 (100%) | 0 (0%) | 100% | 125,25 min | 87,75 min | 98.964 m | 6.185,3 m |

ALTA_DEMANDA contém 2,4 vezes o volume de NORMAL. Neste seed, ambos entregaram
100% dos pedidos; NORMAL teve taxa de atraso de 40% e cumprimento de SLA de
60%, enquanto ALTA_DEMANDA teve taxa de atraso de 0% e cumprimento de 100%.
Esses percentuais descrevem as massas cadastradas, não um experimento causal:
NORMAL contém pedidos mais antigos e prazos já vencidos para parte deles,
enquanto os 24 pedidos de ALTA_DEMANDA foram criados na manhã da simulação.
Por isso, também mostramos o tempo a partir do início da simulação. Ele é
maior em ALTA_DEMANDA, coerente com o maior volume e com o fator de trânsito,
mas inclui os tempos de serviço, filas e retornos, além dos deslocamentos.
O roteador do Cenário 2 usa fator 2.0; os testes verificam a duração da matriz
como exatamente duas vezes o tempo sem trânsito. Não atribuímos causalidade à
comparação de tempos médios entre massas distintas.

NORMAL teve atraso médio real de 2.130,45 min entre as entregas atrasadas. Seus
atrasos normalizados por bairro foram: Barra 0; Boca do Rio 0; Brotas 0,2653;
Comercio 1,5192; Itapua 0,0211; Pernambues 0; Pituba 2,0414; Rio Vermelho 0.
ALTA_DEMANDA não teve entregas atrasadas; todos os seus bairros registraram
atraso normalizado 0. O índice territorial real foi 2,5223 em NORMAL e 0 em
ALTA_DEMANDA e EQUIDADE. O indicador de atraso médio é nulo quando nenhuma
entrega atrasou.

Todos os pedidos foram distribuídos e entregues. Os dois entregadores
respeitaram limites de paradas, peso e volume em cada viagem. A contagem real
de entregas foi: NORMAL 6/4; ALTA_DEMANDA 10/14; EQUIDADE 7/9 (CAM-01/CAM-02).

## Comparação das estratégias em EQUIDADE

Os resultados abaixo documentam o experimento comparativo original da F09.5,
executado quando o seed de EQUIDADE ainda continha 16 pedidos. A referência
vigente passou a 15 pedidos; esses valores são históricos e não representam o
resultado atual com a massa atualizada.

Cada estratégia recebeu os mesmos 16 pedidos (fingerprint SHA-256
`ab70835fd29161b10b3a63628e30aeae34b7369255674c8ca648dd681d7b4aa4`),
dois entregadores com as mesmas capacidades, início, centro e roteamento
simulado sem fator fixo. Cada estratégia foi executada em um SQLite temporário
reinicializado a partir do mesmo seed; os fingerprints confirmam a mesma massa
de pedidos, sem alterar os dados originais.

| Estratégia | Entregues | Atrasados | Cumprimento SLA | Tempo criação até entrega | Atraso médio real | Atraso normalizado por bairro | Índice territorial | Distância total | Entregas por entregador |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| `insercao_mais_barata` | 16 | 0 | 100% | 125,25 min | — | 0 em todos os 8 bairros | 0 | 98.964 m | 7 / 9 |
| `ordem_da_fila` | 16 | 0 | 100% | 169,33 min | — | 0 em todos os 8 bairros | 0 | 193.980 m | 8 / 8 |
| `equidade_sla` | 16 | 0 | 100% | 125,25 min | — | 0 em todos os 8 bairros | 0 | 98.964 m | 7 / 9 |

Nenhuma estratégia teve atraso observado, então o SLA e as medidas territoriais
não distinguem seus resultados nesta massa. `equidade_sla` empatou com
`insercao_mais_barata`; não há evidência aqui de melhoria de equidade. A
`ordem_da_fila` entregou todos os pedidos, mas percorreu mais distância e
levou mais tempo médio. Isso mostra um custo operacional neste experimento,
sem afirmar que esse comportamento ocorrerá com outras massas.

O relatório não presume que a estratégia de equidade sempre vence. Para medir
diferenças territoriais, uma próxima massa de validação precisará produzir
atrasos observados em pelo menos parte dos bairros, sem alterar artificialmente
os dados atuais.

## Cobertura automatizada

`backend/tests/test_f09_validacao_integrada.py` verifica consulta e execução
dos três cenários, contagem e distribuição de pedidos, estratégia padrão,
roteador e fator por cenário, conclusão das entregas e respeito às capacidades.
Também executa as três estratégias com os mesmos parâmetros em EQUIDADE e
valida indicadores calculados sobre os resultados reais.

## Limitação do estado histórico

O endpoint `GET /api/simulacoes/{id}` depende da instância em memória. Depois
que ela é removida (como ocorre após reiniciar o backend), retorna HTTP 410;
os eventos e as consultas de auditoria continuam disponíveis no SQLite. O
experimento captura o estado final na resposta imediata de `POST /executar` e
usa eventos persistidos para conferir os horários de entrega. Assim, o HTTP 410
não impede as comparações nem sua repetição. O teste integrado também remove a
simulação do registro em memória e confirma a resposta 410 e a disponibilidade
dos eventos. Não foi necessário reconstruir o estado histórico nem alterar esse
comportamento nesta etapa.
