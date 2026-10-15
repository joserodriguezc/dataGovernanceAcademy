"""Datos de referencia, enriquecimiento y jerarquías.

El código postal enriquece el golden record con la provincia y la comunidad (dato de
referencia oficial) y con la región comercial de NovaMercado (dato de referencia propio).
De la misma base salen dos jerarquías: la de localización (código postal -> provincia ->
comunidad) y la comercial (comunidad -> región de ventas).
"""

import pandas as pd

from .config import ReferenceData


def enrich(golden: pd.DataFrame, ref: ReferenceData) -> pd.DataFrame:
    prefix = golden["postal_code"].str[:2]
    known = prefix.isin(ref.provinces.keys())
    out = golden.copy()
    out["province_code"] = prefix.where(known)
    out["province"] = prefix.map(lambda p: ref.provinces.get(p, (None, None))[0])
    out["community"] = prefix.map(lambda p: ref.provinces.get(p, (None, None))[1])
    out["sales_region"] = out["community"].map(ref.region_of)
    return out


def reference_table(ref: ReferenceData) -> pd.DataFrame:
    region = ref.region_of
    return pd.DataFrame([{"province_code": code, "province": name, "community": comm,
                          "sales_region": region[comm]}
                         for code, (name, comm) in sorted(ref.provinces.items())])


def hierarchy_counts(golden: pd.DataFrame) -> pd.DataFrame:
    """Clientes por región comercial y comunidad (las dos jerarquías combinadas)."""
    return (golden.dropna(subset=["sales_region"])
            .groupby(["sales_region", "community"]).size().rename("customers").reset_index()
            .sort_values(["sales_region", "customers"], ascending=[True, False]))
