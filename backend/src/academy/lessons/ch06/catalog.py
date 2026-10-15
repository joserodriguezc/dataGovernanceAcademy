"""Catálogo de datos: metadatos técnicos extraídos del warehouse más anotaciones de negocio."""

from dataclasses import dataclass, field

import duckdb
from pydantic import BaseModel, Field, field_validator

from academy.core.company import DATA_DOMAINS

DOCUMENTED_LAYERS = ("staging", "curated")  # capas sujetas al estándar de metadatos
FORMAT_LABELS = {"dataset_curado": "Dataset curado", "tabla_staging": "Tabla de staging",
                 "aterrizaje_raw": "Aterrizaje raw"}


class TableAnnotation(BaseModel):
    description: str = Field(min_length=1)
    domain: str
    format: str
    tags: list[str] = Field(default_factory=list)

    @field_validator("domain")
    @classmethod
    def _known_domain(cls, value: str) -> str:
        if value not in DATA_DOMAINS:
            raise ValueError(f"dominio desconocido '{value}'")
        return value


class ValueAssumptions(BaseModel):
    data_users: int = Field(gt=0)
    annual_cost_per_user: float = Field(gt=0)
    search_time_share: float = Field(gt=0, le=1)
    expected_reduction: float = Field(gt=0, le=1)
    reports_per_year: int = Field(ge=0)
    hours_saved_per_report: float = Field(ge=0)
    hourly_rate: float = Field(gt=0)

    @property
    def catalog_value(self) -> float:
        """Tiempo de búsqueda que libera el catálogo (método del capítulo)."""
        return (self.data_users * self.annual_cost_per_user * self.search_time_share
                * self.expected_reduction)

    @property
    def glossary_value(self) -> float:
        """Horas ahorradas al acordar las definiciones antes de hacer los informes."""
        return self.reports_per_year * self.hours_saved_per_report * self.hourly_rate


class CatalogInput(BaseModel):
    tables: dict[str, TableAnnotation]
    value: ValueAssumptions


@dataclass
class CatalogColumn:
    table: str
    name: str
    data_type: str
    null_rate: float
    term: str | None = None
    level: str | None = None  # nivel de clasificación
    category: str | None = None
    method: str | None = None

    @property
    def fqn(self) -> str:
        return f"{self.table}.{self.name}"


@dataclass
class CatalogTable:
    fqn: str
    layer: str
    rows: int
    columns: list[CatalogColumn] = field(default_factory=list)
    annotation: TableAnnotation | None = None
    business_stewards: list[str] = field(default_factory=list)
    technical_stewards: list[str] = field(default_factory=list)

    @property
    def domain(self) -> str | None:
        return self.annotation.domain if self.annotation else None

    @property
    def subject_to_standard(self) -> bool:
        return self.layer in DOCUMENTED_LAYERS


def extract(con: duckdb.DuckDBPyConnection) -> list[CatalogTable]:
    """Metadatos técnicos de raw, staging y curated: columnas, tipos, filas y % de nulos."""
    tables = []
    rows = con.execute("""
        SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_schema IN ('raw', 'staging', 'curated') ORDER BY 1, 2""").fetchall()
    for schema, table in rows:
        fqn = f"{schema}.{table}"
        n = con.execute(f"SELECT count(*) FROM {fqn}").fetchone()[0]
        cols = con.execute("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position""",
                           [schema, table]).fetchall()
        nulls = con.execute(
            "SELECT " + ", ".join(f'count(*) - count("{c}")' for c, _ in cols) + f" FROM {fqn}"
        ).fetchone() if cols else ()
        tables.append(CatalogTable(fqn, schema, n, [
            CatalogColumn(fqn, c, t, (nulls[i] / n) if n else 0.0)
            for i, (c, t) in enumerate(cols)]))
    return tables


def sample_values(con: duckdb.DuckDBPyConnection, column: CatalogColumn, size: int) -> list[str]:
    return [r[0] for r in con.execute(
        f'SELECT CAST("{column.name}" AS VARCHAR) FROM {column.table} '
        f'WHERE "{column.name}" IS NOT NULL LIMIT {int(size)}').fetchall()]
