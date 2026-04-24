# Changelog

## v2.1.0 — Health, Evolution, Build

### Added
- **Health module** (`sovereign_swarm.health`) — `HealthController` with load tracking, overload threshold, auto-unhealthy flagging, rebalance candidates
- **Speciation** (`EvolutionEngine.speciate()`) — group agents into species by strategy
- **Wheel build** — `sovereign_swarm-2.1.0-py3-none-any.whl`

### Enhanced
- **SCALE test** — 100 agents in 0.2ms, 500 bus messages in 21s
- **ATTACK test** — 1000 fuzz inputs in 56ms, 7/10 injection blocked, adaptive rules learned
- **EVOLVE test** — 5 generations, 3 species speciated
- **PROTOCOL test** — 12 MCP tools with schema + handle + register
- **HEAL test** — retry on timeout, degrade on rate-limit, circuit breaker on repeated failures

## v2.0.0 — Modular Release

### Added
- README, LICENSE, CHANGELOG, CI
- `.gitignore`, badges, entrypoints

### Fixed
- Event loop leak, REPL signal handler, version strings
