# Sovereign Swarm v2

Modular Multi-Agent OS — 45 modules, swarm intelligence, safety council, economic engine.

## Architecture

```
sovereign_swarm/
├── agents/          # Agent profiles, spawning, orchestration
├── infra/           # Bus, memory, scheduling, telemetry
├── intelligence/    # LLM clients, routing, ranking
├── protocols/       # MCP, A2A, swarm bus protocol
├── safety/          # Council, audit, budget, thermal
├── config.py        # Central configuration
├── cli.py           # REPL + command interface
└── __main__.py      # Entry point
```

## Test Suite

33 tests across unit, stress, fuzz, safety, integration, and adversarial suites.

```bash
cd /path/to/repo
python3 -m sovereign_swarm.tests
```

## Entrypoints

- `python3 -m sovereign_swarm` — launch the REPL
- `swarm-repl` — CLI command (after `pip install`)

## License

MIT
