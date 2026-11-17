from __future__ import annotations

import json
from pathlib import Path

from sistema_incendios_forestales.api.app import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_PATH = PROJECT_ROOT / "contracts" / "openapi.json"


def main() -> None:
    CONTRACTS_PATH.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI contracts exported to {CONTRACTS_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
