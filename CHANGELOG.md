# Changelog

## v2.0.0 — Modular Release

### Added
- README.md with architecture diagram and badges
- MIT LICENSE
- GitHub Actions CI across Python 3.10/3.11/3.12
- `.gitignore` for data files and build artifacts
- CI badge on README

### Fixed
- Async event loop leak in tests (`asyncio.run` everywhere)
- REPL signal handler calling `sys.exit()` inside signal handler
- KeyboardInterrupt not caught in REPL
- Version strings updated v1.4 → v2.0 across CLI and REPL

## v2.0.0-pre — Modularization

### Changed
- Monolith (`sovereign_swarm_v14.py`, 1437 lines) → 32 modules
- `pyproject.toml` with `swarm-repl` and `swarm-test` entrypoints
- 33 tests across unit, stress, fuzz, safety, integration, adversarial
