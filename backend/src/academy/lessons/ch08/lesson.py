"""Lección 8: perfilado, reglas de calidad, incidencias, certificación y valor.

Misma lógica que chapters/ch08_calidad_datos/run.py del laboratorio, sobre el warehouse que
el alumno ha construido en «Datos de NovaMercado». Escribe meta.dq_results y meta.dq_issues,
y marca los datasets certificados en el catálogo si la lección 6 lo ha creado.
"""

from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
    BarItem,
    BarListBlock,
    CalloutBlock,
    Column,
    DocumentBlock,
    Kpi,
    KpisBlock,
    ResultSection,
    TableBlock,
)
from academy.core.company import DOMAIN_NAMES
from academy.core.reporting import fmt_money, fmt_num, fmt_pct, render_template
from academy.core.synthetic.io import read_truth
from academy.core.warehouse import connect
from academy.lessons.base import InputSpec, LessonContext, LessonDef
from academy.lessons.ch03.lesson import TEAM

from .profiling import profile_table
from .publish import write_quality
from .quality import (
    SEVERITY_LABELS,
    certify,
    evaluate_detection,
    inherited_postal_defects,
    issue_log,
    marketable_contacts,
)
from .rules import DQInput, run_rules, scorecard

LESSON_DIR = Path(__file__).parent
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
REMEDIATION_LABELS = {"estandarizar": "Estandarizar el formato", "excluir": "Excluir del cálculo",
                      "corregir_en_origen": "Corregir en el sistema de origen",
                      "enriquecer": "Enriquecer con un tercero", "aceptar": "Aceptar el riesgo"}
DEFECT_LABELS = {
    "crm_null_email": "CRM: email vacío", "crm_duplicates": "CRM: altas duplicadas",
    "ecom_bad_date_format": "E-commerce: fecha en dd/mm/aaaa",
    "ecom_invalid_postal": "E-commerce: código postal inválido",
    "order_invalid_postal": "Pedidos: código postal de envío inválido",
    "pos_missing_phone": "Tiendas: tarjeta sin teléfono",
    "pos_negative_price": "Tiendas: precio negativo",
    "product_missing_category": "Productos: sin categoría",
    "supplier_missing_contact": "Proveedores: sin contacto",
}

