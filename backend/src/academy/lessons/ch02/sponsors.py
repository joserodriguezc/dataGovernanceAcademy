"""Evaluación de sponsors ejecutivos y caso de negocio para el dominio piloto.

Reglas del capítulo:
- El sponsor debe estar en el comité de dirección, reportando directamente al CEO.
- El CIO es un socio imprescindible para entregar, pero no el sponsor.
- Hace falta al menos un sponsor, idealmente dos.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator, model_validator

from academy.core.company import DATA_DOMAINS

CRITERIA = {
    "challenges_you": "Exige definir el éxito en términos de negocio",
    "digs_deeper": "Obliga a reforzar el caso de negocio",
    "defines_ultimate_impact": "Mide el éxito por el impacto final",
    "ceo_support": "Respaldo del CEO",
    "urgent_data_needs": "Necesidades de datos urgentes",
}
CIO_ID = "cio"
MAX_SPONSORS = 2


def _check_domain(value: str | None) -> str | None:
    if value is not None and value not in DATA_DOMAINS:
        raise ValueError(f"dominio desconocido '{value}'; válidos: {sorted(DATA_DOMAINS)}")
    return value


class Candidate(BaseModel):
    stakeholder: str
    domain: str | None
    reports_to_ceo: bool
    scores: dict[str, int]
    needs: list[str] = Field(default_factory=list)

    _domain = field_validator("domain")(_check_domain)

    @model_validator(mode="after")
    def _check_scores(self) -> "Candidate":
        if set(self.scores) != set(CRITERIA):
            raise ValueError(f"{self.stakeholder}: hay que puntuar exactamente {sorted(CRITERIA)}")
        if any(not 1 <= v <= 5 for v in self.scores.values()):
            raise ValueError(f"{self.stakeholder}: las puntuaciones van de 1 a 5")
        return self


class Track(BaseModel):
    name: str
    what: str
    capabilities: list[str] = Field(min_length=1)
    why_it_matters: str
    outcomes: list[str] = Field(min_length=1)
    done_to_date: str
    milestones: list[str] = Field(min_length=1)
    needs: list[str]
    kpis: list[str] = Field(min_length=1)


class PilotBusinessCase(BaseModel):
    title: str
    domain: str
    business_sponsor: str
    objective: str
    key_solutions: list[str] = Field(min_length=1)
    kpis: list[str] = Field(min_length=1)
    near_term_outcomes: list[str] = Field(min_length=1)
    committee_asks: list[str]
    tracks: list[Track] = Field(min_length=1)

    _domain = field_validator("domain")(_check_domain)


class SponsorInput(BaseModel):
    weights: dict[str, float]
    candidates: list[Candidate] = Field(min_length=1)
    pilot_business_case: PilotBusinessCase

    @model_validator(mode="after")
    def _check_weights(self) -> "SponsorInput":
        if set(self.weights) != set(CRITERIA):
            raise ValueError(f"hay que ponderar exactamente {sorted(CRITERIA)}")
        return self


@dataclass(frozen=True)
class Assessment:
    candidate: Candidate
    score: float  # 0-100
    exclusion: str | None

    @property
    def eligible(self) -> bool:
        return self.exclusion is None


def exclusion_reason(c: Candidate) -> str | None:
    if c.stakeholder == CIO_ID:
        return "El CIO es el socio para entregar, no el sponsor"
    if not c.reports_to_ceo:
        return "No reporta directamente al CEO"
    return None


def weighted_score(scores: dict[str, int], weights: dict[str, float]) -> float:
    """Puntuación ponderada normalizada a 0-100 (1 en todo = 0; 5 en todo = 100)."""
    total_weight = sum(weights.values())
    mean = sum(scores[k] * w for k, w in weights.items()) / total_weight
    return (mean - 1) / 4 * 100


def assess_sponsors(inp: SponsorInput) -> list[Assessment]:
    """Candidatos ordenados: primero los elegibles, de mayor a menor puntuación."""
    results = [
        Assessment(c, weighted_score(c.scores, inp.weights), exclusion_reason(c))
        for c in inp.candidates
    ]
    return sorted(results, key=lambda a: (not a.eligible, -a.score))


def recommend(assessments: list[Assessment]) -> list[Assessment]:
    """Sponsor principal y, si existe, uno secundario."""
    return [a for a in assessments if a.eligible][:MAX_SPONSORS]


def pilot_mismatch(case: PilotBusinessCase, recommended: list[Assessment]) -> str | None:
    """Aviso si el caso de negocio piloto no es del dominio del sponsor principal."""
    if not recommended:
        return "No hay ningún sponsor elegible: sin sponsor no hay piloto."
    primary = recommended[0].candidate
    if primary.domain != case.domain:
        return (f"El caso de negocio piloto es del dominio '{case.domain}', pero el sponsor "
                f"recomendado ({primary.stakeholder}) lidera '{primary.domain}'.")
    return None
