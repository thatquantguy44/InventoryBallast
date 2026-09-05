"""E1 end-to-end CLI test (T12; specs/0003-public-api-cli/; 01_SPEC.md's Section 26 Task Matrix
names "end-to-end JSON test" as T12's own evidence; specs/spec002/TRACEABILITY.md's `PLT-002` row
names "end-to-end golden test" -- this is that evidence).

Invokes the real *installed* ``inventory-optimizer`` console script via ``subprocess.run`` (after
``pip install -e .``), not an in-process ``cli.main(argv)`` call -- proving the
``[project.scripts]`` wiring itself works, which ``tests/unit/test_cli.py``'s in-process calls
cannot.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_CONSOLE_SCRIPT = Path(sys.executable).parent / "inventory-optimizer"


@pytest.mark.skipif(
    not _CONSOLE_SCRIPT.exists(),
    reason="inventory-optimizer console script not installed (pip install -e . first)",
)
def test_e1_optimize_via_installed_console_script(tmp_path, e1_request) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(e1_request.model_dump_json())
    output_path = tmp_path / "result.json"

    completed = subprocess.run(
        [
            str(_CONSOLE_SCRIPT),
            "optimize",
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output_path.read_text())
    assert result["status"] == "optimal"
    assert result["verification"]["passed"] is True
    assert len(result["allocations"]) == 2
