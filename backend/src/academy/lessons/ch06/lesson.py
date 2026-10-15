"""Lección 6: glosario de negocio, catálogo de datos, clasificación de PII y estándares.

Misma lógica que chapters/ch06_gestion_metadatos/run.py del laboratorio. Escribe en el
warehouse (comentarios y esquema meta): las lecciones 4, 5, 7 y 8 lo notan.
"""

from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
    BarItem,
    BarListBlock,
    CalloutBlock,
    Column,
    DocumentBlock,
    HeatmapBlock,
    HeatmapRow,
    Kpi,
    KpisBlock,
    ResultSection,
    TableBlock,
)
from academy.core.company import DOMAIN_NAMES
from academy.core.reporting import fmt_money, fmt_pct, render_template
from academy.core.warehouse import connect
from academy.lessons.base import InputSpec, LessonContext, LessonDef
from academy.lessons.ch03.lesson import TEAM
from academy.lessons.ch04.evidence import indicators

from .catalog import FORMAT_LABELS, CatalogInput, extract, sample_values
from .classify import ClassificationPolicy, classify
from .glossary import STATUS_LABELS, Glossary, broken_mappings, stewards_by_domain
from .publish import write_comments, write_meta
from .standards import StandardsInput, evaluate, maturity_metrics

LESSON_DIR = Path(__file__).parent
INPUTS = LESSON_DIR / "inputs"
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
LAYERS = ("raw", "staging", "curated")
SCOPE_LABELS = {"table": "Tablas", "column": "Columnas", "term": "Términos"}

CLASSIFICATION = InputSpec("classification", "Clasificación",
                           "Niveles de sensibilidad, reglas de detección de PII por nombre y "
                           "por contenido, y correcciones de los stewards.",
                           ClassificationPolicy, INPUTS / "classification.yaml")
GLOSSARY = InputSpec("glossary", "Glosario",
                     "Términos de negocio con su definición, dominio, responsable, estado y "
                     "columnas del warehouse que los implementan.",
                     Glossary, INPUTS / "glossary.yaml")
