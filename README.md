# InventoryBallast (inventory_optimizer)

Portable, solver-neutral securities-lending inventory optimization engine.

This package is specified by [`specs/engine_spec/`](specs/engine_spec/). Extracted from the
`QR-Haven` monorepo (`projects/inventory_optimizer/`, preserving its original commit
history) into its own repository, per Engine Spec's own design goal of independent
extractability. Its core modules must never import `qr_haven`.

This repository also adopts the [QuantSmith](https://github.com/joshualutkemuller/QuantSmith)
agentic scaffold (`instructions/`, `hooks/`, `agents/`, `prompts/`, `templates/`) — see
`CLAUDE.md` and `docs/handoff.md`.

## Status

T01-T10, T34, and the `securities_lending_inventory` baseline of T35 are implemented and
tested. T11 (result/attribution) and T12 (public API/CLI) are next — see
[`docs/handoff.md`](docs/handoff.md) for the current pick-up point, `specs/engine_spec/00_PLAN.md`
and `specs/engine_spec/01_SPEC.md` for the full specification, and
`specs/engine_spec/TRACEABILITY.md` for requirement-to-evidence mapping.

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

## Tabular output

`inventory-optimizer tables` flattens a saved `optimize`/`scenarios` result into one CSV per table
(no extras required — the CSV path is standard library only):

```bash
inventory-optimizer optimize --request request.json --output result.json
inventory-optimizer tables --input result.json --output-dir ./tables --kind result
```

`--kind` is `result` (default), `scenarios`, or `stress`, matching what `--input` holds.
`--run-summary-layout wide|long` (default `wide`) selects one summary row per run, or long
`run_id`/`key`/`value` pairs for appending many runs into one frame. For a pandas `DataFrame`
instead of CSV, install the `dataframe` extra and call `adapters.dataframe.to_dataframe(table)`
directly — `reporting.tables` builds the `Table` objects either output format reads from.

**Table names and column order are a contract** (consumers index by them): the full, normative
list of every table and its columns lives in
[`specs/0008-tabular-result-output/plan.md`](specs/0008-tabular-result-output/plan.md)'s "Table
catalogue" section. Changing a name or column is a breaking change, not a rename.

## Boundary rule

Nothing under `src/inventory_optimizer/` may import `qr_haven` or any QR Haven-specific module.
`scripts/verify_portability.py` enforces this with `qr_haven` removed from `PYTHONPATH`.
