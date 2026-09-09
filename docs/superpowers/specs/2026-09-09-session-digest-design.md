# session-digest — design

**Data:** 2026-09-09
**Status:** aprovado, pronto para plano de implementação

## Problema

Sessões de Claude Code produzem conhecimento — decisões, causas raiz, correções do
usuário, invariantes descobertos — que morre no transcrito. Os `.jsonl` em
`~/.claude/projects/` são um banco write-only: ninguém relê 240 MB de sessão.

O sintoma concreto que originou este plugin: um vault de conhecimento com sync
automático para o GitHub funcionando perfeitamente, alimentado por 55 sessões ao
longo de dois meses, ficou dois meses sem uma única nota nova. O sync era
automático; escrever a nota dependia de julgamento humano, e o julgamento falhou.

**A lição que o desenho encapsula:** o que depende de alguém lembrar não acontece.

## Objetivo

Transformar transcritos de sessão em conhecimento durável, automaticamente,
roteado por tipo:

- **Aprendizado técnico** (gotcha, invariante, "faça X e não Y neste codebase")
  vai para o **repo** onde o trabalho aconteceu — `docs/`, `CLAUDE.md`, ou a
  skill do próprio projeto. É lá que a próxima sessão, de qualquer pessoa, vai
  encontrar.
- **Narrativa de projeto** (linha do tempo, decisões e seu porquê, pendências,
  correções que o usuário fez) vai para a **base de conhecimento** configurada —
  um vault de notas, um diretório de markdown, o que o usuário apontar.

## Não-objetivos

- Não substitui documentação escrita à mão; destila o que de outra forma se perde.
- Não faz push. Escrever arquivo é reversível, publicar não é.
- Não arquiva transcrito bruto. O valor está na síntese, não no despejo.
- Não gerencia o sync git da base de conhecimento. Isso é do usuário.

## Arquitetura

Duas peças com fronteira clara, no mesmo repo:

```
session-digest/
├── .claude-plugin/
│   ├── marketplace.json
│   └── plugin.json
├── scripts/
│   └── session_digest/        # o CLI Python — a parte mecânica
├── skills/
│   └── session-digest/
│       ├── SKILL.md           # o julgamento
│       └── templates/         # esqueletos de nota (forma, não julgamento)
├── docs/
└── tests/
```

**A fronteira:** o que é determinístico e testável com fixture vive no Python. O
que exige ler conteúdo e julgar vive na skill. Configuração e forma não são
nenhum dos dois — são dados.

### Por que dois filtros, e não um

O Python **não decide substância**. Substância é semântica; script não lê
sentido. O que o Python faz é descarte barato do obviamente vazio, com métrica
objetiva:

| Sinal | Uso |
|---|---|
| Turnos do usuário | Sessão de 2 turnos raramente tem o que registrar |
| Houve Write/Edit | Sessão sem escrita costuma ser consulta |
| Houve commit | Sinal forte de entrega concreta |
| Tamanho do transcrito | Piso mínimo |

Isso mata "qual o path desse arquivo?" sem gastar um token. O **agente** faz o
julgamento de verdade, porque é quem vê o conteúdo — e `nada a registrar` é
saída legítima dele: a marca d'água avança igual, sem escrever nota.

## Componentes

### CLI `session-digest` (Python)

| Comando | Responsabilidade |
|---|---|
| `scan` | Acha sessões acima da marca d'água, aplica o filtro barato, devolve candidatos agrupados por projeto (JSON) |
| `extract <projeto>` | Condensa `.jsonl` em texto legível, fatiado em blocos que cabem no contexto |
| `run` | Para cada candidato, chama `claude -p` uma vez com a skill e o material extraído |
| `install --schedule <cron>` | Escreve o job periódico: launchd no macOS, crontab no Linux |
| `uninstall` | Remove o job |

**Estado:** `~/.claude/state/session-digest.json`, uma marca d'água por projeto.
Avança **apenas** quando o agente retorna com sucesso. Estado de máquina, nunca
versionado.

### Skill `session-digest`

Carrega só o que Python não sabe fazer:

1. **Critério de substância** — decisão tomada, bug com causa raiz identificada,
   correção que o usuário fez, entrega concreta. Nada disso presente, não escreve.
2. **Regra de roteamento** — aprendizado técnico para o repo, narrativa para a base.
3. **Disciplina de atualização** — ler as notas atuais antes de escrever,
   atualizar em vez de recriar, deduplicar contra o que já está registrado.

Se o `SKILL.md` crescer, vira porta com folhas — o padrão do `dev` no
`claude-plugin`. Não é o caso na v1.

### Config `~/.claude/session-digest.json`

```json
{
  "knowledge_base": "~/notes",
  "schedule": "0 23 * * *",
  "commit": false,
  "projects": {
    "<dir-do-projeto-em-~/.claude/projects>": {
      "folder": "OpenRig",
      "repo": "~/Projetos/github.com/jpfaria/OpenRig"
    }
  }
}
```

