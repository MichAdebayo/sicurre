"""Generate or verify the checked-in OpenAPI contract from FastAPI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "api" / "openapi.yaml"
sys.path.insert(0, str(SOURCE_ROOT))

from data_platform.api.main import create_app  # noqa: E402


def generated_openapi() -> dict[str, Any]:
    """Return a recursively ordered, JSON-compatible runtime contract."""
    document = create_app().openapi()
    return json.loads(json.dumps(document, ensure_ascii=False, sort_keys=True))


def render_openapi(document: dict[str, Any]) -> str:
    """Serialize one deterministic, human-readable OpenAPI YAML document."""
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )


def check_openapi(output: Path) -> bool:
    """Return whether the checked-in document exactly matches the runtime."""
    if not output.exists():
        return False
    published = yaml.safe_load(output.read_text(encoding="utf-8"))
    return published == generated_openapi()


def parse_args() -> argparse.Namespace:
    """Parse generation and drift-check command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when the contract is stale")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    """Generate the contract or report deterministic drift."""
    args = parse_args()
    output = args.output.resolve()
    if args.check:
        if check_openapi(output):
            print(f"OpenAPI contract is current: {output}")
            return 0
        print(
            "OpenAPI contract is stale. Run `make openapi` and commit the result.",
            file=sys.stderr,
        )
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_openapi(generated_openapi()), encoding="utf-8")
    print(f"Generated OpenAPI contract: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
