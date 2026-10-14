"""Charter del programa: why statement, misiones, decisión de lanzamiento y glosario."""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

# "Data speak": jerga que no debe aparecer en una visión dirigida al negocio.
DATA_SPEAK = (
    "metadatos", "metadata", "linaje", "lineage", "etl", "elt", "pipeline", "mdm",
    "data lake", "lakehouse", "data warehouse", "esquema", "ingesta", "golden record",
    "cde", "dataset", "modelo de datos", "data mesh", "pii",
)
VISION_MAX_WORDS = 40


class Vision(BaseModel):
    aspire: str = Field(min_length=1)  # ¿Qué aspiramos a hacer?
    who: str = Field(min_length=1)  # ¿Quién nos ayudará a conseguirlo?
    arrival: str = Field(min_length=1)  # ¿Cómo sabremos que hemos llegado?
    statement: str = Field(min_length=1)


class ProgramMission(BaseModel):
    """Plantilla 'Hacemos X para Y mediante A, B y C'."""

    what: str
    for_whom: str
    how: list[str] = Field(min_length=2)

    @property
    def statement(self) -> str:
        how = ", ".join(self.how[:-1]) + f" y {self.how[-1]}"
        return f"Desarrollamos {self.what} para {self.for_whom}, {how}."


class Signal(BaseModel):
    id: str
    name: str
    present: bool
    evidence: str = ""


class LaunchInput(BaseModel):
    drivers: list[Signal]
    warning_signs: list[Signal]


class GlossaryTerm(BaseModel):
    term: str
    definition: str


class ProgramInput(BaseModel):
    company: str
    vision: Vision
    cdao_mission: str
    cdao_principles: list[str]
    program_mission: ProgramMission
    launch: LaunchInput
    glossary: list[GlossaryTerm]


def lint_vision(statement: str, max_words: int = VISION_MAX_WORDS) -> list[str]:
    """Problemas de la visión: demasiado larga o con jerga de datos."""
    issues = []
    words = len(statement.split())
    if words > max_words:
        issues.append(f"Tiene {words} palabras; el máximo para que se recuerde es {max_words}.")
    for term in DATA_SPEAK:
        if re.search(rf"\b{re.escape(term)}\b", statement, flags=re.IGNORECASE):
            issues.append(f"Usa jerga de datos: «{term}».")
    return issues


@dataclass(frozen=True)
class LaunchDecision:
    verdict: Literal["lanzar", "esperar"]
    drivers: list[Signal]
    warnings: list[Signal]
    rationale: str


def assess_launch(inp: LaunchInput) -> LaunchDecision:
    """Lanzar solo con al menos un impulsor y ninguna señal de alerta activa."""
    drivers = [s for s in inp.drivers if s.present]
    warnings = [s for s in inp.warning_signs if s.present]
    if warnings:
        names = "; ".join(s.name for s in warnings)
        return LaunchDecision("esperar", drivers, warnings,
                              f"Hay señales de alerta que conviene mitigar antes: {names}.")
    if not drivers:
        return LaunchDecision("esperar", drivers, warnings,
                              "No hay un impulsor claro; sin necesidad real, el programa no "
                              "tendrá apoyo sostenido.")
    names = ", ".join(s.name.lower() for s in drivers)
    return LaunchDecision("lanzar", drivers, warnings,
                          f"Hay impulsores activos ({names}) y ninguna señal de alerta.")
