"""Carga de ficheros de configuración (inputs YAML de los capítulos)."""

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    """Lee un YAML en UTF-8 y devuelve su contenido como estructuras de Python."""
    with Path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
