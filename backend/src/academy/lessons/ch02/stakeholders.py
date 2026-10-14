"""Registro y mapa de stakeholders: a quién servimos, qué persiguen y cómo les ayudamos.

El mapa sigue la plantilla del capítulo (grupo → objetivos → soluciones de datos →
resultados de negocio objetivo). Además de la plantilla, cada grupo se sitúa en una
matriz influencia/interés para priorizar, porque no todos los stakeholders pesan igual.
"""

from collections import Counter
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Kind = Literal["internal", "external"]
Health = Literal["positive", "neutral", "negative"]
ResultType = Literal["revenue", "customer", "cost", "risk", "productivity", "data"]
Direction = Literal["horizontal", "up", "down", "across", "out"]

INTERNAL_LEVELS = ("individual_contributor", "manager", "divisional_leader", "executive", "board")
EXTERNAL_LEVELS = ("customer", "partner", "supplier", "investor", "regulator")

LEVEL_LABELS = {
    "individual_contributor": "Colaborador individual",
    "manager": "Mando intermedio",
    "divisional_leader": "Líder divisional",
    "executive": "Comité de dirección",
    "board": "Consejo",
    "customer": "Cliente",
    "partner": "Partner",
    "supplier": "Proveedor",
    "investor": "Inversor",
    "regulator": "Regulador",
}
HEALTH_LABELS = {"positive": "🟢 Positiva", "neutral": "⚪ Neutral", "negative": "🔴 Negativa"}
DIRECTION_LABELS = {
    "horizontal": "Horizontal (pares)",
    "up": "Arriba (CEO y consejo)",
    "down": "Abajo (equipo propio)",
    "across": "Transversal (grupos de todos los niveles)",
    "out": "Hacia fuera (proveedores, consultores, antiguos empleados)",
}

# Umbral de la matriz: por encima de este valor, la influencia o el interés son altos.
HIGH = 3


class TargetResult(BaseModel):
    text: str
    type: ResultType


class MapEntry(BaseModel):
    objectives: list[str] = Field(min_length=1)
    data_solutions: list[str] = Field(min_length=1)
    target_results: list[TargetResult] = Field(min_length=1)
    actual_results: list[str] = Field(default_factory=list)
    ultimate_beneficiary: str

    @property
    def vanity_only(self) -> bool:
        """Todos los resultados miden el dato y ninguno el negocio."""
        return all(r.type == "data" for r in self.target_results)


class Partnership(BaseModel):
    what_we_need: str
    what_they_need: str


class StakeholderGroup(BaseModel):
    id: str
    short: str
    name: str
    kind: Kind
    level: str
    role: str
    health: Health
    contributions: str
    success_measures: list[str] = Field(min_length=1)
    influence: int = Field(ge=1, le=5)
    interest: int = Field(ge=1, le=5)
    notes: str | None = None
    map: MapEntry | None = None
    partnership: Partnership | None = None

    @model_validator(mode="after")
    def _level_matches_kind(self) -> "StakeholderGroup":
        valid = INTERNAL_LEVELS if self.kind == "internal" else EXTERNAL_LEVELS
        if self.level not in valid:
            raise ValueError(f"{self.id}: nivel '{self.level}' no válido para {self.kind}")
        return self

    @property
    def quadrant(self) -> str:
        high_influence, high_interest = self.influence > HIGH, self.interest > HIGH
        if high_influence and high_interest:
            return "Gestionar de cerca"
        if high_influence:
            return "Mantener satisfecho"
        if high_interest:
            return "Mantener informado"
        return "Monitorizar"


class ListeningSession(BaseModel):
    direction: Direction
    audience: str
    format: Literal["one_on_one", "small_group", "large_group"]
    date: date
    done: bool


class StakeholderInput(BaseModel):
    purpose: str
    groups: list[StakeholderGroup] = Field(min_length=1)
    listening_sessions: list[ListeningSession] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> "StakeholderInput":
        dupes = [k for k, n in Counter(g.id for g in self.groups).items() if n > 1]
        if dupes:
            raise ValueError(f"ids de stakeholder repetidos: {dupes}")
        return self

    def by_id(self, group_id: str) -> StakeholderGroup:
        for g in self.groups:
            if g.id == group_id:
                return g
        raise KeyError(group_id)


def listening_coverage(sessions: list[ListeningSession]) -> dict[str, dict[str, int]]:
    """Sesiones hechas y planificadas en cada una de las cinco direcciones."""
    coverage = {d: {"done": 0, "planned": 0} for d in DIRECTION_LABELS}
    for s in sessions:
        coverage[s.direction]["done" if s.done else "planned"] += 1
    return coverage


def listening_gaps(sessions: list[ListeningSession]) -> list[str]:
    """Direcciones en las que todavía no se ha escuchado a nadie."""
    return [d for d, c in listening_coverage(sessions).items() if c["done"] == 0]


def vanity_groups(groups: list[StakeholderGroup]) -> list[StakeholderGroup]:
    """Grupos del mapa cuyos resultados objetivo son solo métricas del dato."""
    return [g for g in groups if g.map and g.map.vanity_only]
