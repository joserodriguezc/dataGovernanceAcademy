"""Fixtures compartidos: un espacio de trabajo pequeño con el warehouse ya construido."""

import shutil

import pytest

from academy.core.synthetic import Scale, SyntheticConfig, generate, write_dataset
from academy.core.warehouse import build_warehouse
from academy.lessons.base import LessonContext
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


@pytest.fixture
def compute_lesson(small_workspace):
    """Ejecuta una lección con sus entradas por defecto sobre el warehouse pequeño.

    `stored` simula lo que el alumno ha editado en otras lecciones: (lección, spec) -> datos.
    """
    def run(lesson, stored=None, workspace=None):
        ws = workspace or small_workspace
        inputs = {s.id: s.model.model_validate(s.default()) for s in lesson.inputs}
        ctx = LessonContext(ws.db_path, ws.raw_dir, stored)
        return lesson.compute(inputs, ctx)
    return run


@pytest.fixture
def workspace_copy(small_workspace, tmp_path) -> Workspace:
    """Copia propia del warehouse pequeño, para las lecciones que escriben en él."""
    ws = Workspace(tmp_path / "copy")
    shutil.copytree(small_workspace.raw_dir, ws.raw_dir)
    shutil.copy(small_workspace.db_path, ws.db_path)
    return ws


def docs(sections) -> dict[str, str]:
    """Documentos Markdown de un resultado, por nombre de fichero."""
    return {b.filename: b.markdown for s in sections for b in s.blocks if b.type == "document"}
