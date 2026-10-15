"""Lección 7: metadatos técnicos y linaje de datos a nivel de columna.

Misma lógica que chapters/ch07_metadatos_tecnicos_linaje/run.py del laboratorio. Analiza el
SQL del warehouse y publica el linaje en meta.lineage_edges: las lecciones 4, 5 y 8 lo notan.
"""

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
    CalloutBlock,
    Column,
    DocumentBlock,
    GraphBlock,
    GraphEdge,
    GraphNode,
    Kpi,
    KpisBlock,
    ResultSection,
    TableBlock,
)
from academy.core.reporting import fmt_money, fmt_num, fmt_pct, render_template
from academy.core.warehouse import connect, sql_files
from academy.lessons.base import InputSpec, LessonContext, LessonDef
from academy.lessons.ch04.evidence import indicators
from academy.lessons.ch06.lesson import GLOSSARY

from .analysis import (
    LineageInput,
    impact,
    maturity_metrics,
    path_to,
    pii_reaching,
    reach_curated,
    validate,
)
from .lineage import build_lineage, column_graph, table_graph
from .publish import write_lineage

LESSON_DIR = Path(__file__).parent
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
LAYERS = ["sistema", "raw", "staging", "curated"]
LAYER_LABELS = {"sistema": "Sistemas de origen", "raw": "Raw", "staging": "Staging",
                "curated": "Curated"}

INPUT_SPECS = [
    InputSpec("lineage", "Linaje",
              "Sistemas de origen, métricas críticas, la narrativa que se quiere validar y "
              "supuestos de valor. El linaje en sí se calcula del SQL, no se escribe a mano.",
              LineageInput, LESSON_DIR / "inputs" / "lineage.yaml"),
]


def _has_table(con, schema: str, table: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE "
                            "table_schema = ? AND table_name = ?", [schema, table]).fetchone()[0])


