"""Uso de los resultados: aciertos frente al solucionario, incidencias, certificación y valor."""

from dataclasses import dataclass

import duckdb

from .rules import DQInput, RuleResult

SEVERITY_LABELS = {1: "Sev1 · material", 2: "Sev2 · relevante", 3: "Sev3 · menor"}


# --- Aciertos frente a los defectos sembrados ---------------------------------------------

@dataclass(frozen=True)
class Detection:
    defect: str
    rule_id: str
    seeded: int
    detected: int
    true_positives: int

    @property
    def recall(self) -> float:
        return self.true_positives / self.seeded if self.seeded else 1.0

    @property
    def precision(self) -> float:
        return self.true_positives / self.detected if self.detected else 1.0


def evaluate_detection(results: list[RuleResult], seeded: dict[str, list[str]],
                       mapping: dict[str, str]) -> list[Detection]:
    by_rule = {r.rule.id: set(r.failed_keys) for r in results}
    out = []
    for defect, rule_id in mapping.items():
        truth, found = set(seeded.get(defect, [])), by_rule[rule_id]
        out.append(Detection(defect, rule_id, len(truth), len(found), len(truth & found)))
    return out


def inherited_postal_defects(con: duckdb.DuckDBPyConnection, flagged: list[str],
                             seeded_orders: list[str], seeded_customers: list[str]) -> int:
    """Pedidos marcados fuera del solucionario cuyo cliente ya tenía el código postal mal."""
    extra = sorted(set(flagged) - set(seeded_orders))
    if not extra:
        return 0
    return con.execute(
        "SELECT count(*) FROM staging.stg_ecom_orders "
        "WHERE list_contains(?, order_line_id) AND list_contains(?, ecom_user_id)",
        [extra, seeded_customers]).fetchone()[0]


# --- Incidencias -------------------------------------------------------------------------

@dataclass(frozen=True)
class Issue:
    id: str
    result: RuleResult
    steward: str
    status: str  # abierta | aceptada
    disposition: str | None

    @property
    def severity(self) -> int:
        return self.result.rule.severity


def issue_log(results: list[RuleResult], inp: DQInput,
              stewards: dict[str, list[str]]) -> list[Issue]:
    """Una incidencia por regla que no cumple su umbral; las disposiciones las cierran."""
    issues = []
    for r in sorted((r for r in results if not r.meets_threshold),
                    key=lambda r: (r.rule.severity, r.pass_rate)):
        domain = inp.tables[r.rule.table].domain
        d = inp.dispositions.get(r.rule.id)
        issues.append(Issue(
            f"INC-{len(issues) + 1:03d}", r, ", ".join(stewards.get(domain, [])) or "⚠️ sin steward",
            "aceptada" if d else "abierta",
            f"{d.decision} por {d.by} el {d.date:%d/%m/%Y}: {d.reason}" if d else None))
    return issues


# --- Certificación -----------------------------------------------------------------------

@dataclass(frozen=True)
class CertificationResult:
    table: str
    certified: bool
    reasons: list[str]


def upstream_tables(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    """Tablas de las que depende `table`, según el linaje del capítulo 7 (si existe)."""
    try:
        edges = con.execute("SELECT DISTINCT source_table, target_table FROM meta.lineage_edges"
                            ).fetchall()
    except duckdb.CatalogException:
        return set()
    parents: dict[str, set[str]] = {}
    for s, t in edges:
        parents.setdefault(t, set()).add(s)
    seen, stack = set(), [table]
    while stack:
        for p in parents.get(stack.pop(), set()):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


def certify(con: duckdb.DuckDBPyConnection, tables: list[str], results: list[RuleResult],
            inp: DQInput) -> list[CertificationResult]:
    """Certifica un dataset curado si él y sus fuentes cumplen las reglas bloqueantes y,
    además, tiene linaje, documentación y steward."""
    blocking = inp.certification.max_severity_blocking
    documented = {f"{s}.{t}" for s, t in con.execute(
        "SELECT schema_name, table_name FROM duckdb_tables() WHERE comment <> ''").fetchall()}
    try:
        stewarded = {r[0] for r in con.execute(
            "SELECT table_fqn FROM meta.catalog_tables WHERE business_steward <> ''").fetchall()}
    except duckdb.CatalogException:
        stewarded = set()
    out = []
    for table in tables:
        upstream = upstream_tables(con, table)
        reasons = []
        if not upstream:
            reasons.append("Sin linaje documentado (capítulo 7)")
        if table not in documented:
            reasons.append("Sin documentar (capítulo 6)")
        if table not in stewarded:
            reasons.append("Sin steward de negocio")
        for r in results:
            if r.rule.severity <= blocking and not r.meets_threshold \
                    and r.rule.table in upstream | {table}:
                where = "" if r.rule.table == table else f" en la fuente {r.rule.table}"
                reasons.append(f"{r.rule.id} no cumple{where} ({r.pass_rate:.2%} < "
                               f"{r.rule.threshold:.1%})")
        out.append(CertificationResult(table, not reasons, reasons))
    return out


# --- Valor -------------------------------------------------------------------------------

def marketable_contacts(con: duckdb.DuckDBPyConnection, valid_email_pattern: str) -> tuple:
    """(clientes del CRM, aptos para marketing: email válido y consentimiento)."""
    total, ok = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE consent_marketing AND "
        "regexp_full_match(email, ?)) FROM staging.stg_crm_customers",
        [valid_email_pattern.strip("^$")]).fetchone()
    return total, ok
