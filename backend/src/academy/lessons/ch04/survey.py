"""Participantes (#2) y respuestas de la evaluación (#4).

Participan quienes están más cerca de los datos: el steward de negocio y el técnico de
cada dominio. Si un dominio aún no tiene stewards, se entrevista a su ejecutivo de dominio.

Las respuestas se simulan: en un caso real saldrían de los talleres. Cada participante se
autoevalúa antes del taller y después el taller fija una puntuación de consenso
facilitada. La autoevaluación lleva el sesgo de cada dominio, para reproducir el caso de
"gaming the system" del capítulo.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from academy.lessons.ch03.team import FunctionalRoles

from .model import DATA_OFFICE, AssessmentInput, MaturityModel


@dataclass(frozen=True)
class Participant:
    unit: str
    name: str
    role: str
    fallback: bool = False  # True si se entrevista al ejecutivo por falta de stewards


def participants(inp: AssessmentInput, roles: list[FunctionalRoles]) -> list[Participant]:
    by_domain = {r.domain: r for r in roles}
    out = []
    for unit in inp.scope.units:
        if unit == DATA_OFFICE:
            out += [Participant(unit, n, "Oficina de datos") for n in inp.data_office_participants]
            continue
        r = by_domain.get(unit)
        stewards = ([Participant(unit, n, "Steward de negocio") for n in r.business_stewards]
                    + [Participant(unit, n, "Steward técnico") for n in r.technical_stewards]
                    ) if r else []
        if stewards:
            out += stewards
        elif r and r.executive:
            out.append(Participant(unit, r.executive, "Ejecutivo de dominio", fallback=True))
    return out


def simulate_responses(inp: AssessmentInput, model: MaturityModel,
                       people: list[Participant]) -> pd.DataFrame:
    """Una fila por participante y pregunta, con la autoevaluación y el consenso del taller."""
    sim, rng = inp.simulation, np.random.default_rng(inp.simulation.seed)
    lo, hi = model.min_level, model.max_level
    rows = []
    for unit in inp.scope.units:
        unit_people = [p for p in people if p.unit == unit]
        for dim in model.dimensions:
            true_level = sim.domain_base[unit] + sim.dimension_adjust.get(dim.id, 0.0)
            for q, question in enumerate(dim.questions, start=1):
                consensus = int(np.clip(round(true_level + rng.normal(0, sim.noise)), lo, hi))
                for p in unit_people:
                    own = true_level + sim.self_bias.get(unit, 0.0) + rng.normal(0, sim.noise)
                    rows.append({
                        "unit": unit, "participant": p.name, "role": p.role,
                        "dimension": dim.id, "question": q, "question_text": question,
                        "self_score": int(np.clip(round(own), lo, hi)),
                        "workshop_score": consensus,
                    })
    return pd.DataFrame(rows)
