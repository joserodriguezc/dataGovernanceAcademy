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


Compute = Callable[[dict[str, BaseModel]], list[ResultSection]]


@dataclass(frozen=True)
class LessonDef:
    number: int
    inputs: list[InputSpec]
    compute: Compute
    content_file: Path

    def content(self) -> LessonContent:
        return LessonContent.model_validate(load_yaml(self.content_file))

    def input_spec(self, input_id: str) -> InputSpec | None:
        return next((s for s in self.inputs if s.id == input_id), None)
