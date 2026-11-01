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

## Princípio de organização

A lógica de domínio não deve depender do React, nem realizar chamadas HTTP diretamente para o Google Maps. As dependências externas devem ser encapsuladas em serviços e adaptadores próprios.