INPUT_SPECS = [
    InputSpec("dq_rules", "Reglas de calidad",
              "Tablas medidas, las 17 reglas con su umbral y severidad, disposiciones, "
              "criterio de certificación y valor de negocio.",
              DQInput, LESSON_DIR / "inputs" / "dq_rules.yaml"),
]


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    inp: DQInput = inputs["dq_rules"]
    roles = ctx.input_of(3, TEAM).functional_roles  # stewards de la lección 3
    stewards = {r.domain: r.business_stewards for r in roles}
    _, seeded = read_truth(ctx.raw_dir)

    with connect(ctx.db_path) as con:
        profiles = {t: profile_table(con, t) for t in inp.tables}
        results = run_rules(con, inp)
        issues = issue_log(results, inp, stewards)
        curated = sorted(t for t in inp.tables if t.startswith("curated."))
        certs = certify(con, curated, results, inp)
        write_quality(con, results, issues, certs, inp.as_of)
        email_rule = next((r for r in inp.rules if r.id == "DQ-02"), None)
        crm_total, marketable = (marketable_contacts(con, email_rule.pattern) if email_rule
                                 else (0, 0))
        consented = con.execute("SELECT count(*) FILTER (WHERE consent_marketing) "
                                "FROM staging.stg_crm_customers").fetchone()[0]
        dq06 = next((r for r in results if r.rule.id == "DQ-06"), None)
        inherited_n = inherited_postal_defects(
            con, dq06.failed_keys, seeded.get("order_invalid_postal", []),
            seeded.get("ecom_invalid_postal", [])) if dq06 else 0

    detection = evaluate_detection(results, seeded, inp.seeded_defects)
    fixable = max(consented - marketable, 0)
    failed_records = sum(r.failed for r in results if r.rule.type != "freshness")
    manual_hours = failed_records * inp.value.hours_manual_fix_per_issue
    by_dim = scorecard(results, lambda r: r.rule.dimension)
    by_dom = scorecard(results, lambda r: inp.tables[r.rule.table].domain)
    meets = sum(r.meets_threshold for r in results)
    open_issues = [i for i in issues if i.status == "abierta"]
    certified = [c for c in certs if c.certified]
    recall = (sum(d.true_positives for d in detection) / sum(d.seeded for d in detection)
              if detection and sum(d.seeded for d in detection) else 1.0)

    # Resumen
    summary = [KpisBlock(items=[
        Kpi(label="Reglas que cumplen su umbral", value=f"{meets} de {len(results)}",
            tone="good" if meets == len(results) else "warning"),
        Kpi(label="Incidencias abiertas", value=fmt_num(len(open_issues)),
            detail=f"{len(issues) - len(open_issues)} aceptada(s) con disposición firmada",
            tone="bad" if any(i.severity == 1 for i in open_issues) else None),
        Kpi(label="Datasets curados certificados", value=f"{len(certified)} de {len(certs)}",
            tone="good" if certified else "bad"),
        Kpi(label="Defectos sembrados detectados", value=fmt_pct(recall),
            detail="Frente al solucionario de los datos sintéticos",
            tone="good" if recall == 1 else "warning"),
    ])]

    # Reglas
    measurable = sorted((r for r in results if r.rule.type != "freshness"),
                        key=lambda r: r.pass_rate)
    lowest = min((r.pass_rate for r in measurable), default=0.9)
    rules_blocks = [
        BarListBlock(
            title="Registros que cumplen cada regla frente a su umbral",
            subtitle="Ordenadas de peor a mejor. La marca vertical es el umbral. Las reglas de "
                     "actualidad miden el conjunto y van en la tabla.",
            min_value=max(0.0, min(0.75, lowest - 0.02)), max_value=1.0,
            items=[BarItem(label=f"{r.rule.id} · {r.rule.dimension}", value=r.pass_rate,
                           display=fmt_pct(r.pass_rate, 2), target=r.rule.threshold,
                           ok=r.meets_threshold,
                           detail=f"{r.rule.description} ({r.rule.table}.{r.rule.column})")
                   for r in measurable]),
        TableBlock(
            title="Resultado de cada regla",
            columns=[Column(key="id", label="Regla"), Column(key="desc", label="Descripción"),
                     Column(key="where", label="Tabla.columna"),
                     Column(key="dim", label="Dimensión"),
                     Column(key="sev", label="Sev.", align="right"),
                     Column(key="failed", label="Fallan", align="right"),
                     Column(key="rate", label="Válidos", align="right"),
                     Column(key="threshold", label="Umbral", align="right"),
                     Column(key="ok", label="Cumple")],
            rows=[{"id": r.rule.id, "desc": r.rule.description + (f" ({r.note})" if r.note else ""),
                   "where": f"{r.rule.table}.{r.rule.column}", "dim": r.rule.dimension,
                   "sev": str(r.rule.severity), "failed": fmt_num(r.failed),
                   "rate": fmt_pct(r.pass_rate, 2), "threshold": fmt_pct(r.rule.threshold, 1),
                   "ok": "✅ Sí" if r.meets_threshold else "❌ No"} for r in results]),
        TableBlock(
            title="Por dimensión",
            columns=[Column(key="g", label="Dimensión"),
                     Column(key="rules", label="Reglas", align="right"),
                     Column(key="meets", label="Cumplen", align="right"),
                     Column(key="rate", label="Registros válidos (media)", align="right")],
            rows=[{"g": str(g).capitalize(), "rules": fmt_num(row.rules),
                   "meets": fmt_num(row.meets), "rate": fmt_pct(row.pass_rate, 1)}
                  for g, row in by_dim.iterrows()]),
        TableBlock(
            title="Por dominio",
            columns=[Column(key="g", label="Dominio"),
                     Column(key="rules", label="Reglas", align="right"),
                     Column(key="meets", label="Cumplen", align="right"),
                     Column(key="rate", label="Registros válidos (media)", align="right")],
            rows=[{"g": DOMAIN_NAMES.get(g, g), "rules": fmt_num(row.rules),
                   "meets": fmt_num(row.meets), "rate": fmt_pct(row.pass_rate, 1)}
                  for g, row in by_dom.iterrows()]),
    ]

    # Incidencias
    issue_blocks = [TableBlock(
        title="Registro de incidencias",
        description="Una incidencia por regla que no cumple su umbral, ordenadas por severidad.",
        columns=[Column(key="id", label="Incidencia"), Column(key="rule", label="Regla"),
                 Column(key="sev", label="Severidad"),
                 Column(key="records", label="Registros", align="right"),
                 Column(key="remediation", label="Remediación"),
                 Column(key="steward", label="Steward"), Column(key="status", label="Estado")],
        rows=[{"id": i.id, "rule": f"{i.result.rule.id} · {i.result.rule.description}",
               "sev": SEVERITY_LABELS[i.severity], "records": fmt_num(i.result.failed),
               "remediation": REMEDIATION_LABELS[i.result.rule.remediation],
               "steward": i.steward,
               "status": i.status + (f" ({i.disposition})" if i.disposition else "")}
              for i in issues])]
    if inherited_n:
        issue_blocks.append(CalloutBlock(
            tone="info", title="Un defecto que se hereda",
            text=f"{inherited_n} pedidos con código postal inválido son de clientes cuyo código "
                 "postal ya era inválido en el e-commerce. Se corrige en el maestro de cliente, "
                 "no en cada pedido."))

    # Certificación
    cert_blocks: list = [TableBlock(
        title="Certificación de los datasets curados",
        description="Se certifica si el dataset y sus fuentes cumplen las reglas de severidad "
                    f"≤ {inp.certification.max_severity_blocking}, y además tiene linaje, "
                    "documentación y steward.",
        columns=[Column(key="table", label="Dataset"), Column(key="cert", label="Estado"),
                 Column(key="reasons", label="Motivos")],
        rows=[{"table": c.table, "cert": "✅ Certificado" if c.certified else "❌ No certificado",
               "reasons": "; ".join(c.reasons) or "—"} for c in certs])]
    missing = {reason for c in certs for reason in c.reasons
               if "capítulo 6" in reason or "capítulo 7" in reason or "steward" in reason}
    if missing:
        cert_blocks.append(CalloutBlock(
            tone="info", title="La certificación necesita las lecciones 6 y 7",
            text="Un dato solo se certifica si está documentado, tiene steward (lección 6) y "
                 "se conoce su linaje (lección 7). Cuando las ejecutes sobre este warehouse, "
                 "vuelve a ejecutar esta lección."))

    # Detección y valor
    detection_blocks = [
        TableBlock(
            title="Detección frente al solucionario",
            description="Los datos sintéticos guardan qué registros llevan cada defecto. Así "
                        "se puede medir si las reglas encuentran todos.",
            columns=[Column(key="defect", label="Defecto sembrado"),
                     Column(key="rule", label="Regla"),
                     Column(key="seeded", label="Sembrados", align="right"),
                     Column(key="detected", label="Detectados", align="right"),
                     Column(key="recall", label="Encontrados", align="right")],
            rows=[{"defect": DEFECT_LABELS.get(d.defect, d.defect), "rule": d.rule_id,
                   "seeded": fmt_num(d.seeded), "detected": fmt_num(d.detected),
                   "recall": fmt_pct(d.recall)} for d in detection]),
        KpisBlock(items=[
            Kpi(label="Contactos aptos para marketing", value=f"{fmt_num(marketable)} de "
                f"{fmt_num(crm_total)}", detail="Email válido y consentimiento"),
            Kpi(label="Recuperables corrigiendo el email", value=fmt_num(fixable),
                detail=f"{fmt_money(fixable * inp.value.contacts_marketing_value)} al año",
                tone="good"),
            Kpi(label="Coste de corregir a mano lo que falla", value=fmt_money(
                manual_hours * inp.value.cost_per_hour),
                detail=f"{fmt_num(manual_hours)} horas"),
        ]),
    ]

    docs = [
        DocumentBlock(title="Perfil de los datos", filename="data_profile.md",
                      markdown=render_template(
                          TEMPLATES, "data_profile.md.j2", company=COMPANY,
                          tables=list(profiles.items()),
                          mixed=[p for ps in profiles.values() for p in ps if p.mixed_formats])),
        DocumentBlock(title="Scorecard de calidad", filename="dq_scorecard.md",
                      markdown=render_template(
                          TEMPLATES, "dq_scorecard.md.j2", company=COMPANY, as_of=inp.as_of,
                          results=results, meets=meets, issues=issues,
                          open_issues=len(open_issues), certs=certs, certified=certified,
                          chart_name=None, by_dimension=list(by_dim.iterrows()),
                          by_domain=list(by_dom.iterrows()), domain_names=DOMAIN_NAMES,
                          severity_labels=SEVERITY_LABELS, remediation_labels=REMEDIATION_LABELS,
                          dispositions=[i for i in issues if i.disposition],
                          blocking=inp.certification.max_severity_blocking,
                          detection=detection,
                          inherited={"order_invalid_postal": f"{inherited_n} pedidos son de "
                                     "clientes cuyo código postal ya era inválido en el "
                                     "e-commerce."},
                          marketable=marketable, crm_total=crm_total, fixable=fixable,
                          fixable_value=fixable * inp.value.contacts_marketing_value,
                          manual_hours=manual_hours,
                          manual_cost=manual_hours * inp.value.cost_per_hour)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Reglas", blocks=rules_blocks),
        ResultSection(title="Incidencias", blocks=issue_blocks),
        ResultSection(title="Certificación", blocks=cert_blocks),
        ResultSection(title="Detección y valor", blocks=detection_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=8, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
