# Sovereign Swarm v2

Modular Multi-Agent OS — swarm intelligence, safety councils, economic engines, and protocol bridges. 45 modules across 6 functional domains.

[![CI](https://github.com/sahiixx/sovereign-swarm-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/sahiixx/sovereign-swarm-v2/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Architecture

```
sovereign_swarm/
├── agents/          # Agent profiles, spawning, HITL, scheduling
├── infra/           # Event bus, memory, LLM client, platform detection
├── intelligence/    # Orchestration, routing, reputation, healing, evolution
├── protocols/       # MCP server, A2A cards, Hermes messenger, OpenClaw gateway
├── safety/          # Safety council, audit, budget, observe, alerts
├── cli.py           # CLI entrypoint (--seed, --repl, --test)
├── repl.py          # Interactive REPL with 15+ commands
├── tests.py         # 33 tests across 6 suites
└── config.py        # Shared config, optional deps
```

## Install

```bash
git clone https://github.com/sahiixx/sovereign-swarm-v2.git
cd sovereign-swarm-v2
pip install .          # core only
pip install ".[all]"   # aiohttp + pydantic + prometheus
```

## CLI Usage

```bash
python -m sovereign_swarm --seed --repl    # bootstrap + interactive shell
python -m sovereign_swarm --test all       # run full test suite
swarm-test                                  # pip-installed entrypoint
```

## REPL Commands

- `spawn <name>` — spawn specialist agent
- `hermes` — protocol messenger status
- `oc` — OpenClaw gateway status
- `ollama` — LLM healthcheck
- `metrics` — swarm metrics
- `mcp tools` — list MCP tools
- `memory search <q>` — semantic memory search
- `platform` — platform + model recommendation
- `battery` / `thermal` — hardware monitoring
- `reputation` / `economics` — agent scores + ROI
- `backup` — create snapshot
- `kill` — arm kill switch
- `help` / `exit`

## Tests

```bash
python -m sovereign_swarm --test all
```

| Suite         | Tests | Description                        |
|---------------|-------|------------------------------------|
| Unit          | 11    | Bus, routing, safety, memory, LLM  |
| Stress        | 2     | 20-msg burst, 16-agent routing     |
| Fuzz          | 1     | 100 random safety scans            |
| Safety        | 7     | rm -rf, mkfs, eval, emergency mode |
| Integration   | 5     | Pipeline, HITL, persistence        |
| Adversarial   | 7     | Prompt injection, collusion, healing |

## Key Modules

- **SwarmBus** — async SQLite-backed event bus
- **MetaOrchestrator** — trust/latency/cost-weighted agent routing
- **SafetyCouncil** — adaptive rule blocking with emergency mode
- **HealEngine** — cascading-failure auto-heal with circuit breakers
- **EconomicEngine** — ROI tracking + cost prediction
- **EvolutionEngine** — agent trait evolution + speciation

## License

MIT © Sahil Khan
