"""EDG Scorecard: avance en la implantación de la política, corporativo y por dominio.

Las métricas corporativas cuentan dominios (denominador: total de dominios) y las de
dominio cuentan sistemas de registro (denominador: sistemas del dominio). El estado
sigue la convención del capítulo: Verde en plazo, Amarillo en riesgo, Rojo vencido.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from academy.core.company import DATA_DOMAINS

Status = Literal["green", "yellow", "red"]
STATUS_LABELS: dict[Status, str] = {
    "green": "🟢 En plazo",
    "yellow": "🟡 En riesgo",
    "red": "🔴 Vencido",
}

# Métricas que se miden por sistema de registro: clave -> (etiqueta, atributo del sistema).
SYSTEM_METRICS: dict[str, tuple[str, str]] = {
    "cdes": ("CDE identificados", "cdes"),
    "dq_rules": ("Reglas de calidad escritas y ejecutadas", "dq_rules"),
    "business_glossary": ("Glosario de negocio", "glossary"),
    "data_dictionary": ("Diccionario de datos", "dictionary"),
    "reference_data": ("Datos de referencia adoptados", "reference_data"),
}


class SystemStatus(BaseModel):
    name: str
    owner: str | None = None
    cdes: bool = False
    dq_rules: bool = False
    glossary: bool = False
    dictionary: bool = False
    reference_data: bool = False


class DomainStatus(BaseModel):
    id: str
    executive: str | None = None
    stewards: list[str] = Field(default_factory=list)
    systems: list[SystemStatus] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _known_domain(cls, value: str) -> str:
        if value not in DATA_DOMAINS:
            raise ValueError(f"dominio desconocido '{value}'; válidos: {sorted(DATA_DOMAINS)}")
        return value

    def all_systems(self, attr: str) -> bool:
        """El dominio cumple una métrica de sistema si todos sus sistemas la cumplen."""
        return bool(self.systems) and all(getattr(s, attr) for s in self.systems)


# Métricas corporativas: clave -> (etiqueta, predicado sobre el dominio).
CORPORATE_METRICS: dict[str, tuple[str, Callable[[DomainStatus], bool]]] = {
    "domain_executive": ("Ejecutivo de dominio identificado", lambda d: d.executive is not None),
    "data_stewards": ("Data stewards designados", lambda d: bool(d.stewards)),
    "systems_identified": ("Sistemas de registro identificados", lambda d: bool(d.systems)),
    "system_owners": ("Owners de sistema asignados",
                      lambda d: bool(d.systems) and all(s.owner for s in d.systems)),
    **{
        key: (f"{label} en cada sistema", lambda d, attr=attr: d.all_systems(attr))
        for key, (label, attr) in SYSTEM_METRICS.items()
    },
}


class ScorecardInput(BaseModel):
    as_of: date
    at_risk_days: int = Field(30, ge=0)
    due_dates: dict[str, date]
    domains: list[DomainStatus] = Field(min_length=1)
    updates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "ScorecardInput":
        missing = set(CORPORATE_METRICS) - set(self.due_dates)
        if missing:
            raise ValueError(f"faltan fechas comprometidas para: {sorted(missing)}")
        ids = [d.id for d in self.domains]
        if len(ids) != len(set(ids)):
            raise ValueError("hay dominios repetidos")
        return self


@dataclass(frozen=True)
class MetricResult:
    key: str
    label: str
    numerator: int
    denominator: int
    due: date
    status: Status

    @property
    def pct(self) -> float:
        return self.numerator / self.denominator if self.denominator else 0.0

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]


def rag_status(pct: float, due: date, as_of: date, at_risk_days: int) -> Status:
    """Verde si está completa o falta tiempo; Amarillo si vence pronto; Rojo si venció."""
    if pct >= 1.0:
        return "green"
    days_left = (due - as_of).days
    if days_left < 0:
        return "red"
    if days_left <= at_risk_days:
        return "yellow"
    return "green"


def _result(inp: ScorecardInput, key: str, label: str, num: int, den: int) -> MetricResult:
    due = inp.due_dates[key]
    pct = num / den if den else 0.0
    return MetricResult(key, label, num, den, due,
                        rag_status(pct, due, inp.as_of, inp.at_risk_days))


def corporate_scorecard(inp: ScorecardInput) -> list[MetricResult]:
    total = len(inp.domains)
    return [
        _result(inp, key, label, sum(pred(d) for d in inp.domains), total)
        for key, (label, pred) in CORPORATE_METRICS.items()
    ]


def domain_scorecard(inp: ScorecardInput, domain: DomainStatus) -> list[MetricResult]:
    total = len(domain.systems)
    return [
        _result(inp, key, label, sum(getattr(s, attr) for s in domain.systems), total)
        for key, (label, attr) in SYSTEM_METRICS.items()
    ]
