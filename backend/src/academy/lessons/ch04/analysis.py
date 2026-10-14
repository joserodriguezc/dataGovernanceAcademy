"""Análisis de la evaluación (#5): puntuaciones, sesgo, evidencia y temas."""

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from .evidence import Cap
from .model import Finding

SCORE = "workshop_score"  # se reporta el consenso del taller, no la autoevaluación


def dimension_scores(responses: pd.DataFrame) -> pd.Series:
    """Media de la empresa por dimensión: media simple de las unidades evaluadas."""
    by_unit = responses.groupby(["dimension", "unit"])[SCORE].mean()
    return by_unit.groupby("dimension").mean()


def unit_scores(responses: pd.DataFrame) -> pd.DataFrame:
    """Matriz unidad × dimensión (uso interno de la oficina de datos)."""
    return responses.pivot_table(index="unit", columns="dimension", values=SCORE, aggfunc="mean")


def company_score(responses: pd.DataFrame) -> float:
    return float(dimension_scores(responses).mean())


@dataclass(frozen=True)
class Bias:
    unit: str
    self_avg: float
    workshop_avg: float

    @property
    def gap(self) -> float:
        return self.self_avg - self.workshop_avg

    @property
    def direction(self) -> str:
        return "se sobrevalora" if self.gap > 0 else "se infravalora"


def self_assessment_bias(responses: pd.DataFrame, threshold: float) -> list[Bias]:
    """Unidades cuya autoevaluación se aleja del consenso del taller más que el umbral."""
    means = responses.groupby("unit")[["self_score", SCORE]].mean()
    out = [Bias(u, float(r.self_score), float(r[SCORE])) for u, r in means.iterrows()]
    return sorted((b for b in out if abs(b.gap) >= threshold), key=lambda b: -abs(b.gap))


@dataclass(frozen=True)
class EvidenceFlag:
    cap: Cap
    score: float


def unsupported_scores(scores: pd.Series, caps: list[Cap]) -> list[EvidenceFlag]:
    """Dimensiones cuya puntuación supera lo que respalda la evidencia."""
    return [EvidenceFlag(c, float(scores[c.dimension])) for c in caps
            if c.dimension in scores and scores[c.dimension] > c.max_level]


@dataclass(frozen=True)
class Theme:
    name: str
    findings: list[Finding]

    @property
    def priority(self) -> int:
        return min(f.priority for f in self.findings)

    @property
    def domains(self) -> list[str]:
        return sorted({d for f in self.findings for d in f.domains})

    @property
    def dimensions(self) -> list[str]:
        return sorted({f.dimension for f in self.findings})


def group_themes(findings: list[Finding]) -> list[Theme]:
    """Agrupa los hallazgos en temas, ordenados por prioridad y nº de dominios afectados."""
    groups: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        groups[f.theme].append(f)
    themes = [Theme(name, fs) for name, fs in groups.items()]
    return sorted(themes, key=lambda t: (t.priority, -len(t.domains), t.name))