INPUT_SPECS = [
    GLOSSARY,
    InputSpec("catalog", "Catálogo",
              "Descripción, dominio y formato de cada tabla, y supuestos de valor.",
              CatalogInput, INPUTS / "catalog.yaml"),
    CLASSIFICATION,
    InputSpec("standards", "Estándares",
              "Estándares de metadatos que deben cumplir tablas, columnas y términos.",
              StandardsInput, INPUTS / "standards.yaml"),
]


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    glossary: Glossary = inputs["glossary"]
    catalog_in: CatalogInput = inputs["catalog"]
    policy: ClassificationPolicy = inputs["classification"]
    standards: StandardsInput = inputs["standards"]
    stewards = stewards_by_domain(ctx.input_of(3, TEAM).functional_roles)
    column_terms = glossary.column_terms()

    with connect(ctx.db_path) as con:
        before = indicators(con)["documented_tables"]
        tables = extract(con)
        unknown = sorted(set(catalog_in.tables) - {t.fqn for t in tables})
        for t in tables:
            t.annotation = catalog_in.tables.get(t.fqn)
            if t.domain and t.domain in stewards:
                t.business_stewards = stewards[t.domain].business
                t.technical_stewards = stewards[t.domain].technical
            for c in t.columns:
                c.term = column_terms.get(c.fqn)
                result = classify(c.fqn, c.name, sample_values(con, c, policy.sample_size),
                                  policy)
                c.level, c.category, c.method = result.level, result.category, result.method
        comments = write_comments(con, tables, glossary)
        write_meta(con, tables, glossary, stewards, {k: v.name for k, v in policy.levels.items()})
        after = indicators(con)["documented_tables"]
        has_lineage = con.execute("SELECT count(*) FROM information_schema.tables WHERE "
                                  "table_schema = 'meta' AND table_name = 'lineage_edges'"
                                  ).fetchone()[0]
        lineage_tables = {r[0] for r in con.execute(
            "SELECT DISTINCT target_table FROM meta.lineage_edges").fetchall()} if has_lineage \
            else set()

    columns = [c for t in tables for c in t.columns]
    broken = broken_mappings(glossary, {c.fqn for c in columns})
    compliance = evaluate(standards.standards, tables, glossary, stewards)
    maturity = maturity_metrics(tables, compliance, lineage_tables)
    restricted = [c for c in columns if policy.is_restricted(c.level)]
    level_order = sorted(policy.levels, key=lambda k: -policy.levels[k].order)
    level_names = {k: v.name for k, v in policy.levels.items()}
    matrix = []
    for level in level_order:
        row = {layer: sum(c.level == level for t in tables if t.layer == layer
                          for c in t.columns) for layer in LAYERS}
        row["_total"] = sum(row.values())
        matrix.append((level, row))
    by_domain = [(d, [t for t in glossary.terms if t.domain == d])
                 for d in DOMAIN_NAMES if any(t.domain == d for t in glossary.terms)]
    domains = [d for d in DOMAIN_NAMES if any(t.domain == d for t in tables)]
    sensitive = {t.fqn: sum(policy.levels[c.level].order >= 2 for c in t.columns)
                 for t in tables}
    value = catalog_in.value.catalog_value + catalog_in.value.glossary_value

    summary: list = [KpisBlock(items=[
        Kpi(label="Tablas curated documentadas", value=f"{fmt_pct(before)} → {fmt_pct(after)}",
            detail="Antes y después de ejecutar esta lección",
            tone="good" if after >= 1 else "warning"),
        Kpi(label="Catálogo", value=f"{len(tables)} tablas", detail=f"{len(columns)} columnas"),
        Kpi(label="Columnas restringidas (PII)", value=str(len(restricted)),
            tone="warning" if restricted else None),
        Kpi(label="Valor estimado al año", value=fmt_money(value),
            detail="Menos tiempo buscando datos y menos conciliaciones"),
    ]), CalloutBlock(
        tone="info", title="Lo que deja en el warehouse",
        text=f"{comments} comentarios (COMMENT ON) y el esquema meta con el glosario y el "
             "catálogo. Vuelve a ejecutar las lecciones 4, 5 y 8: su evidencia cambia.")]
    for fqn in unknown:
        summary.append(CalloutBlock(
            tone="info", title=f"{fqn} todavía no existe",
            text="El catálogo la describe, pero la crea la lección 10 (cliente único). Se "
                 "omite hasta entonces."))
    for term, col in broken:
        summary.append(CalloutBlock(tone="bad", title=f"Vínculo roto: {term}",
                                    text=f"El glosario apunta a {col}, que no existe."))

    glossary_blocks = [TableBlock(
        title="Glosario de negocio",
        columns=[Column(key="term", label="Término"), Column(key="domain", label="Dominio"),
                 Column(key="definition", label="Definición"),
                 Column(key="source", label="Fuente autorizada"),
                 Column(key="status", label="Estado"),
                 Column(key="columns", label="Columnas", align="right")],
        rows=[{"term": t.term, "domain": DOMAIN_NAMES.get(t.domain, t.domain),
               "definition": t.definition, "source": t.authorized_source or "—",
               "status": STATUS_LABELS.get(t.status, t.status), "columns": str(len(t.columns))}
              for t in glossary.terms])]
    counts = Counter(t.status for t in glossary.terms)
    if counts.get("draft") or counts.get("in_review"):
        glossary_blocks.append(CalloutBlock(
            tone="info", title="Términos aún sin aprobar",
            text=", ".join(f"{STATUS_LABELS.get(s, s)}: {n}" for s, n in counts.items()
                           if s != "approved") + ". Un término solo es oficial cuando su "
                 "responsable lo aprueba."))

    catalog_blocks = [TableBlock(
        title="Catálogo de datos",
        columns=[Column(key="fqn", label="Tabla"), Column(key="domain", label="Dominio"),
                 Column(key="rows", label="Filas", align="right"),
                 Column(key="desc", label="Descripción"),
                 Column(key="stewards", label="Stewards"),
                 Column(key="sensitive", label="Columnas sensibles", align="right")],
        rows=[{"fqn": t.fqn, "domain": DOMAIN_NAMES.get(t.domain or "", "—"),
               "rows": f"{t.rows:,}".replace(",", "."),
               "desc": t.annotation.description if t.annotation else "⚠️ sin documentar",
               "stewards": ", ".join(t.business_stewards) or "—",
               "sensitive": str(sensitive[t.fqn])} for t in tables])]

    pii_blocks = [
        HeatmapBlock(
            title="Columnas por nivel de sensibilidad y capa",
            subtitle="Más oscuro = más columnas. Los datos personales llegan en raw y se "
                     "propagan a las capas siguientes.",
            columns=[*LAYERS, "Total"],
            rows=[HeatmapRow(label=level_names[level],
                             values=[row[layer] for layer in LAYERS] + [row["_total"]])
                  for level, row in matrix],
            min_value=0, max_value=max((row["_total"] for _, row in matrix), default=1)),
        TableBlock(
            title="Columnas restringidas",
            description="Detectadas por el nombre de la columna o por el contenido de una "
                        f"muestra de {policy.sample_size} valores.",
            columns=[Column(key="col", label="Columna"), Column(key="cat", label="Categoría"),
                     Column(key="method", label="Cómo se detectó")],
            rows=[{"col": c.fqn, "cat": c.category, "method": c.method} for c in restricted]),
    ]

    standards_blocks = [
        BarListBlock(
            title="Cumplimiento de los estándares de metadatos",
            items=[BarItem(label=f"{c.standard.id} · {SCOPE_LABELS[c.standard.applies_to]}",
                           value=c.rate, display=f"{c.passed}/{c.total}", target=1.0,
                           ok=c.rate >= 1, detail=c.standard.text) for c in compliance],
            legend="De 0 % a 100 % de los elementos que cumplen · pasa el ratón por encima "
                   "para leer cada estándar"),
        TableBlock(
            title="Madurez del catálogo",
            columns=[Column(key="m", label="Métrica"),
                     Column(key="v", label="Cumplen", align="right")],
            rows=[{"m": m, "v": f"{ok}/{total} ({fmt_pct(ok / total if total else 0)})"}
                  for m, ok, total in maturity]),
    ]

    common = {"company": COMPANY, "domain_names": DOMAIN_NAMES}
    docs = [
        DocumentBlock(title="Glosario de negocio", filename="business_glossary.md",
                      markdown=render_template(
                          TEMPLATES, "business_glossary.md.j2", **common, terms=glossary.terms,
                          status_counts=sorted(counts.items()), status_labels=STATUS_LABELS,
                          by_domain=by_domain, stewards=stewards)),
        DocumentBlock(title="Catálogo de datos", filename="data_catalog.md",
                      markdown=render_template(
                          TEMPLATES, "data_catalog.md.j2", **common, tables=tables,
                          format_labels=FORMAT_LABELS, sensitive=sensitive,
                          level_names=level_names)),
        DocumentBlock(title="Clasificación de PII", filename="pii_classification.md",
                      markdown=render_template(
                          TEMPLATES, "pii_classification.md.j2", **common,
                          sample_size=policy.sample_size, layers=LAYERS, matrix=matrix,
                          level_names=level_names, restricted=restricted,
                          overrides=policy.overrides)),
        DocumentBlock(title="Estándares de metadatos", filename="metadata_standards.md",
                      markdown=render_template(
                          TEMPLATES, "metadata_standards.md.j2", **common,
                          pub=standards.publication, compliance=compliance,
                          scope_labels=SCOPE_LABELS, domains=domains, maturity=maturity,
                          broken=broken, v=catalog_in.value)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Glosario", blocks=glossary_blocks),
        ResultSection(title="Catálogo", blocks=catalog_blocks),
        ResultSection(title="Datos personales", blocks=pii_blocks),
        ResultSection(title="Estándares", blocks=standards_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=6, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
