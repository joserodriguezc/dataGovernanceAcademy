"""Lógica de confianza (trust logic): construye el golden record atributo a atributo.

Para cada grupo de registros y cada atributo se recorren las fuentes en orden de
confianza; dentro de una fuente gana el registro más reciente; se toma el primer valor
válido. Se guarda de qué sistema y registro sale cada valor (atribución de la fuente dorada).
"""

import re

import pandas as pd

from .config import PdmConfig

TITLE_CASE = {"first_name", "last_name"}


def _valid(value, pattern: re.Pattern | None) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return False
    return pattern is None or bool(pattern.fullmatch(str(value)))


def golden_records(parties: pd.DataFrame, cfg: PdmConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (golden records, atribución por atributo)."""
    patterns = {a: re.compile(c.validate_) if c.validate_ else None
                for a, c in cfg.attributes.items()}
    ordered = parties.sort_values(["group", "source", "created_at"],
                                  ascending=[True, True, False], na_position="last")
    golden_rows, attribution = [], []
    for gid, members in ordered.groupby("group", sort=True):
        by_source = {s: m for s, m in members.groupby("source")}
        row = {"golden_id": gid}
        for attr, conf in cfg.attributes.items():
            value, origin = conf.default, None
            for source in conf.sources:
                rows = by_source.get(source)
                if rows is None:
                    continue
                hit = next(((v, sid) for v, sid in zip(rows[attr], rows["source_id"],
                                                        strict=True)
                            if _valid(v, patterns[attr])), None)
                if hit:
                    value, origin = hit[0], (source, hit[1])
                    break
            if attr in TITLE_CASE and isinstance(value, str):
                value = value.title()
            row[attr] = value
            attribution.append({"golden_id": gid, "attribute": attr,
                                "source": origin[0] if origin else "por defecto",
                                "source_id": origin[1] if origin else None})
        row["first_seen"] = members["created_at"].min()
        row["source_records"] = len(members)
        for s in cfg.sources:
            row[f"in_{s}"] = s in by_source
        golden_rows.append(row)
    return pd.DataFrame(golden_rows), pd.DataFrame(attribution)
