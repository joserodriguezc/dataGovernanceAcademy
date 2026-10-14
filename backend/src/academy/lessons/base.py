"""Definición de una lección interactiva: entradas editables, cálculo y contenido."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from academy.blocks import ResultSection
from academy.core.config import load_yaml


@dataclass(frozen=True)
class InputSpec:
    """Una entrada de la lección: un modelo pydantic con sus valores por defecto en YAML."""

    id: str
    title: str
    description: str
    model: type[BaseModel]
    default_file: Path

    def default(self) -> dict[str, Any]:
        return self.model.model_validate(load_yaml(self.default_file)).model_dump(mode="json")


class Idea(BaseModel):
    idea: str  # idea del capítulo, con palabras propias
    application: str  # cómo se aplica en la lección


class Challenge(BaseModel):
    title: str
    steps: list[str]
    look_for: str  # qué debería observar el alumno


class LessonContent(BaseModel):
    intro: str
    ideas: list[Idea]
    takeaways: list[str] = []
    challenges: list[Challenge] = []
    labels: dict[str, str] = {}  # etiquetas de los campos del formulario


@dataclass(frozen=True)
class LessonContext:
    """Lo que una lección necesita del entorno.

    - El warehouse y los datos de NovaMercado (lecciones técnicas).
    - Las entradas de otras lecciones tal como las ha dejado el alumno: si edita los
      stakeholders en la lección 2, la lección 5 los usa así.
    """

    db_path: Path | None = None
    raw_dir: Path | None = None
    stored_input: Callable[[int, "InputSpec"], dict[str, Any]] | None = None

    def input_of(self, lesson: int, spec: "InputSpec") -> BaseModel:
        """Entrada `spec` de la lección `lesson`: la editada o, si no hay, la de por defecto."""
        data = self.stored_input(lesson, spec) if self.stored_input else spec.default()
        return spec.model.model_validate(data)


Compute = Callable[[dict[str, BaseModel], LessonContext], list[ResultSection]]


@dataclass(frozen=True)
class LessonDef:
    number: int
    inputs: list[InputSpec]
    compute: Compute
    content_file: Path
    requires_warehouse: bool = False

    def content(self) -> LessonContent:
        return LessonContent.model_validate(load_yaml(self.content_file))

    def input_spec(self, input_id: str) -> InputSpec | None:
        return next((s for s in self.inputs if s.id == input_id), None)
