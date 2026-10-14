"""Matriz RACI: un único Accountable por actividad y al menos un Responsable."""

import csv
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class Activity(BaseModel):
    name: str
    A: str
    R: list[str] = Field(min_length=1)
    C: list[str] = Field(default_factory=list)
    I: list[str] = Field(default_factory=list)  # noqa: E741 (letra estándar de RACI)

    def letters(self, role: str) -> str:
        """Letras de la celda (rol, actividad); A y R pueden coincidir (p. ej., 'A/R')."""
        out = [k for k in ("A", "R", "C", "I")
               if (role == self.A if k == "A" else role in getattr(self, k))]
        return "/".join(out)


class RaciInput(BaseModel):
    roles: dict[str, str]  # id -> nombre visible
    activities: list[Activity] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "RaciInput":
        for act in self.activities:
            used = {act.A, *act.R, *act.C, *act.I}
            unknown = used - set(self.roles)
            if unknown:
                raise ValueError(f"«{act.name}» usa roles desconocidos: {sorted(unknown)}")
            if set(act.C) & set(act.I) or (set(act.R) & (set(act.C) | set(act.I))):
                raise ValueError(f"«{act.name}» asigna a un rol dos letras incompatibles")
        return self


def idle_roles(inp: RaciInput) -> list[str]:
    """Roles que no son A ni R en ninguna actividad: solo opinan o se enteran."""
    active = {a.A for a in inp.activities} | {r for a in inp.activities for r in a.R}
    return [name for rid, name in inp.roles.items() if rid not in active]


def raci_table(inp: RaciInput) -> list[list[str]]:
    """Filas de la matriz: actividad seguida de una celda por rol."""
    return [[a.name, *(a.letters(rid) for rid in inp.roles)] for a in inp.activities]


def write_csv(inp: RaciInput, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Actividad", *inp.roles.values()])
        writer.writerows(raci_table(inp))
    return path
