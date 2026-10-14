"""Espacio de trabajo: los datos sintéticos de NovaMercado y su warehouse DuckDB.

Es la Fase 0 del laboratorio dentro de la app. El alumno puede cambiar la semilla, el
volumen de clientes y las tasas de defectos sembrados, y reconstruir: las lecciones técnicas
trabajan sobre lo que haya construido.
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from academy.core.synthetic import DefectRates, Scale, SyntheticConfig, generate, write_dataset
from academy.core.synthetic.io import read_truth
from academy.core.warehouse import build_warehouse, connect, table_counts

_DEFAULT_DEFECTS = DefectRates()


def _rate(name: str) -> float:
    return Field(getattr(_DEFAULT_DEFECTS, name), ge=0, le=0.5)


class DefectSettings(BaseModel):
    """Proporción de registros con cada defecto sembrado (0 a 0,5)."""

    crm_null_email: float = _rate("crm_null_email")
    crm_duplicates: float = _rate("crm_duplicates")
    ecom_name_no_accents: float = _rate("ecom_name_no_accents")
    ecom_bad_date_format: float = _rate("ecom_bad_date_format")
    ecom_invalid_postal: float = _rate("ecom_invalid_postal")
    order_invalid_postal: float = _rate("order_invalid_postal")
    pos_missing_phone: float = _rate("pos_missing_phone")
    pos_negative_price: float = _rate("pos_negative_price")
    product_missing_category: float = _rate("product_missing_category")
    supplier_missing_contact: float = _rate("supplier_missing_contact")


class WorkspaceSettings(BaseModel):
    seed: int = Field(42, ge=0)
    persons: int = Field(Scale.persons, ge=100, le=10000)
    defects: DefectSettings = DefectSettings()

    def synthetic_config(self) -> SyntheticConfig:
        return SyntheticConfig(seed=self.seed, scale=Scale(persons=self.persons),
                               defects=DefectRates(**self.defects.model_dump()))


LABELS = {
    "seed": "Semilla (mismos datos con la misma semilla)",
    "persons": "Clientes reales (100 a 10.000)",
    "defects": "Defectos sembrados (proporción de registros)",
    "crm_null_email": "CRM: email vacío",
    "crm_duplicates": "CRM: cliente dado de alta dos veces",
    "ecom_name_no_accents": "E-commerce: nombre sin tildes",
    "ecom_bad_date_format": "E-commerce: fecha de alta en dd/mm/aaaa",
    "ecom_invalid_postal": "E-commerce: código postal inválido",
    "order_invalid_postal": "Pedidos: código postal de envío inválido",
    "pos_missing_phone": "Tiendas: tarjeta sin teléfono",
    "pos_negative_price": "Tiendas: precio unitario negativo",
    "product_missing_category": "Productos: sin categoría",
    "supplier_missing_contact": "Proveedores: sin contacto",
}


class TableCount(BaseModel):
    table: str
    layer: str
    rows: int


class WorkspaceStatus(BaseModel):
    built: bool
    built_at: datetime | None = None
    built_with: WorkspaceSettings | None = None
    settings: WorkspaceSettings
    pending_changes: bool  # los parámetros guardados no son los del warehouse construido
    tables: list[TableCount] = []
    seeded_defects: dict[str, int] = {}


class Workspace:
    def __init__(self, data_dir: Path):
        self.dir = data_dir / "workspace"
        self.raw_dir = self.dir / "raw"
        self.db_path = self.dir / "novamercado.duckdb"
        self._settings_file = self.dir / "settings.json"
        self._build_file = self.dir / "build.json"

    @property
    def built(self) -> bool:
        return self.db_path.exists() and self._build_file.exists()

    def settings(self) -> WorkspaceSettings:
        if self._settings_file.exists():
            return WorkspaceSettings.model_validate_json(self._settings_file.read_text("utf-8"))
        return WorkspaceSettings()

    def save_settings(self, data: dict) -> WorkspaceSettings:
        settings = WorkspaceSettings.model_validate(data)  # lanza ValidationError
        self.dir.mkdir(parents=True, exist_ok=True)
        self._settings_file.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        return settings

    def build(self) -> WorkspaceStatus:
        """Genera los CSV y el solucionario, y reconstruye el warehouse desde cero."""
        settings = self.settings()
        shutil.rmtree(self.raw_dir, ignore_errors=True)
        self.db_path.unlink(missing_ok=True)
        self._build_file.unlink(missing_ok=True)
        write_dataset(generate(settings.synthetic_config()), self.raw_dir)
        build_warehouse(self.db_path, self.raw_dir)
        self._build_file.write_text(json.dumps({
            "built_at": datetime.now(UTC).isoformat(),
            "settings": settings.model_dump(mode="json"),
        }, indent=2), encoding="utf-8")
        return self.status()

    def reset(self) -> WorkspaceStatus:
        """Borra datos y warehouse; conserva los parámetros."""
        shutil.rmtree(self.raw_dir, ignore_errors=True)
        self.db_path.unlink(missing_ok=True)
        self._build_file.unlink(missing_ok=True)
        return self.status()

    def status(self) -> WorkspaceStatus:
        settings = self.settings()
        if not self.built:
            return WorkspaceStatus(built=False, settings=settings, pending_changes=False)
        info = json.loads(self._build_file.read_text(encoding="utf-8"))
        built_with = WorkspaceSettings.model_validate(info["settings"])
        with connect(self.db_path, read_only=True) as con:
            counts = table_counts(con)
        _, defects = read_truth(self.raw_dir)
        return WorkspaceStatus(
            built=True, built_at=datetime.fromisoformat(info["built_at"]), built_with=built_with,
            settings=settings, pending_changes=settings != built_with,
            tables=[TableCount(table=t, layer=t.split(".")[0], rows=n) for t, n in counts.items()],
            seeded_defects={k: len(v) for k, v in defects.items()},
        )



