# Contribuição ao projeto

## Branches

A branch `main` deve permanecer estável. Cada alteração deve ser feita em uma branch própria.

Padrões de nomes:

- `feature/F01-modelos-dominio`
- `feature/F03-fila-prioridade`
- `fix/F02-calculo-sla`
- `docs/F00-documentacao`
- `test/F03-testes-heap`

## Commits

Utilizamos Conventional Commits:

`tipo(escopo): descrição curta`

Tipos usuais:

- `feat`: nova funcionalidade.
- `fix`: correção de erro.
- `docs`: documentação.
- `test`: testes.
- `refactor`: reorganização interna sem alterar o comportamento esperado.
- `chore`: configuração ou manutenção.

Exemplos:

- `chore(F00): estrutura inicial do projeto`
- `feat(F03): implementa fila de prioridade com heap`
- `fix(F02): corrige cálculo do aging`
- `docs(F00): documenta instalação do projeto`

Escrever as descrições em português e de forma objetiva.

## Pull Requests

Antes de abrir um Pull Request:

1. Verificar se a aplicação continua iniciando.
2. Executar os testes pertinentes.
3. Revisar as próprias alterações.
4. Confirmar que arquivos `.env`, `node_modules`, ambientes virtuais e bancos locais não foram adicionados.
5. Descrever o que foi implementado, como testar e quais issues estão relacionadas.

Toda mudança deve passar por revisão antes de ser integrada à branch `main`.

## Colaboração

- Não desenvolver diretamente na `main`.
- Atualizar a branch com as mudanças recentes da `main` antes de concluir o trabalho.
- Evitar alterar módulos pertencentes a outra feature sem combinar.
- Registrar mudanças em contratos entre frontend, backend e domínio.
- Não enviar chaves de API ou outros segredos nos commits.
