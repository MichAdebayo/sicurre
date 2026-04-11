from __future__ import annotations

import runpy
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]


def run_legacy_script(relative_path: str) -> None:
    script_path = ROOT_DIR / relative_path
    if not script_path.exists():
        raise FileNotFoundError(f"Legacy script not found: {script_path}")
    runpy.run_path(str(script_path), run_name="__main__")
