"""Fixtures compartidos: un espacio de trabajo pequeño con el warehouse ya construido."""

import pytest

from academy.core.synthetic import Scale, SyntheticConfig, generate, write_dataset
from academy.core.warehouse import build_warehouse
from academy.workspace import Workspace

SMALL_SCALE = Scale(persons=300, products=60, suppliers=20, stores=5, pos_lines=2000,
                    ecom_lines=800)


@pytest.fixture(scope="session")
def small_workspace(tmp_path_factory) -> Workspace:
    """Warehouse pequeño y determinista, construido una sola vez por sesión.

    Se construye a mano (sin Workspace.build) para usar la escala pequeña; solo sirve para
    las lecciones, que leen db_path y raw_dir.
    """
    ws = Workspace(tmp_path_factory.mktemp("data"))
    write_dataset(generate(SyntheticConfig(scale=SMALL_SCALE)), ws.raw_dir)
    build_warehouse(ws.db_path, ws.raw_dir)
    return ws
