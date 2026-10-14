"""Bloques de resultado: el lenguaje común con el que cada lección describe sus resultados.

El frontend sabe dibujar cada tipo de bloque, así que una lección nueva no necesita código
de interfaz propio: su `compute` devuelve secciones con bloques.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Tone = Literal["info", "good", "warning", "bad"]


class Kpi(BaseModel):
    label: str
    value: str
    detail: str | None = None
    tone: Tone | None = None


class KpisBlock(BaseModel):
    type: Literal["kpis"] = "kpis"
    items: list[Kpi]


class CalloutBlock(BaseModel):
    type: Literal["callout"] = "callout"
    tone: Tone = "info"
    title: str
    text: str


class Column(BaseModel):
    key: str
    label: str
    align: Literal["left", "right"] = "left"


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str
    description: str | None = None
    columns: list[Column]
    rows: list[dict[str, Any]]  # valores ya formateados para mostrar


class Series(BaseModel):
    name: str
    points: list[tuple[float, float]]
    emphasis: bool = False


class Marker(BaseModel):
    series: str
    x: float
    y: float
    label: str


class LineChartBlock(BaseModel):
    type: Literal["line_chart"] = "line_chart"
    title: str
    subtitle: str | None = None
    x_label: str
    y_label: str
    series: list[Series]
    markers: list[Marker] = []
    reference_y: float | None = None  # línea horizontal de referencia (p. ej., 0)


class DocumentBlock(BaseModel):
    type: Literal["document"] = "document"
    title: str
    filename: str
    markdown: str


Block = Annotated[KpisBlock | CalloutBlock | TableBlock | LineChartBlock | DocumentBlock,
                  Field(discriminator="type")]


class ResultSection(BaseModel):
    title: str
    blocks: list[Block]


class LessonResult(BaseModel):
    lesson: int
    ran_at: datetime
    sections: list[ResultSection]
