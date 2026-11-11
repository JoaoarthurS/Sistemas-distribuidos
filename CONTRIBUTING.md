# Como contribuir

## Fluxo de branches (Git Flow)

| Branch | Para quê | Nasce de | Volta para |
|---|---|---|---|
| `main` | versões entregues; cada merge recebe uma tag `vX.Y.Z` | — | — |
| `develop` | integração do trabalho em andamento | `main` | — |
| `feature/<nome>` | uma funcionalidade ou refatoração | `develop` | `develop` |
| `release/<versão>` | preparação de uma entrega (versão, changelog, ajustes finais) | `develop` | `main` e `develop` |
| `hotfix/<versão>` | correção urgente de uma versão entregue | `main` | `main` e `develop` |

Os merges usam `--no-ff`, para que o histórico mostre cada branch como um
bloco. Branches de feature, release e hotfix são apagadas depois do merge.

```bash
# nova funcionalidade
git switch develop
git switch -c feature/minha-funcionalidade
# ... commits ...
git switch develop
git merge --no-ff feature/minha-funcionalidade
git branch -d feature/minha-funcionalidade

# entrega
git switch -c release/1.1.0 develop
# ... atualizar CHANGELOG.md e versões ...
git switch main && git merge --no-ff release/1.1.0 && git tag -a v1.1.0 -m "Versão 1.1.0"
git switch develop && git merge --no-ff release/1.1.0
git branch -d release/1.1.0
```

Quem tiver a extensão [git-flow](https://github.com/petervanderdoes/gitflow-avh)
pode usar os atalhos equivalentes (`git flow feature start ...`). O
repositório já está configurado com `main`/`develop` e o prefixo de tag `v`.

## Mensagens de commit

Padrão [Conventional Commits](https://www.conventionalcommits.org/pt-br/), em
português, no imperativo:

```
<tipo>(<escopo>): <resumo em até ~70 caracteres>

<corpo opcional: o porquê da mudança>
```

Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `build`.
Escopos usados: `common`, `server`, `painel`, `bot`, `cliente`, `certs`,
`testes`, `docs`.

## Antes de abrir o merge

```bash
python -m unittest discover -s tests/unit
python tests/integration/test_integration.py
cd client && npm test
```

Todos devem passar. Mudanças no protocolo exigem atualizar
[docs/PROTOCOLO.md](docs/PROTOCOLO.md) e os dois lados (Python e Node.js).