`projects` é opcional: sem entrada explícita, o destino é derivado do cwd
codificado no nome do diretório de sessão, e a pasta na base recebe o basename
do repo.

**Nenhum caminho pessoal dentro da skill ou do código.** É o que o `skill-rules`
exige: skill é commitada e compartilhada, e qualquer coisa presa à máquina de
uma pessoa quebra em silêncio para todo mundo.

## Fluxo

```
cron/launchd
   └─> session-digest run
         ├─ scan          (Python: marca d'água + filtro barato)
         └─ por projeto candidato:
              ├─ extract  (Python: .jsonl → texto fatiado)
              ├─ claude -p com a skill
              │    ├─ lê notas atuais do repo e da base
              │    ├─ julga substância
              │    └─ escreve/atualiza, ou não escreve nada
              └─ marca d'água avança (só em sucesso)
```

Projetos são independentes: um pode rodar em paralelo com outro, e a falha de um
não afeta os demais.

## Segurança e falha

- **Nunca faz push.** Commit no repo do usuário é opt-in via `commit: true`, e
  desligado por padrão.
- **Lock por diretório** (`mkdir` atômico) impede duas rodadas concorrentes;
  lock com mais de N minutos é considerado órfão e limpo. Um `index.lock` órfão
  já congelou um repo do usuário por dois meses — o modo de falha é conhecido.
- **Falha aberta.** O job nunca bloqueia nada; erro vai para log próprio.
- **Idempotência por marca d'água:** morreu no meio, o projeto volta na rodada
  seguinte a partir de onde parou.
- **Conteúdo de transcrito é dado, não instrução.** A skill trata o material
  extraído como texto a resumir, nunca como comando a obedecer.

## Testes

- **Python:** fixtures de `.jsonl` sintético cobrindo marca d'água, métricas do
  filtro, agrupamento por projeto, fatiamento do extrator. Determinístico e rápido.
- **Instalador:** dry-run comparando o plist/crontab gerado com o esperado.
- **Skill:** baseline com subagente **antes** de escrever, conforme
  `superpowers:writing-skills` — gate obrigatório para autorar qualquer `SKILL.md`.
- **RED-first** em tudo, conforme `dev-rules`.

## Decisões e seus porquês

| Decisão | Porquê |
|---|---|
| Extrator determinístico separado do agente | O garimpo de arquivo é barato em script e caro em LLM; e vira testável |
| Filtro em dois estágios | Script corta o vazio por métrica; só o agente corta o irrelevante por sentido |
| Roteia repo vs base por tipo de achado | Aprendizado de repo numa base pessoal vira ilha que só uma pessoa lê |
| Agendado, não por fim de sessão | Uma passada por projeto por dia sintetiza melhor que três notas soltas da mesma tarefa |
| Cadência configurável | Diário é padrão, não lei |
| Nunca faz push | Escrever é reversível; publicar não é |
| Templates como arquivo, não como texto na skill | Forma é dado; a skill fica com o julgamento e não incha |

## Alternativas descartadas

- **Job chama `claude -p` e faz tudo** — o LLM gastaria turnos fazendo garimpo
  de arquivo que script faz de graça, e nada ficaria testável.
- **Hook `SessionEnd`** — roda em toda sessão, inclusive triviais, e fragmenta
  uma tarefa espalhada em três sessões em três entradas.
- **Job só enfileira, humano destila depois** — reintroduz exatamente a
  dependência de alguém lembrar, que é o problema que o plugin existe para
  resolver.

## Aberto para depois da v1

- Cadência por projeto em vez de global.
- Detecção de projeto sem entrada em `projects` e sem repo identificável.
- Consolidação periódica: reler as notas de um projeto e compactá-las.

## 2026-09-09 — Scheduling and invocation layers removed

The plugin's own scheduling (`installer.py`: a launchd plist on macOS, a
crontab entry elsewhere) and its own agent invocation (`runner.py`: build a
prompt, shell out to `claude -p`, parse the result into `DigestResult`) were
removed, along with `lock.py` — the directory lock that existed only to stop
two of the plugin's own scheduled runs from colliding — and the `install`,
`uninstall`, and `run` CLI subcommands that drove them.

The reason: Claude Code gained a native local scheduled-task facility. It
stores a task as a skill at `~/.claude/scheduled-tasks/<id>/SKILL.md` and
runs it as a real Claude Code session on the user's machine at the chosen
cadence. A scheduled task IS an agent session — it reads the
`session-digest` skill directly and can call `scan` and `extract` itself.
Every piece of machinery this plugin built to schedule itself and to invoke
an agent by subprocess became redundant the moment that facility existed:
redundant scheduling and invocation code in a public plugin still has to be
maintained, documented, and trusted, for a result the platform now provides
for free.

What did not change: `scan`, `extract`, `config.py`, `state.py` (including
`advance_watermark`, now called by the scheduled agent instead of by
`runner.py`), and the `session-digest` skill and its templates. The
two-stage filter this document describes — a script that discards the
obviously empty by objective signal, an agent that judges substance — is
still exactly how the tool works; only who schedules the agent and how it
gets invoked changed.
