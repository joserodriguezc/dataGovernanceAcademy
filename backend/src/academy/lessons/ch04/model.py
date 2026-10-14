"""Modelo de madurez y configuración de la evaluación (pasos #1, #3, #6, #7 y #10)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from academy.core.company import DATA_DOMAINS

DATA_OFFICE = "data_office"
MAX_PLAN_ITEMS = 5


class Level(BaseModel):
    name: str
    description: str


class Dimension(BaseModel):
    id: str
    short: str
    name: str
    chapter: int
    questions: list[str] = Field(min_length=1)


class MaturityModel(BaseModel):
    name: str
    version: str
    levels: dict[int, Level]
    dimensions: list[Dimension] = Field(min_length=1)

    @model_validator(mode="after")
    def _consecutive_levels(self) -> "MaturityModel":
        if sorted(self.levels) != list(range(1, len(self.levels) + 1)):
            raise ValueError("los niveles deben ser 1, 2, …, N")
        return self

    @property
    def min_level(self) -> int:
        return min(self.levels)

    @property
    def max_level(self) -> int:
        return max(self.levels)

    def dimension(self, dim_id: str) -> Dimension:
        return next(d for d in self.dimensions if d.id == dim_id)


class Scope(BaseModel):
    type: Literal["enterprise", "pilot", "rolling"]
    domains: list[str] = Field(min_length=1)
    include_data_office: bool = True

    @field_validator("domains")
    @classmethod
    def _known(cls, value: list[str]) -> list[str]:
        unknown = set(value) - set(DATA_DOMAINS)
        if unknown:
            raise ValueError(f"dominios desconocidos: {sorted(unknown)}")
        return value

    @property
    def units(self) -> list[str]:
        """Unidades evaluadas: los dominios y, si procede, la oficina de datos."""
        return [*self.domains, *([DATA_OFFICE] if self.include_data_office else [])]

    @property
    def missing_domains(self) -> list[str]:
        return [d for d in DATA_DOMAINS if d not in self.domains]


class Phase(BaseModel):
    name: str
    weeks: int | None
    steps: list[int]


class Simulation(BaseModel):
    seed: int
    domain_base: dict[str, float]
    dimension_adjust: dict[str, float]
    self_bias: dict[str, float]
    noise: float = Field(ge=0)


class Finding(BaseModel):
    text: str
    theme: str
    dimension: str
    domains: list[str]
    root_cause: str
    priority: int = Field(ge=1, le=3)


class PlanItem(BaseModel):
    initiative: str
    theme: str
    dimensions: list[str] = Field(min_length=1)
    owner: str
    start: str
    end: str
    funding_usd: float = Field(ge=0)
    metric: str
    baseline_indicator: str | None
    target: float


class Trigger(BaseModel):
    event: str
    action: str


class Reassessment(BaseModel):
    frequency_months: int = Field(gt=0)
    triggers: list[Trigger]


class SuccessMeasure(BaseModel):
    measure: str
    value: str | None = None


class AssessmentInput(BaseModel):
    assessment_year: int
    scope: Scope
    data_office_participants: list[str]
    one_on_one_first: list[str]
    phases: list[Phase]
    start_date: date
    hours_per_participant: float = Field(gt=0)
    communication: Literal["aggregated", "disaggregated"]
    target_level: int
    simulation: Simulation
    bias_threshold: float = Field(gt=0)
    findings: list[Finding]
    plan: list[PlanItem] = Field(max_length=MAX_PLAN_ITEMS)
    reassessment: Reassessment
    success_measures: list[SuccessMeasure]

    @model_validator(mode="after")
    def _plan_tied_to_findings(self) -> "AssessmentInput":
        themes = {f.theme for f in self.findings}
        orphan = [p.initiative for p in self.plan if p.theme not in themes]
        if orphan:
            raise ValueError(f"iniciativas sin un tema de los hallazgos: {orphan}")
        steps = sorted(s for p in self.phases for s in p.steps)
        if steps != list(range(1, 11)):
            raise ValueError("las fases deben cubrir exactamente los pasos 1 a 10")
        return self

    def check_against(self, model: MaturityModel) -> None:
        """Valida las referencias a dimensiones y niveles del modelo."""
        dims = {d.id for d in model.dimensions}
        used = {f.dimension for f in self.findings} | {d for p in self.plan for d in p.dimensions}
        used |= set(self.simulation.dimension_adjust)
        if used - dims:
            raise ValueError(f"dimensiones desconocidas: {sorted(used - dims)}")
        if not model.min_level <= self.target_level <= model.max_level:
            raise ValueError("el nivel objetivo está fuera de la escala del modelo")
        missing = set(self.scope.units) - set(self.simulation.domain_base)
        if missing:
            raise ValueError(f"falta el nivel base simulado de: {sorted(missing)}")
