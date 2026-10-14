"""Parámetros del generador: volumen, presencia en sistemas y tasas de defectos sembrados."""

from dataclasses import dataclass, field
from datetime import date

DEFAULT_SEED = 42


@dataclass(frozen=True)
class Scale:
    persons: int = 2000  # clientes reales (cada uno puede estar en varios sistemas)
    products: int = 300
    suppliers: int = 40
    stores: int = 30
    pos_lines: int = 20000  # líneas de ticket en tienda
    ecom_lines: int = 8000  # líneas de pedido online


@dataclass(frozen=True)
class Presence:
    """Probabilidad de que una persona esté registrada en cada sistema."""

    crm: float = 0.85
    ecom: float = 0.55
    pos: float = 0.45


@dataclass(frozen=True)
class DefectRates:
    """Proporción exacta de registros afectados por cada defecto sembrado."""

    crm_null_email: float = 0.05  # email obligatorio vacío
    crm_duplicates: float = 0.03  # la misma persona dada de alta dos veces en el CRM
    ecom_name_no_accents: float = 0.30  # nombre escrito sin tildes
    ecom_bad_date_format: float = 0.20  # fecha de alta en dd/mm/aaaa en vez de ISO
    ecom_invalid_postal: float = 0.04  # código postal de cliente inválido
    order_invalid_postal: float = 0.03  # código postal de envío inválido
    pos_missing_phone: float = 0.15  # tarjeta de fidelización sin teléfono
    pos_negative_price: float = 0.005  # precio unitario negativo en el ticket
    product_missing_category: float = 0.05  # producto sin categoría
    supplier_missing_contact: float = 0.10  # proveedor sin persona ni email de contacto


@dataclass(frozen=True)
class SyntheticConfig:
    seed: int = DEFAULT_SEED
    locale: str = "es_ES"
    start: date = date(2025, 1, 1)
    end: date = date(2026, 9, 30)
    scale: Scale = field(default_factory=Scale)
    presence: Presence = field(default_factory=Presence)
    defects: DefectRates = field(default_factory=DefectRates)
