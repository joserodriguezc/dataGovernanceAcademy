"""Lección 9: arquitectura de datos (as-is, to-be, principios, estándares y revisión SDLC).

Misma lógica que chapters/ch09_arquitectura_datos/run.py del laboratorio. El linter usa los
estándares de esta lección y la política de clasificación de la lección 6.
"""

from collections import Counter, defaultdict
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
from academy.core.reporting import fmt_pct, render_template
from academy.core.warehouse import connect, sql_files
from academy.lessons.base import InputSpec, LessonContext, LessonDef
from academy.lessons.ch06.lesson import CLASSIFICATION

from .architecture import Architecture
from .lint import StandardsInput, lint_files
from .review import make_linter

LESSON_DIR = Path(__file__).parent
INPUTS = LESSON_DIR / "inputs"
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
KIND_LAYERS = {"aplicación": "Aplicaciones", "almacén departamental": "Almacenes paralelos",
               "hoja de cálculo": "Almacenes paralelos", "almacén analítico": "Warehouse",
               "consumo": "Consumo"}

INPUT_SPECS = [
    InputSpec("architecture", "Arquitectura",
              "Almacenes y flujos actuales, arquitectura objetivo, principios, programa y "
              "hoja de ruta.", Architecture, INPUTS / "architecture.yaml"),
    InputSpec("standards", "Estándares",
              "Estándares de nomenclatura, tipos, claves y datos personales que el linter "
              "comprueba en el warehouse y en cada cambio SQL.",
              StandardsInput, INPUTS / "standards.yaml"),
]


