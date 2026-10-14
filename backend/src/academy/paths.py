"""Rutas del proyecto. `ACADEMY_DATA_DIR` permite cambiar dónde se guarda el estado local."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("ACADEMY_DATA_DIR", ROOT / "data"))
FRONTEND_DIST = ROOT / "frontend" / "dist"