def _layer(node: str) -> str:
    return node.split(".")[0] if node.split(".")[0] in LAYERS else "curated"


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    inp: LineageInput = inputs["lineage"]
    terms = ctx.input_of(6, GLOSSARY).column_terms()

    with connect(ctx.db_path) as con:
        before = indicators(con)["lineage_coverage"]
        edges, steps = build_lineage(con, sql_files(), {k: s.name for k, s in
                                                         inp.source_systems.items()})
        write_lineage(con, edges, steps)
        after = indicators(con)["lineage_coverage"]
        raw_columns = [f"raw.{t}.{c}" for t, c in con.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'raw'").fetchall()]
        curated = [f"curated.{t}" for (t,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'curated'"
        ).fetchall()]
        documented = {f"{s}.{t}" for s, t in con.execute(
            "SELECT schema_name, table_name FROM duckdb_tables() WHERE comment IS NOT NULL "
            "AND comment <> ''").fetchall()}
        pii_known = _has_table(con, "meta", "catalog_columns")
        pii = [r[0] for r in con.execute(
            "SELECT table_fqn || '.' || column_name FROM meta.catalog_columns "
            "WHERE classification = 'restricted'").fetchall()] if pii_known else []

    g, tg = column_graph(edges), table_graph(edges)
    missing = [m.column for m in inp.critical_metrics if m.column not in g]
    if missing or inp.validation.business_element not in g:
        raise ValueError("Hay métricas críticas cuyas columnas no están en el linaje: "
                         f"{missing or [inp.validation.business_element]}")

    layers = [(LAYER_LABELS[key], sorted(n for n in tg if n.split(".")[0] == key))
              for key in LAYERS]
    raw_by_system: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.kind == "carga":
            raw_by_system[e.source_table.split(".")[1]].append(e.target_table)
    columns_by_table: dict[str, dict[str, dict]] = defaultdict(dict)
    for e in edges:
        if e.target_column is None or e.kind == "carga":
            continue
        info = columns_by_table[e.target_table].setdefault(
            e.target_column, {"kinds": [], "expressions": [], "sources": []})
        for key, value in (("kinds", e.kind), ("expressions", e.expression),
                           ("sources", e.source if e.source_column else None)):
            if value and value not in info[key]:
                info[key].append(value)
    kpi = path_to(g, inp.validation.business_element)
    kpi_edges = sorted((s, t, d["kind"]) for s, t, d in kpi.edges(data=True))
    result = validate(g, steps, inp.validation)
    rows = []
    for c in sorted(set(result.actual_sources) | set(inp.validation.claimed_sources)):
        claimed, actual = c in inp.validation.claimed_sources, c in result.actual_sources
        reading = ("Confirmado" if claimed and actual else
                   "⚠️ La narrativa lo cita, pero no se usa" if claimed else
                   "⚠️ Se usa, pero la narrativa no lo menciona")
        rows.append({"column": c, "claimed": claimed, "actual": actual, "reading": reading})
    examples = [c for c in ("raw.pos_sales.amount", "raw.ecom_orders.status",
                            "raw.erp_products.category", "raw.crm_customers.birth_date")
                if c in g]
    impacts = [impact(g, c, inp.critical_metrics) for c in examples]
    reach = reach_curated(g, sorted(raw_columns))
    reaching = pii_reaching(g, pii)
    maturity = maturity_metrics(edges, g, inp.source_systems, inp.critical_metrics, documented,
                                curated)
    constants = [e for e in edges if e.kind == "constante"]
    pii_set = set(pii)
    critical_cols = {m.column for m in inp.critical_metrics}

    summary: list = [KpisBlock(items=[
        Kpi(label="Tablas curated con linaje", value=f"{fmt_pct(before)} → {fmt_pct(after)}",
            detail="Antes y después de ejecutar esta lección",
            tone="good" if after >= 1 else "warning"),
        Kpi(label="Linaje calculado", value=f"{fmt_num(g.number_of_nodes())} columnas",
            detail=f"{len(edges)} aristas, {len(steps)} transformaciones SQL"),
        Kpi(label=f"Diferencias con la narrativa del {inp.validation.producer}",
            value=str(result.gaps), tone="warning" if result.gaps else "good"),
        Kpi(label="ROI estimado", value=fmt_pct(inp.value.roi),
            detail=f"{fmt_money(sum(inp.value.benefits.values()))} al año de beneficio"),
    ])]
    if not pii_known:
        summary.append(CalloutBlock(
            tone="info", title="Sin la lección 6 no se sabe qué PII llega a curated",
            text="Ejecuta la lección 6 (clasificación de datos personales) y vuelve a "
                 "ejecutar esta para cruzar el linaje con la PII."))

    graph_blocks = [
        GraphBlock(
            title="Linaje entre tablas",
            subtitle="De los sistemas de origen a curated. Elige una tabla para ver de qué "
                     "depende y qué depende de ella.",
            layers=[LAYER_LABELS[k] for k in LAYERS],
            nodes=[GraphNode(id=n, label=n.split(".", 1)[1] if "." in n else n,
                             layer=LAYER_LABELS[_layer(n)]) for n in tg.nodes],
            edges=[GraphEdge(source=s, target=t) for s, t in tg.edges]),
        GraphBlock(
            title=f"De dónde sale {inp.validation.business_element}",
            subtitle="Linaje de columna de la métrica, con el tipo de transformación de cada "
                     "paso. En rojo, datos personales; en azul, la métrica.",
            layers=[LAYER_LABELS[k] for k in LAYERS if k != "sistema"],
            nodes=[GraphNode(id=n, label=n.split(".", 1)[1], layer=LAYER_LABELS[_layer(n)],
                             tone="bad" if n in pii_set else
                             "info" if n in critical_cols else None,
                             detail=terms.get(n))
                   for n in kpi.nodes],
            edges=[GraphEdge(source=s, target=t, kind=k) for s, t, k in kpi_edges],
            focus=inp.validation.business_element),
    ]

    validation_blocks: list = [TableBlock(
        title=f"La narrativa del {inp.validation.producer} frente al linaje real",
        description=inp.validation.narrative,
        columns=[Column(key="column", label="Columna de origen"),
                 Column(key="claimed", label="La cita"), Column(key="actual", label="Se usa"),
                 Column(key="reading", label="Lectura")],
        rows=[{"column": r["column"], "claimed": "Sí" if r["claimed"] else "No",
               "actual": "Sí" if r["actual"] else "No", "reading": r["reading"]}
              for r in rows])]
    for f in result.filters_missing:
        validation_blocks.append(CalloutBlock(
            tone="warning", title="Un filtro que la narrativa no cuenta",
            text=f"La narrativa dice que se filtra por «{f}», pero el SQL no lo hace."))
    if result.filters_found:
        validation_blocks.append(CalloutBlock(
            tone="info", title="Filtros que aplica el SQL",
            text="; ".join(result.filters_found)))

    impact_blocks: list = [TableBlock(
        title="Análisis de impacto: ¿qué se rompe si cambia una columna de origen?",
        columns=[Column(key="col", label="Si cambia"),
                 Column(key="n", label="Columnas afectadas", align="right"),
                 Column(key="tables", label="Tablas"),
                 Column(key="critical", label="Métricas críticas afectadas")],
        rows=[{"col": i.column, "n": str(len(i.affected)), "tables": ", ".join(i.tables),
               "critical": ", ".join(i.critical) or "—"} for i in impacts])]
    dark = [r for r in reach if not r.reaching]
    if dark:
        impact_blocks.append(CalloutBlock(
            tone="info", title="Tablas raw que no llegan a curated",
            text=", ".join(r.table for r in dark) + ": se cargan, pero ninguna columna "
                 "alimenta la capa de negocio."))
    if pii_known and reaching:
        impact_blocks.append(TableBlock(
            title="Datos personales que llegan a curated",
            columns=[Column(key="src", label="Columna con PII"),
                     Column(key="dst", label="Llega a")],
            rows=[{"src": s, "dst": d} for s, d in reaching]))
    elif pii_known:
        impact_blocks.append(CalloutBlock(
            tone="good", title="Ningún dato personal llega a curated",
            text=f"Las {len(pii)} columnas con datos personales que clasificó la lección 6 se "
                 "quedan en raw y staging: la capa de negocio no los expone."))
    impact_blocks.append(TableBlock(
        title="Madurez de los metadatos técnicos",
        columns=[Column(key="m", label="Métrica"),
                 Column(key="v", label="Cumplen", align="right")],
        rows=[{"m": m, "v": f"{ok}/{total} ({fmt_pct(ok / total if total else 0)})"}
              for m, ok, total in maturity]))

    docs = [
        DocumentBlock(title="Linaje de datos", filename="data_lineage.md",
                      markdown=render_template(
                          TEMPLATES, "data_lineage.md.j2", company=COMPANY, layers=layers,
                          table_edges=sorted(tg.edges()), systems=inp.source_systems,
                          raw_by_system=raw_by_system, kpi_edges=kpi_edges, steps=steps,
                          columns_by_table=columns_by_table)),
        DocumentBlock(title="Validación del linaje", filename="lineage_validation.md",
                      markdown=render_template(
                          TEMPLATES, "lineage_validation.md.j2", v=inp.validation, r=result,
                          rows=rows, term=terms.get(inp.validation.business_element))),
        DocumentBlock(title="Metadatos técnicos", filename="technical_metadata.md",
                      markdown=render_template(
                          TEMPLATES, "technical_metadata.md.j2", company=COMPANY,
                          maturity=maturity, impacts=impacts, reach=reach, pii_known=pii_known,
                          pii_reaching=reaching, constants=constants, value=inp.value)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Linaje", blocks=graph_blocks),
        ResultSection(title="Validación de la narrativa", blocks=validation_blocks),
        ResultSection(title="Impacto y madurez", blocks=impact_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=7, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
