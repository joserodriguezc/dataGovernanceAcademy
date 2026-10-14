"""Resultados, modelo organizativo y consideraciones de IA.

Reglas del capítulo para elegir el modelo:
- Sin requisitos ni capacidades de datos: oficina del CDO pequeña (federada) que construye
  el caso de negocio y evoluciona hacia hub and spoke.
- Capacidades inconsistentes y problemas graves de calidad, uso o confianza: centralizar
  durante 12-24 meses para ganar consistencia y después pasar a hub and spoke.
- Apoyo general y líderes fuertes en las áreas: hub and spoke, pero solo si la oficina
  central es sólida y está bien financiada.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Model = Literal["federated", "hub_and_spoke", "centralized"]

MODEL_LABELS: dict[Model, str] = {
    "federated": "Federado (oficina del CDO)",
    "hub_and_spoke": "Hub and spoke",
    "centralized": "Centralizado",
}

# Quién asume cada responsabilidad en cada modelo (figuras del capítulo).
RESPONSIBILITIES = (
    "Fijar políticas y estándares y proveer herramientas centrales",
    "Impulsar la implantación en las áreas mediante el modelo de dominios",
    "Monitorizar el cumplimiento de políticas y estándares",
    "Cumplir las políticas y los estándares",
    "Usar las herramientas que provee la oficina del CDO",
    "Remediar las brechas de cumplimiento",
)
CDO, BU = "Oficina del CDO", "Áreas de negocio"
RESPONSIBILITY_MATRIX: dict[Model, tuple[str, ...]] = {
    "federated": (CDO, CDO, CDO, BU, BU, BU),
    "hub_and_spoke": (CDO, BU, CDO, BU, BU, BU),
    "centralized": (CDO, CDO, CDO, CDO, CDO, CDO),
}


class Outcome(BaseModel):
    id: str
    name: str
    selected: bool
    priority: int | None = None
    rationale: str

    @model_validator(mode="after")
    def _priority_if_selected(self) -> "Outcome":
        if self.selected and self.priority is None:
            raise ValueError(f"el resultado seleccionado '{self.id}' necesita prioridad")
        return self


class CoreQuestion(BaseModel):
    question: str
    answer: str = Field(min_length=1)


class OrgFacts(BaseModel):
    has_data_capabilities: bool
    capabilities_consistent: bool
    major_trust_issues: bool
    broad_support: bool
    strong_bu_leaders: bool
    central_office_strong: bool


class AIQuestion(BaseModel):
    question: str
    owner: str
    status: Literal["open", "in_progress", "answered"]
    decision: str | None = None

    @model_validator(mode="after")
    def _answered_needs_decision(self) -> "AIQuestion":
        if self.status == "answered" and not self.decision:
            raise ValueError(f"pregunta respondida sin decisión: {self.question}")
        return self


class AIOpportunity(BaseModel):
    area: str
    use_case: str


class OrgContext(BaseModel):
    outcomes: list[Outcome] = Field(min_length=1)
    core_questions: list[CoreQuestion]
    org_facts: OrgFacts
    ai_governance: list[AIQuestion]
    ai_opportunities: list[AIOpportunity]

    @model_validator(mode="after")
    def _unique_priorities(self) -> "OrgContext":
        priorities = [o.priority for o in self.outcomes if o.selected]
        if len(priorities) != len(set(priorities)):
            raise ValueError("las prioridades de los resultados seleccionados deben ser únicas")
        return self

    @property
    def selected_outcomes(self) -> list[Outcome]:
        return sorted((o for o in self.outcomes if o.selected), key=lambda o: o.priority or 0)


@dataclass(frozen=True)
class ModelRecommendation:
    model: Model
    target: Model  # modelo al que evolucionar
    horizon: str
    rationale: str
    prerequisites: list[str]


def recommend_model(f: OrgFacts) -> ModelRecommendation:
    if not f.has_data_capabilities:
        return ModelRecommendation(
            "federated", "hub_and_spoke", "hasta que las áreas adopten los resultados",
            "Aún no hay requisitos ni capacidades de datos. Una oficina del CDO pequeña construye "
            "el caso de negocio y fija los requisitos mínimos.", [])
    if not f.capabilities_consistent and f.major_trust_issues:
        return ModelRecommendation(
            "centralized", "hub_and_spoke", "12-24 meses",
            "Las capacidades se implementan de forma inconsistente y hay problemas graves de "
            "calidad o confianza. Reunir a los profesionales de datos en un equipo central da "
            "consistencia y rigor; a largo plazo, centralizar aleja a los stewards del negocio, "
            "por eso es temporal.",
            [] if f.broad_support else ["Conseguir apoyo general del comité de dirección"])
    if f.broad_support and f.strong_bu_leaders:
        prerequisites = [] if f.central_office_strong else [
            "Reforzar la oficina del CDO (equipo, herramientas y financiación) antes de "
            "delegar la implantación en las áreas"]
        return ModelRecommendation(
            "hub_and_spoke", "hub_and_spoke", "largo plazo",
            "Hay apoyo general y líderes fuertes en las áreas: el hub and spoke da el éxito más "
            "duradero si la oficina central es sólida.", prerequisites)
    return ModelRecommendation(
        "federated", "hub_and_spoke", "hasta que maduren los líderes de las áreas",
        "Las capacidades existen, pero aún faltan líderes de datos fuertes en las áreas para "
        "repartir la implantación.", [])
