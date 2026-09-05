# InventoryBallast (inventory_optimizer)

Portable, solver-neutral securities-lending inventory optimization engine.

This package is specified by [`specs/spec002/`](specs/spec002/). Extracted from the
`QR-Haven` monorepo (`projects/inventory_optimizer/`, preserving its original commit
history) into its own repository, per Spec002's own design goal of independent
extractability. Its core modules must never import `qr_haven`.

This repository also adopts the [QuantSmith](https://github.com/joshualutkemuller/QuantSmith)
agentic scaffold (`instructions/`, `hooks/`, `agents/`, `prompts/`, `templates/`) — see
`CLAUDE.md` and `docs/handoff.md`.

## Status

T01-T10, T34, and the `securities_lending_inventory` baseline of T35 are implemented and
tested. T11 (result/attribution) and T12 (public API/CLI) are next — see
[`docs/handoff.md`](docs/handoff.md) for the current pick-up point, `specs/spec002/00_PLAN.md`
and `specs/spec002/01_SPEC.md` for the full specification, and
`specs/spec002/TRACEABILITY.md` for requirement-to-evidence mapping.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,highs,dataframe,agentic]"
.venv/bin/python -m pytest tests/ -q
```

`highs` is required for the full test suite (`solvers/highs.py` and its tests
import `highspy`); `agentic` pulls in the `quantsmith` package (see
`docs/handoff.md` for what it's useful for here). Drop either extra for a
lighter install if you only need a subset.

## Boundary rule

Nothing under `src/inventory_optimizer/` may import `qr_haven` or any QR Haven-specific module.
`scripts/verify_portability.py` enforces this with `qr_haven` removed from `PYTHONPATH`.
