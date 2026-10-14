"""Caso de negocio: tres opciones de timeline comparadas con VAN, ROI y payback.

Supuestos del modelo de flujos mensuales:
- El coste de construcción se reparte por igual durante la duración del programa.
- El coste de operación (run) empieza al terminar la construcción.
- El beneficio anual (mejora de data equity) crece de forma lineal durante la
  construcción, porque se entrega de forma iterativa, y es pleno al terminarla.
"""

from dataclasses import dataclass
from itertools import accumulate

from pydantic import BaseModel, Field, model_validator


class TimelineOption(BaseModel):
    id: str
    name: str
    description: str
    duration_months: int = Field(gt=0)
    build_cost_usd: float = Field(ge=0)
    run_cost_annual_usd: float = Field(ge=0)


class Program(BaseModel):
    chapter: int
    name: str
    description: str


class BusinessCaseInput(BaseModel):
    title: str
    owner: str
    authors: list[str]
    contributors: list[str]
    reviewers: list[str]
    purpose: str
    ask: str
    horizon_months: int = Field(gt=0)
    discount_rate_annual: float = Field(ge=0)
    include_unvetted_benefits: bool = False
    recommended_option: str
    programs: list[Program]
    measures_of_success: list[str] = Field(min_length=1)
    options: list[TimelineOption] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_options(self) -> "BusinessCaseInput":
        ids = [o.id for o in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("los id de las opciones deben ser únicos")
        if self.recommended_option not in ids:
            raise ValueError(f"recommended_option '{self.recommended_option}' no existe")
        return self


@dataclass(frozen=True)
class OptionResult:
    option: TimelineOption
    costs: list[float]
    benefits: list[float]
    npv: float
    payback_month: int | None

    @property
    def total_cost(self) -> float:
        return sum(self.costs)

    @property
    def total_benefit(self) -> float:
        return sum(self.benefits)

    @property
    def roi(self) -> float:
        return (self.total_benefit - self.total_cost) / self.total_cost if self.total_cost else 0.0

    @property
    def cumulative(self) -> list[float]:
        """Flujo neto acumulado mes a mes."""
        return list(accumulate(b - c for c, b in zip(self.costs, self.benefits, strict=True)))


def monthly_flows(
    option: TimelineOption, annual_benefit: float, horizon_months: int
) -> tuple[list[float], list[float]]:
    """Devuelve (costes, beneficios) por mes, del mes 1 al horizonte."""
    d = option.duration_months
    costs, benefits = [], []
    for month in range(1, horizon_months + 1):
        building = month <= d
        cost = option.build_cost_usd / d if building else option.run_cost_annual_usd / 12
        costs.append(cost)
        benefits.append(annual_benefit / 12 * min(month / d, 1.0))
    return costs, benefits


def npv(flows: list[float], annual_rate: float) -> float:
    """Valor actual neto de flujos mensuales (el primero se descuenta un mes)."""
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    return sum(f / (1 + monthly_rate) ** m for m, f in enumerate(flows, start=1))


def payback_month(cumulative: list[float]) -> int | None:
    """Primer mes en que el flujo acumulado deja de ser negativo; None si no ocurre."""
    return next((m for m, value in enumerate(cumulative, start=1) if value >= 0), None)


def evaluate_option(
    option: TimelineOption, annual_benefit: float, horizon_months: int, annual_rate: float
) -> OptionResult:
    costs, benefits = monthly_flows(option, annual_benefit, horizon_months)
    net = [b - c for c, b in zip(costs, benefits, strict=True)]
    return OptionResult(
        option, costs, benefits, npv(net, annual_rate), payback_month(list(accumulate(net)))
    )


def evaluate_business_case(inp: BusinessCaseInput, annual_benefit: float) -> list[OptionResult]:
    return [
        evaluate_option(o, annual_benefit, inp.horizon_months, inp.discount_rate_annual)
        for o in inp.options
    ]
