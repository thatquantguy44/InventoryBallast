# inventory_optimizer

Portable, solver-neutral securities-lending inventory optimization engine.

This package is specified by `specs/spec002/` in the parent QR Haven repository. It is designed to
be independently installable and eventually extractable into its own repository: its core modules
must never import `qr_haven`.

## Status

Phase 0A (scaffold + E1-vertical contracts) is in progress. See `specs/spec002/00_PLAN.md` and
`specs/spec002/01_SPEC.md` in the parent repository for the full specification, and
`specs/spec002/TRACEABILITY.md` for requirement-to-evidence mapping.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Boundary rule

Nothing under `src/inventory_optimizer/` may import `qr_haven` or any QR Haven-specific module.
`scripts/verify_portability.py` enforces this with `qr_haven` removed from `PYTHONPATH`.
