"""Lectura de los registros de cliente de cada sistema en un formato común (party)."""

import duckdb
import pandas as pd

from academy.core.synthetic.noise import strip_accents

from .config import PdmConfig

COLUMNS = ["source", "source_id", "first_name", "last_name", "email", "phone", "postal_code",
           "birth_date", "loyalty_tier", "consent_marketing", "created_at", "name_key"]

QUERIES = {
    "crm": """SELECT customer_id AS source_id, first_name, last_name, email, phone, postal_code,
                     birth_date, loyalty_tier, consent_marketing, created_at
              FROM {table}""",
    "ecom": """SELECT ecom_user_id AS source_id, full_name, email, phone, postal_code,
                      created_at FROM {table}""",
    "pos": """SELECT card_id AS source_id, holder_name AS full_name, phone, postal_code
              FROM {table}""",
}


def name_key(text: str | None) -> str:
    """Nombre normalizado para comparar: sin tildes, en minúsculas y sin espacios extra."""
    return " ".join(strip_accents(text or "").lower().split())


def _split(full: str | None) -> tuple[str | None, str | None]:
    """'Ana Ruiz Gil' -> ('Ana', 'Ruiz Gil'). Los nombres compuestos se parten mal: por eso
    el nombre de pila del CRM, que viene separado, es la fuente de más confianza."""
    if not full:
        return None, None
    tokens = full.title().split()
    return tokens[0], " ".join(tokens[1:]) or None


def load_parties(con: duckdb.DuckDBPyConnection, cfg: PdmConfig) -> pd.DataFrame:
    frames = []
    for key, src in cfg.sources.items():
        df = con.execute(QUERIES[key].format(table=src.table)).df()
        if "full_name" in df:
            split = df["full_name"].map(_split)
            df["first_name"] = split.map(lambda s: s[0])
            df["last_name"] = split.map(lambda s: s[1])
            df["name_key"] = df["full_name"].map(name_key)
            df = df.drop(columns="full_name")
        else:
            df["name_key"] = (df["first_name"].fillna("") + " " + df["last_name"].fillna("")
                              ).map(name_key)
        df["source"] = key
        frames.append(df.reindex(columns=COLUMNS))
    parties = pd.concat(frames, ignore_index=True)
    parties["created_at"] = pd.to_datetime(parties["created_at"])
    parties["birth_date"] = pd.to_datetime(parties["birth_date"]).dt.date
    return parties
