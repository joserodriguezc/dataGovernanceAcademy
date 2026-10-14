"""Bloques de resultado: el lenguaje común con el que cada lección describe sus resultados.

El frontend sabe dibujar cada tipo de bloque, así que una lección nueva no necesita código
de interfaz propio: su `compute` devuelve secciones con bloques.
"""

from datetime import date, datetime
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


class BarItem(BaseModel):
    label: str
    value: float
    display: str  # valor ya formateado
    target: float | None = None  # umbral u objetivo, dibujado como una marca
    ok: bool | None = None  # cumple el objetivo (se muestra con icono y texto, no solo color)
    detail: str | None = None


class BarListBlock(BaseModel):
    """Barras horizontales con su objetivo: p. ej., registros válidos de cada regla."""

    type: Literal["bar_list"] = "bar_list"
    title: str
    subtitle: str | None = None
    items: list[BarItem]
    min_value: float = 0.0
    max_value: float = 1.0
    legend: str | None = None  # explica la escala y las marcas; si falta, porcentajes y umbral


class MatrixGroup(BaseModel):
    id: str
    label: str
    tone: Tone  # color y forma: good = círculo, info = cuadrado, bad = triángulo, warning = rombo


class MatrixPoint(BaseModel):
    x: float
    y: float
    label: str
    group: str
    detail: str | None = None


class QuadrantLabel(BaseModel):
    x: float
    y: float
    text: str


class MatrixBlock(BaseModel):
    """Matriz de dos ejes con cuadrantes, p. ej., influencia frente a interés."""

    type: Literal["matrix"] = "matrix"
    title: str
    subtitle: str | None = None
    x_label: str
    y_label: str
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    ticks: list[float] = []
    divider_x: float | None = None
    divider_y: float | None = None
    quadrants: list[QuadrantLabel] = []
    groups: list[MatrixGroup]
    points: list[MatrixPoint]


class HeatmapRow(BaseModel):
    label: str
    values: list[float | None]


class HeatmapBlock(BaseModel):
    """Mapa de calor con una sola rampa de color (más oscuro = más valor)."""

    type: Literal["heatmap"] = "heatmap"
    title: str
    subtitle: str | None = None
    columns: list[str]
    rows: list[HeatmapRow]
    min_value: float
    max_value: float


class TimelineItem(BaseModel):
    label: str
    group: str
    start: date
    end: date
    note: str | None = None


class TimelineBlock(BaseModel):
    """Barras en el tiempo, coloreadas por grupo, con la fecha de corte."""

    type: Literal["timeline"] = "timeline"
    title: str
    subtitle: str | None = None
    today: date | None = None
    groups: list[MatrixGroup]
    items: list[TimelineItem]


class DocumentBlock(BaseModel):
    type: Literal["document"] = "document"
    title: str
    filename: str
    markdown: str


Block = Annotated[
    KpisBlock | CalloutBlock | TableBlock | LineChartBlock | BarListBlock | MatrixBlock
    | HeatmapBlock | TimelineBlock | DocumentBlock,
    Field(discriminator="type"),
]


class ResultSection(BaseModel):
    title: str
    blocks: list[Block]


class LessonResult(BaseModel):
    lesson: int
    ran_at: datetime
    sections: list[ResultSection]
