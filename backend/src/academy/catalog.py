"""Catálogo de lecciones: una por capítulo del libro, cargado de lessons.yaml."""

from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

CATALOG_FILE = Path(__file__).with_name("lessons.yaml")


class Lesson(BaseModel):
    number: int = Field(ge=1)
    slug: str
    title: str
    book_title: str
    part: int
    kind: Literal["gestion", "tecnico", "caso"]
    project: str
    summary: str
    recommended: list[int] = []
    status: Literal["available", "planned"] = "planned"
    requires_warehouse: bool = False  # necesita los datos de NovaMercado construidos


class Catalog(BaseModel):
    parts: dict[int, str]
    lessons: list[Lesson]

    @model_validator(mode="after")
    def check(self) -> "Catalog":
        numbers = [lesson.number for lesson in self.lessons]
        if numbers != sorted(set(numbers)):
            raise ValueError("los números de lección deben ser únicos y estar en orden")
        for lesson in self.lessons:
            if lesson.part not in self.parts:
                raise ValueError(f"lección {lesson.number}: parte {lesson.part} desconocida")
            # Solo se recomienda lo anterior: así el orden del libro no tiene ciclos.
            bad = [n for n in lesson.recommended if n not in numbers or n >= lesson.number]
            if bad:
                raise ValueError(f"lección {lesson.number}: recomendaciones inválidas {bad}")
        return self

    def get(self, number: int) -> Lesson | None:
        return next((lesson for lesson in self.lessons if lesson.number == number), None)


@cache
def load_catalog(path: Path = CATALOG_FILE) -> Catalog:
    return Catalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