def _scalar(con, sql: str):
    try:
        return con.execute(sql).fetchone()[0]
    except Exception:  # la tabla meta aún no existe: la lección no se ha ejecutado
        return None


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    arch: Architecture = inputs["architecture"]
    linter = make_linter(inputs["standards"], ctx.input_of(6, CLASSIFICATION))
    stores = {s.id for s in arch.as_is.stores}
    proposals = sorted((INPUTS / "proposals").glob("*.sql"))

    with connect(ctx.db_path, read_only=True) as con:
        findings = linter.lint_warehouse(con)
        reviews = lint_files(linter, con, [*sql_files(), *proposals])
        documented = _scalar(con, "SELECT avg(CASE WHEN comment <> '' THEN 1 ELSE 0 END) "
                                  "FROM duckdb_tables() WHERE schema_name = 'curated'")
        certified = _scalar(con, "SELECT count(*) FILTER (WHERE certified) || ' de ' || "
                                 "count(*) FROM meta.catalog_tables WHERE layer = 'curated'")
        dq_issues = _scalar(con, "SELECT count(*) FROM meta.dq_issues WHERE status = 'abierta'")

    by_standard: dict[str, list] = defaultdict(list)
    for f in findings:
        by_standard[f.standard].append(f)
    counts = Counter(f.standard for f in findings)
    retired = set(arch.to_be.retired)
    kept = [f for f in arch.as_is.flows if not {f.from_, f.to} & retired]
    sql_reviews = [(Path(k).name, v) for k, v in reviews.items()]
    compliant = sum(1 for s in linter.std.standards if not counts.get(s.id))
    pii_tables = sorted(set().union(*linter.pii_places.values()))
    manual = sum(f.manual for f in arch.as_is.flows)
    measures = [
        ("Estándares que cumple el warehouse", f"{compliant} de {len(linter.std.standards)}"),
        ("Seguridad y cumplimiento: tablas con datos personales fuera de raw",
         f"{len(pii_tables)} ({', '.join(pii_tables)})" if pii_tables else "0"),
        ("Simplificación: almacenes de datos", f"{len(stores)} hoy → {len(stores - retired)}"),
        ("Simplificación: flujos punto a punto", f"{len(arch.as_is.flows)} hoy → {len(kept)}"),
        ("Accesibilidad: puntos de provisión autorizados (curated certificados, lección 8)",
         certified or "sin medir (ejecuta la lección 8)"),
        ("Metadatos: tablas curated documentadas (lección 6)",
         fmt_pct(documented) if documented is not None else "sin medir"),
        ("Calidad: incidencias abiertas (lección 8)",
         str(dq_issues) if dq_issues is not None else "sin medir (ejecuta la lección 8)"),
        ("Programa: principios definidos y to-be en borrador",
         f"{len(arch.principles)} principios · to-be de {len(arch.to_be.layers)} capas"),
    ]

    summary: list = [KpisBlock(items=[
        Kpi(label="Estándares que cumple el warehouse",
            value=f"{compliant} de {len(linter.std.standards)}",
            tone="good" if compliant == len(linter.std.standards) else "warning"),
        Kpi(label="Almacenes de datos", value=f"{len(stores)} → {len(stores - retired)}",
            detail="Hoy y en la arquitectura objetivo"),
        Kpi(label="Flujos", value=f"{len(arch.as_is.flows)} → {len(kept)}",
            detail=f"{manual} manuales hoy"),
        Kpi(label="Cambios SQL que pasan la revisión",
            value=f"{sum(not fs for _, fs in sql_reviews)} de {len(sql_reviews)}"),
    ])]

    names = {s.id: s.name for s in arch.as_is.stores}
    layers = list(dict.fromkeys(KIND_LAYERS.get(s.kind, s.kind) for s in arch.as_is.stores))
    as_is_blocks = [GraphBlock(
        title="Arquitectura actual: almacenes y flujos",
        subtitle="Discontinuo: flujo manual · rojo: transporta datos personales · nodo rojo: "
                 "se retira en la arquitectura objetivo. Elige un almacén para ver sus flujos.",
        layers=layers,
        nodes=[GraphNode(id=s.id, label=s.name, layer=KIND_LAYERS.get(s.kind, s.kind),
                         tone="bad" if s.id in retired else None, detail=s.kind)
               for s in arch.as_is.stores],
        edges=[GraphEdge(source=f.from_, target=f.to, kind=f.how, dashed=f.manual,
                         tone="bad" if f.pii else None) for f in arch.as_is.flows])]
    as_is_blocks.append(TableBlock(
        title="Arquitectura objetivo por capas",
        columns=[Column(key="layer", label="Capa"), Column(key="components", label="Componentes")],
        rows=[{"layer": la.name, "components": ", ".join(la.components)}
              for la in arch.to_be.layers]))
    as_is_blocks.append(CalloutBlock(
        tone="info", title="Lo que desaparece",
        text=", ".join(names[r] for r in sorted(retired)) + f": de {len(arch.as_is.flows)} "
             f"flujos se pasa a {len(kept)}, y los manuales bajan de {manual} a "
             f"{sum(f.manual for f in kept)}."))

    standards_blocks: list = [TableBlock(
        title="Estándares de arquitectura en el warehouse",
        columns=[Column(key="id", label="Estándar"), Column(key="area", label="Área"),
                 Column(key="text", label="Qué exige"),
                 Column(key="n", label="Incumplimientos", align="right"),
                 Column(key="examples", label="Ejemplos")],
        rows=[{"id": s.id, "area": s.area, "text": s.text, "n": str(counts.get(s.id, 0)),
               "examples": "; ".join(f.target for f in by_standard.get(s.id, [])[:3])
                           or "✓"} for s in linter.std.standards])]
    standards_blocks.append(TableBlock(
        title="Revisión de los cambios SQL (puerta del SDLC)",
        description="Cada transformación del warehouse, y la propuesta nueva, pasa por el "
                    "linter antes de aceptarse.",
        columns=[Column(key="file", label="Fichero"), Column(key="ok", label="Resultado"),
                 Column(key="issues", label="Hallazgos")],
        rows=[{"file": f, "ok": "✅ Pasa" if not fs else f"❌ {len(fs)} hallazgos",
               "issues": "; ".join(f"{x.standard}: {x.message}" for x in fs) or "—"}
              for f, fs in sql_reviews]))

    measures_blocks = [TableBlock(
        title="Medidas de éxito de la arquitectura",
        description="Las de metadatos, certificación y calidad se miden con lo que han dejado "
                    "las lecciones 6, 7 y 8 en el warehouse.",
        columns=[Column(key="m", label="Medida"), Column(key="v", label="Valor")],
        rows=[{"m": m, "v": v} for m, v in measures])]

    docs = [DocumentBlock(title="Arquitectura de datos", filename="data_architecture.md",
                          markdown=render_template(
                              TEMPLATES, "data_architecture.md.j2", company=COMPANY,
                              as_is=arch.as_is, to_be=arch.to_be, retired=sorted(retired),
                              retired_names=[s.name for s in arch.as_is.stores
                                             if s.id in retired],
                              pii_flows=sum(f.pii for f in arch.as_is.flows),
                              manual_flows=manual, to_be_stores=len(stores - retired),
                              to_be_flows=len(kept), to_be_manual=sum(f.manual for f in kept),
                              to_be_pii=sum(f.pii for f in kept), principles=arch.principles,
                              standards=linter.std.standards, counts=counts,
                              by_standard=by_standard, sql_reviews=sql_reviews,
                              program=arch.program, roadmap=arch.roadmap, measures=measures))]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="As-is y to-be", blocks=as_is_blocks),
        ResultSection(title="Estándares y revisión SQL", blocks=standards_blocks),
        ResultSection(title="Medidas de éxito", blocks=measures_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=9, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
