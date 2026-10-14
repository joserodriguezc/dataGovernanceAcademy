"""Generador de datos sintéticos de NovaMercado.

Crea personas "reales" que después aparecen en el CRM, el e-commerce y las tiendas con
las variaciones propias de cada sistema, más el catálogo, los proveedores, las tiendas y
las ventas. Todo es determinista para una misma semilla.

Además de las tablas, devuelve el solucionario (`truth`): qué registros de cada sistema
son la misma persona y qué registros llevan cada defecto sembrado. Los capítulos lo usan
solo para medir si sus detecciones aciertan, nunca como entrada.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from .config import SyntheticConfig
from .noise import invalid_postal, phone_format, pick, slug, strip_accents, typo

CATEGORIES = {  # categoría -> rango de precio unitario en USD
    "Alimentación": (1, 15), "Bebidas": (1, 20), "Limpieza": (2, 18), "Hogar": (5, 120),
    "Electrónica": (15, 600), "Textil": (8, 90), "Juguetes": (6, 80), "Perfumería": (4, 70),
    "Mascotas": (3, 60), "Jardín": (5, 150),
}
REGIONS = ("Norte", "Sur", "Este", "Oeste", "Centro")
EMAIL_DOMAINS = ("gmail.com", "hotmail.com", "yahoo.es", "outlook.com", "correo.es")
LOYALTY_TIERS = ("Bronce", "Plata", "Oro")
ORDER_STATUS = ("entregado", "entregado", "entregado", "entregado", "devuelto", "cancelado")


@dataclass
class SyntheticDataset:
    tables: dict[str, pd.DataFrame]  # nombre de tabla raw -> datos
    customer_links: pd.DataFrame  # person_id, system, source_id
    defects: dict[str, list[str]]  # tipo de defecto -> ids afectados


class _Generator:
    def __init__(self, cfg: SyntheticConfig) -> None:
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.fake = Faker(cfg.locale)
        self.fake.seed_instance(cfg.seed)
        self.defects: dict[str, list[str]] = {}
        self.links: list[tuple[str, str, str]] = []

    # --- utilidades --------------------------------------------------------------------
    def _date(self, start: date, end: date) -> date:
        return start + timedelta(days=int(self.rng.integers(0, (end - start).days + 1)))

    def _ts(self) -> datetime:
        d = self._date(self.cfg.start, self.cfg.end)
        return datetime(d.year, d.month, d.day, int(self.rng.integers(9, 22)),
                        int(self.rng.integers(0, 60)))

    def _mark(self, defect: str, ids: list[str]) -> None:
        self.defects[defect] = sorted(ids)

    # --- maestros ----------------------------------------------------------------------
    def persons(self) -> pd.DataFrame:
        rows = []
        for i in range(self.cfg.scale.persons):
            first = self.fake.first_name()
            last = f"{self.fake.last_name()} {self.fake.last_name()}"
            rows.append({
                "person_id": f"P{i + 1:06d}",
                "first_name": first,
                "last_name": last,
                "email": f"{slug(first)}.{slug(last.split()[0])}{int(self.rng.integers(1, 999))}"
                         f"@{self.rng.choice(EMAIL_DOMAINS)}",
                "phone": f"{self.rng.choice(['6', '7'])}{int(self.rng.integers(0, 10**8)):08d}",
                "birth_date": self._date(date(1950, 1, 1), date(2006, 12, 31)),
                "postal_code": self.fake.postcode(),
                "city": self.fake.city(),
                "signup": self._date(date(2018, 1, 1), self.cfg.end),
            })
        return pd.DataFrame(rows)

    def stores(self) -> pd.DataFrame:
        rows = []
        for i in range(self.cfg.scale.stores):
            city = self.fake.city()
            rows.append({
                "store_id": f"T{i + 1:03d}",
                "store_name": f"NovaMercado {city}",
                "region": REGIONS[i % len(REGIONS)],
                "city": city,
                "opened_at": self._date(date(2005, 1, 1), date(2024, 12, 31)).isoformat(),
            })
        return pd.DataFrame(rows)

    def suppliers(self) -> pd.DataFrame:
        n = self.cfg.scale.suppliers
        missing = pick(n, self.cfg.defects.supplier_missing_contact, self.rng)
        rows = []
        for i in range(n):
            sid = f"SUP-{i + 1:03d}"
            name = self.fake.company()
            has_contact = i not in missing
            tax_id = f"{self.rng.choice(list('ABCDEFGH'))}{int(self.rng.integers(0, 10**8)):08d}"
            rows.append({
                "supplier_id": sid,
                "supplier_name": name,
                "tax_id": tax_id,
                "contact_name": self.fake.name() if has_contact else None,
                "contact_email": f"compras@{slug(name)[:15]}.com" if has_contact else None,
                "country": "España" if self.rng.random() < 0.8 else self.fake.country(),
            })
        self._mark("supplier_missing_contact", [rows[i]["supplier_id"] for i in missing])
        return pd.DataFrame(rows)

    def products(self, suppliers: pd.DataFrame) -> pd.DataFrame:
        n = self.cfg.scale.products
        missing = pick(n, self.cfg.defects.product_missing_category, self.rng)
        categories = list(CATEGORIES)
        rows = []
        for i in range(n):
            category = categories[int(self.rng.integers(0, len(categories)))]
            low, high = CATEGORIES[category]
            price = round(float(self.rng.uniform(low, high)), 2)
            rows.append({
                "sku": f"SKU-{i + 1:05d}",
                "product_name": f"{category} {self.fake.word().capitalize()} "
                                f"{self.fake.color_name().lower()}",
                "category": None if i in missing else category,
                "brand": self.fake.last_name(),
                "unit_price": price,
                "unit_cost": round(price * float(self.rng.uniform(0.55, 0.8)), 2),
                "supplier_id": suppliers["supplier_id"].iloc[
                    int(self.rng.integers(0, len(suppliers)))],
            })
        self._mark("product_missing_category", [rows[i]["sku"] for i in missing])
        return pd.DataFrame(rows)

    # --- clientes por sistema ----------------------------------------------------------
    def crm_customers(self, persons: pd.DataFrame) -> pd.DataFrame:
        d, rows = self.cfg.defects, []
        present = persons[self.rng.random(len(persons)) < self.cfg.presence.crm]
        for _, p in present.iterrows():
            rows.append({
                "customer_id": f"CRM-{len(rows) + 1:06d}", "_person": p.person_id,
                "first_name": p.first_name, "last_name": p.last_name, "email": p.email,
                "phone": phone_format(p.phone, "international"),
                "birth_date": p.birth_date.isoformat(), "postal_code": p.postal_code,
                "city": p.city, "loyalty_tier": self.rng.choice(LOYALTY_TIERS),
                "consent_marketing": bool(self.rng.random() < 0.7),
                "created_at": p.signup.isoformat(),
            })
        # Duplicados internos: la misma persona dada de alta otra vez con una errata
        dupes = pick(len(rows), d.crm_duplicates, self.rng)
        dup_ids = []
        for i in sorted(dupes):
            original = rows[i]
            copy = {**original, "customer_id": f"CRM-{len(rows) + 1:06d}",
                    "first_name": typo(original["first_name"], self.rng),
                    "created_at": self._date(date.fromisoformat(original["created_at"]),
                                             self.cfg.end).isoformat()}
            rows.append(copy)
            dup_ids += [original["customer_id"], copy["customer_id"]]
        self._mark("crm_duplicates", dup_ids)
        null_email = pick(len(rows), d.crm_null_email, self.rng)
        for i in null_email:
            rows[i]["email"] = None
        self._mark("crm_null_email", [rows[i]["customer_id"] for i in null_email])
        self.links += [(r["_person"], "crm", r["customer_id"]) for r in rows]
        return pd.DataFrame(rows).drop(columns="_person")

    def ecom_customers(self, persons: pd.DataFrame) -> pd.DataFrame:
        d, rows = self.cfg.defects, []
        present = persons[self.rng.random(len(persons)) < self.cfg.presence.ecom]
        for _, p in present.iterrows():
            email = p.email.upper() if self.rng.random() < 0.1 else p.email
            rows.append({
                "ecom_user_id": f"WEB{len(rows) + 1:06d}", "_person": p.person_id,
                "full_name": f"{p.first_name} {p.last_name}", "email": email,
                "phone": phone_format(p.phone, "digits"),
                "postal_code": p.postal_code, "city": p.city,
                "created_at": p.signup.isoformat(),
            })
        n = len(rows)
        no_accents = pick(n, d.ecom_name_no_accents, self.rng)
        for i in no_accents:
            rows[i]["full_name"] = strip_accents(rows[i]["full_name"])
        bad_date = pick(n, d.ecom_bad_date_format, self.rng)
        for i in bad_date:
            rows[i]["created_at"] = date.fromisoformat(rows[i]["created_at"]).strftime("%d/%m/%Y")
        bad_postal = pick(n, d.ecom_invalid_postal, self.rng)
        for i in bad_postal:
            rows[i]["postal_code"] = invalid_postal(self.rng)
        self._mark("ecom_bad_date_format", [rows[i]["ecom_user_id"] for i in bad_date])
        self._mark("ecom_invalid_postal", [rows[i]["ecom_user_id"] for i in bad_postal])
        self.links += [(r["_person"], "ecom", r["ecom_user_id"]) for r in rows]
        return pd.DataFrame(rows).drop(columns="_person")

    def pos_customers(self, persons: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
        rows = []
        present = persons[self.rng.random(len(persons)) < self.cfg.presence.pos]
        for _, p in present.iterrows():
            first_surname = p.last_name.split()[0]
            rows.append({
                "card_id": f"FID{len(rows) + 1:07d}", "_person": p.person_id,
                "holder_name": f"{p.first_name} {first_surname}".upper(),
                "phone": phone_format(p.phone, "dashes"), "postal_code": p.postal_code,
                "home_store_id": stores["store_id"].iloc[int(self.rng.integers(0, len(stores)))],
            })
        missing = pick(len(rows), self.cfg.defects.pos_missing_phone, self.rng)
        for i in missing:
            rows[i]["phone"] = None
        self._mark("pos_missing_phone", [rows[i]["card_id"] for i in missing])
        self.links += [(r["_person"], "pos", r["card_id"]) for r in rows]
        return pd.DataFrame(rows).drop(columns="_person")

    # --- transacciones -----------------------------------------------------------------
    def pos_sales(self, products: pd.DataFrame, stores: pd.DataFrame,
                  cards: pd.DataFrame) -> pd.DataFrame:
        n = self.cfg.scale.pos_lines
        negative = pick(n, self.cfg.defects.pos_negative_price, self.rng)
        rows, ticket, lines_left, line_no = [], 0, 0, 0
        for i in range(n):
            if lines_left == 0:  # nuevo ticket con 1-6 líneas
                ticket += 1
                lines_left = int(self.rng.integers(1, 7))
                line_no = 0
                store = stores["store_id"].iloc[int(self.rng.integers(0, len(stores)))]
                ts = self._ts()
                card = (cards["card_id"].iloc[int(self.rng.integers(0, len(cards)))]
                        if self.rng.random() < 0.4 else None)
            lines_left -= 1
            line_no += 1
            prod = products.iloc[int(self.rng.integers(0, len(products)))]
            price = -prod.unit_price if i in negative else prod.unit_price
            qty = int(self.rng.integers(1, 6))
            rows.append({
                "line_id": f"TK{ticket:07d}-{line_no}",
                "ticket_id": f"TK{ticket:07d}", "store_id": store,
                "sale_ts": ts.isoformat(sep=" "), "card_id": card, "sku": prod.sku,
                "quantity": qty, "unit_price": price, "amount": round(qty * price, 2),
            })
        self._mark("pos_negative_price", [rows[i]["line_id"] for i in negative])
        return pd.DataFrame(rows)

    def ecom_orders(self, products: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
        n = self.cfg.scale.ecom_lines
        bad_postal = pick(n, self.cfg.defects.order_invalid_postal, self.rng)
        rows, order, lines_left = [], 0, 0
        for i in range(n):
            if lines_left == 0:  # nuevo pedido con 1-3 líneas del mismo usuario
                order += 1
                lines_left = int(self.rng.integers(1, 4))
                user = users.iloc[int(self.rng.integers(0, len(users)))]
                ts = self._ts()
                status = self.rng.choice(ORDER_STATUS)
            lines_left -= 1
            prod = products.iloc[int(self.rng.integers(0, len(products)))]
            postal = invalid_postal(self.rng) if i in bad_postal else user.postal_code
            rows.append({
                "order_line_id": f"WO{i + 1:07d}", "order_id": f"WO{order:06d}",
                "ecom_user_id": user.ecom_user_id, "order_ts": ts.isoformat(sep=" "),
                "sku": prod.sku, "quantity": int(self.rng.integers(1, 4)),
                "unit_price": prod.unit_price, "shipping_postal_code": postal,
                "status": status,
            })
        self._mark("order_invalid_postal", [rows[i]["order_line_id"] for i in bad_postal])
        return pd.DataFrame(rows)


def generate(cfg: SyntheticConfig | None = None) -> SyntheticDataset:
    """Genera todas las tablas raw de NovaMercado y su solucionario."""
    g = _Generator(cfg or SyntheticConfig())
    persons = g.persons()
    stores = g.stores()
    suppliers = g.suppliers()
    products = g.products(suppliers)
    crm = g.crm_customers(persons)
    ecom = g.ecom_customers(persons)
    pos = g.pos_customers(persons, stores)
    tables = {
        "crm_customers": crm,
        "ecom_customers": ecom,
        "pos_loyalty_cards": pos,
        "erp_stores": stores,
        "erp_suppliers": suppliers,
        "erp_products": products,
        "pos_sales": g.pos_sales(products, stores, pos),
        "ecom_orders": g.ecom_orders(products, ecom),
    }
    links = pd.DataFrame(g.links, columns=["person_id", "system", "source_id"])
    return SyntheticDataset(tables, links, dict(sorted(g.defects.items())))
