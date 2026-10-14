"""Data equity: activos de datos − pasivos de datos.

Un dato es un activo cuando genera valor (ingresos, tiempo ahorrado, satisfacción del
cliente) y un pasivo cuando genera riesgo (multas, ineficiencias, clientes perdidos).
Cada línea se valora en su situación actual y en la objetivo; la mejora anual de data
equity es el beneficio que alimenta el caso de negocio.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from academy.core.company import DATA_DOMAINS

State = Literal["current", "target"]


class AssetValue(BaseModel):
    """Valor anual que aporta un activo de datos."""

    revenue_usd: float = Field(0, ge=0)
    hours_saved: float = Field(0, ge=0)
    customer_value_usd: float = Field(0, ge=0)  # gasto adicional o retención atribuible

    def value(self, hourly_rate: float) -> float:
        return self.revenue_usd + self.hours_saved * hourly_rate + self.customer_value_usd


class LiabilityValue(BaseModel):
    """Coste anual que genera un pasivo de datos."""

    fine_probability: float = Field(0, ge=0, le=1)
    fine_amount_usd: float = Field(0, ge=0)
    hours_lost: float = Field(0, ge=0)
    customer_impact_usd: float = Field(0, ge=0)  # gasto perdido o abandono atribuible

    def value(self, hourly_rate: float) -> float:
        expected_fine = self.fine_probability * self.fine_amount_usd
        return expected_fine + self.hours_lost * hourly_rate + self.customer_impact_usd


class _EquityItem(BaseModel):
    id: str
    name: str
    domain: str
    description: str
    vetted_by: str | None = None  # quién del negocio validó la valoración

    @field_validator("domain")
    @classmethod
    def _known_domain(cls, value: str) -> str:
        if value not in DATA_DOMAINS:
            raise ValueError(f"dominio desconocido '{value}'; válidos: {sorted(DATA_DOMAINS)}")
        return value


class DataAsset(_EquityItem):
    current: AssetValue
    target: AssetValue


class DataLiability(_EquityItem):
    current: LiabilityValue
    target: LiabilityValue


class DataEquityInput(BaseModel):
    hourly_rate_usd: float = Field(gt=0)
    assets: list[DataAsset]
    liabilities: list[DataLiability]


@dataclass(frozen=True)
class EquityLine:
    id: str
    name: str
    kind: Literal["asset", "liability"]
    domain: str
    vetted_by: str | None
    current: float
    target: float

    @property
    def vetted(self) -> bool:
        return self.vetted_by is not None

    @property
    def benefit(self) -> float:
        """Mejora anual de data equity: más activo o menos pasivo."""
        if self.kind == "asset":
            return self.target - self.current
        return self.current - self.target


@dataclass(frozen=True)
class EquitySummary:
    lines: list[EquityLine]

    def _select(self, kind: str, vetted_only: bool) -> list[EquityLine]:
        return [ln for ln in self.lines if ln.kind == kind and (ln.vetted or not vetted_only)]

    def assets(self, state: State, vetted_only: bool = False) -> float:
        return sum(getattr(ln, state) for ln in self._select("asset", vetted_only))

    def liabilities(self, state: State, vetted_only: bool = False) -> float:
        return sum(getattr(ln, state) for ln in self._select("liability", vetted_only))

    def equity(self, state: State, vetted_only: bool = False) -> float:
        return self.assets(state, vetted_only) - self.liabilities(state, vetted_only)

    def annual_benefit(self, vetted_only: bool = False) -> float:
        return self.equity("target", vetted_only) - self.equity("current", vetted_only)

    @property
    def unvetted(self) -> list[EquityLine]:
        return [ln for ln in self.lines if not ln.vetted]


def evaluate_equity(inp: DataEquityInput) -> EquitySummary:
    rate = inp.hourly_rate_usd
    lines = [
        EquityLine(a.id, a.name, "asset", a.domain, a.vetted_by,
                   a.current.value(rate), a.target.value(rate))
        for a in inp.assets
    ] + [
        EquityLine(li.id, li.name, "liability", li.domain, li.vetted_by,
                   li.current.value(rate), li.target.value(rate))
        for li in inp.liabilities
    ]
    return EquitySummary(lines)
