"""Clasificación de datos y detección automática de PII.

Primero se busca una regla que coincida por el nombre de la columna; solo si ninguna
coincide se mira el contenido (proporción de una muestra que cumple el patrón). Las
correcciones confirmadas por los stewards prevalecen sobre la detección automática.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field


class Level(BaseModel):
    name: str
    order: int


class Rule(BaseModel):
    category: str
    level: str
    name_pattern: str | None = None
    value_pattern: str | None = None


class Default(BaseModel):
    category: str
    level: str


class Override(BaseModel):
    category: str
    level: str
    by: str
    reason: str


class ClassificationPolicy(BaseModel):
    levels: dict[str, Level]
    rules: list[Rule] = Field(min_length=1)
    default: Default
    sample_size: int = Field(gt=0)
    min_match: float = Field(gt=0, le=1)
    overrides: dict[str, Override] = Field(default_factory=dict)

    def level_name(self, level: str) -> str:
        return self.levels[level].name

    def is_restricted(self, level: str) -> bool:
        return self.levels[level].order == max(lv.order for lv in self.levels.values())


@dataclass(frozen=True)
class Classification:
    category: str
    level: str
    method: str  # nombre | contenido | nombre y contenido | steward | por defecto


def match_ratio(values: list[str], pattern: str) -> float:
    if not values:
        return 0.0
    regex = re.compile(pattern)
    return sum(bool(regex.fullmatch(v.strip())) for v in values) / len(values)


def classify(column_fqn: str, column_name: str, values: list[str],
             policy: ClassificationPolicy) -> Classification:
    if column_fqn in policy.overrides:
        o = policy.overrides[column_fqn]
        return Classification(o.category, o.level, "steward")

    def by_value(rule: Rule) -> bool:
        return bool(rule.value_pattern
                    and match_ratio(values, rule.value_pattern) >= policy.min_match)

    # 1) El nombre manda: es más fiable que el contenido (una fecha parece un número).
    for rule in policy.rules:
        if rule.name_pattern and re.search(rule.name_pattern, column_name, re.I):
            method = "nombre y contenido" if by_value(rule) else "nombre"
            return Classification(rule.category, rule.level, method)
    # 2) Si el nombre no dice nada, se mira el contenido de la muestra.
    for rule in policy.rules:
        if by_value(rule):
            return Classification(rule.category, rule.level, "contenido")
    return Classification(policy.default.category, policy.default.level, "por defecto")
