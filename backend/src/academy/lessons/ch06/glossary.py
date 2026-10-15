"""Glosario de negocio: términos, definiciones y su vínculo con las columnas del warehouse."""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from academy.core.company import DATA_DOMAINS
from academy.lessons.ch03.team import FunctionalRoles

STATUS_LABELS = {"approved": "✅ Aprobado", "in_review": "🟡 En revisión", "draft": "📝 Borrador"}


class Term(BaseModel):
    term: str
    domain: str
    definition: str = Field(min_length=1)
    synonyms: list[str] = Field(default_factory=list)
    antonyms: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    notes: str | None = None
    authorized_source: str | None = None
    status: Literal["approved", "in_review", "draft"]
    columns: list[str] = Field(default_factory=list)

    @field_validator("domain")
    @classmethod
    def _known_domain(cls, value: str) -> str:
        if value not in DATA_DOMAINS:
            raise ValueError(f"dominio desconocido '{value}'")
        return value

    @field_validator("columns")
    @classmethod
    def _qualified(cls, value: list[str]) -> list[str]:
        bad = [c for c in value if c.count(".") != 2]
        if bad:
            raise ValueError(f"las columnas deben ser esquema.tabla.columna: {bad}")
        return value


class Glossary(BaseModel):
    terms: list[Term] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "Glossary":
        names = [t.term.lower() for t in self.terms]
        dupes = [k for k, n in Counter(names).items() if n > 1]
        if dupes:
            raise ValueError(f"términos repetidos: {dupes}")
        return self

    def column_terms(self) -> dict[str, str]:
        """Columna -> término que la define (el primero si hubiera varios)."""
        out: dict[str, str] = {}
        for t in self.terms:
            for c in t.columns:
                out.setdefault(c, t.term)
        return out


@dataclass(frozen=True)
class Stewards:
    business: list[str]
    technical: list[str]


def stewards_by_domain(roles: list[FunctionalRoles]) -> dict[str, Stewards]:
    return {r.domain: Stewards(r.business_stewards, r.technical_stewards) for r in roles}


def broken_mappings(glossary: Glossary, existing_columns: set[str]) -> list[tuple[str, str]]:
    """(término, columna) para columnas del glosario que no existen en el warehouse."""
    return [(t.term, c) for t in glossary.terms for c in t.columns if c not in existing_columns]
