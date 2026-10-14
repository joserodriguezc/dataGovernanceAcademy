"""Marco de resultados: resultado de negocio → capacidades → entregables → resultados de datos.

Las reglas que hacen fallar la validación son las estructurales: ids únicos, cada
resultado con capacidades, cada capacidad con entregables, métricas con responsable e
hitos coherentes. Lo que es mejorable pero no imposible (falta la firma del valor, una
capacidad sin componente de cultura, etc.) se devuelve como aviso.
"""

from collections import Counter
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Los cinco componentes de una capacidad de datos sólida
COMPONENTS = {
    "skills": "Habilidades y conocimiento",
    "processes": "Procesos y metodologías",
    "technology": "Tecnología y herramientas",
    "resources": "Recursos",
    "culture": "Cultura",
}
BARRIER_LABELS = {
    "culture": "Cultura o política de la organización",
    "funding": "Cambios o dificultades de financiación",
    "sponsor_turnover": "Rotación del sponsor",
    "lack_of_support": "Falta de apoyo",
    "technical_expertise": "Falta de experiencia técnica",
    "regulatory_economic": "Cambios regulatorios o económicos",
}


class Deliverable(BaseModel):
    id: str
    name: str
    start: date
    due: date
    done: int = Field(ge=0)
    total: int = Field(gt=0)
    data_outcome: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "Deliverable":
        if self.done > self.total:
            raise ValueError(f"{self.id}: hecho ({self.done}) mayor que el total ({self.total})")
        if self.due < self.start:
            raise ValueError(f"{self.id}: la fecha de entrega es anterior al inicio")
        return self

    @property
    def complete(self) -> bool:
        return self.done == self.total

    def overdue(self, as_of: date) -> bool:
        return not self.complete and self.due < as_of


class Capability(BaseModel):
    id: str
    name: str
    why: str = Field(min_length=1)  # paso 2: explicar por qué es la capacidad adecuada
    components: dict[str, str | None] = Field(default_factory=dict)
    deliverables: list[Deliverable] = Field(min_length=1)

    @property
    def missing_components(self) -> list[str]:
        return [label for key, label in COMPONENTS.items() if not self.components.get(key)]


class Signoff(BaseModel):
    by: str
    date: date


class BusinessMetric(BaseModel):
    name: str
    unit: Literal["usd", "hours", "pct", "count"]
    baseline: float
    target: float
    actual: float | None = None
    higher_is_better: bool
    owner: str = Field(min_length=1)

    @model_validator(mode="after")
    def _direction(self) -> "BusinessMetric":
        better = self.target > self.baseline if self.higher_is_better else (
            self.target < self.baseline)
        if not better:
            raise ValueError(f"«{self.name}»: el objetivo no mejora la línea base")
        return self

    @property
    def progress(self) -> float:
        """Avance desde la línea base hacia el objetivo (0 = base, 1 = objetivo)."""
        if self.actual is None:
            return 0.0
        return (self.actual - self.baseline) / (self.target - self.baseline)


class Outcome(BaseModel):
    id: str
    stakeholder: str
    goal: str
    business_outcome: str
    deadline: date
    equity_lines: list[str] = Field(min_length=1)
    signoff: Signoff | None = None
    business_metric: BusinessMetric
    capabilities: list[Capability] = Field(min_length=1)

    @property
    def deliverables(self) -> list[Deliverable]:
        return [d for c in self.capabilities for d in c.deliverables]

    @property
    def milestone_progress(self) -> float:
        ds = self.deliverables
        return sum(d.done for d in ds) / sum(d.total for d in ds)


class DataOutcomeMetric(BaseModel):
    indicator: str
    target: float
    higher_is_better: bool


class Barrier(BaseModel):
    type: Literal["culture", "funding", "sponsor_turnover", "lack_of_support",
                  "technical_expertise", "regulatory_economic"]
    outcomes: list[str] = Field(min_length=1)
    description: str
    likelihood: int = Field(ge=1, le=3)
    impact: int = Field(ge=1, le=3)
    mitigation: str = Field(min_length=1)

    @property
    def severity(self) -> int:
        return self.likelihood * self.impact


class Qbr(BaseModel):
    quarter_label: str
    quarter_start: date
    quarter_end: date
    enterprise_services: list[str]


class OutcomeFramework(BaseModel):
    as_of: date
    outcomes: list[Outcome] = Field(min_length=1)
    data_outcome_metrics: dict[str, DataOutcomeMetric] = Field(default_factory=dict)
    barriers: list[Barrier] = Field(default_factory=list)
    qbr: Qbr

    @model_validator(mode="after")
    def _check_ids(self) -> "OutcomeFramework":
        ids = ([o.id for o in self.outcomes]
               + [c.id for o in self.outcomes for c in o.capabilities]
               + [d.id for o in self.outcomes for d in o.deliverables])
        dupes = [k for k, n in Counter(ids).items() if n > 1]
        if dupes:
            raise ValueError(f"ids repetidos: {dupes}")
        known = {o.id for o in self.outcomes}
        bad = [b.description for b in self.barriers if set(b.outcomes) - known]
        if bad:
            raise ValueError(f"barreras ligadas a resultados inexistentes: {bad}")
        outcomes_text = {d.data_outcome for o in self.outcomes for d in o.deliverables}
        orphan = set(self.data_outcome_metrics) - outcomes_text
        if orphan:
            raise ValueError(f"métricas de resultados de datos que nadie entrega: {orphan}")
        return self


def warnings(fw: OutcomeFramework) -> list[str]:
    """Problemas que no impiden ejecutar, pero sí reportar el éxito con credibilidad."""
    out = []
    for o in fw.outcomes:
        if o.signoff is None:
            out.append(f"{o.id}: el stakeholder no ha firmado el valor; no se puede presentar "
                       "como éxito hasta que lo haga.")
        if o.deadline < fw.as_of and o.business_metric.progress < 1:
            out.append(f"{o.id}: venció el {o.deadline:%d/%m/%Y} sin alcanzar el objetivo.")
        for c in o.capabilities:
            if c.missing_components:
                out.append(f"{c.id}: a la capacidad le falta {', '.join(c.missing_components)}.")
            for d in c.deliverables:
                if not d.data_outcome:
                    out.append(f"{d.id}: el entregable no está ligado a ningún resultado de datos.")
    return out
