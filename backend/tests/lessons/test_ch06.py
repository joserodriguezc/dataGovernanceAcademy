
import pytest
from pydantic import ValidationError

from academy.core.config import load_yaml
from academy.core.warehouse import connect
from academy.lessons.ch04.evidence import indicators
from academy.lessons.ch06.catalog import (
    CatalogColumn,
    CatalogTable,
    TableAnnotation,
    ValueAssumptions,
)
from academy.lessons.ch06.classify import ClassificationPolicy, classify, match_ratio
from academy.lessons.ch06.glossary import Glossary, Stewards, Term, broken_mappings
from academy.lessons.ch06.lesson import INPUTS, LESSON
from academy.lessons.ch06.marketplace import search
from academy.lessons.ch06.standards import Standard, evaluate

POLICY = ClassificationPolicy.model_validate(load_yaml(INPUTS / "classification.yaml"))


@pytest.mark.parametrize(("name", "values", "level", "method"), [
    ("email", ["ana@correo.es"], "restricted", "nombre y contenido"),
    ("mail_cliente", ["ana@correo.es", "luis@x.com"], "restricted", "contenido"),
    ("phone", ["+34 612 345 678", "612-345-678", "612345678"], "restricted",
     "nombre y contenido"),
    ("first_name", ["Ana"], "restricted", "nombre"),
    ("birth_date", ["1980-01-01"], "restricted", "nombre"),
    ("sale_date", ["2025-03-14", "2026-01-02"], "internal", "por defecto"),  # no es un teléfono
    ("quantity", ["1", "2"], "internal", "por defecto"),
    ("tax_id", ["A12345678"], "confidential", "nombre y contenido"),
])
def test_classification_rules(name, values, level, method):
    result = classify(f"x.t.{name}", name, values, POLICY)
    assert (result.level, result.method) == (level, method)


def test_steward_override_wins():
    result = classify("staging.stg_suppliers.contact_email", "contact_email", ["a@b.com"], POLICY)
    assert (result.level, result.method) == ("confidential", "steward")


def test_match_ratio():
    assert match_ratio(["12345", "1234", "54321", "abcde"], r"\d{5}") == 0.5
    assert match_ratio([], r"\d") == 0.0


# --- Glosario ----------------------------------------------------------------------------

def _term(**kw) -> Term:
    base = dict(term="T", domain="sales", definition="d", status="approved",
                columns=["curated.fct_sales.channel"])
    return Term(**(base | kw))


def test_glossary_rejects_duplicates_and_unqualified_columns():
    with pytest.raises(ValidationError):
        Glossary(terms=[_term(term="Venta"), _term(term="venta")])
    with pytest.raises(ValidationError):
        _term(columns=["fct_sales.channel"])


def test_broken_mappings():
    g = Glossary(terms=[_term(columns=["curated.fct_sales.channel", "curated.fct_sales.nope"])])
    assert broken_mappings(g, {"curated.fct_sales.channel"}) == [("T", "curated.fct_sales.nope")]


# --- Estándares --------------------------------------------------------------------------

def test_standards_compliance_by_domain():
    ok = CatalogTable("staging.a", "staging", 1, [CatalogColumn("staging.a", "c", "INT", 0.0,
                                                                term="T", level="internal")],
                      TableAnnotation(description="d", domain="sales", format="f"), ["b"], ["t"])
    bad = CatalogTable("curated.b", "curated", 1, [CatalogColumn("curated.b", "c", "INT", 0.0)],
                       TableAnnotation(description="d", domain="supplier", format="f"))
    raw = CatalogTable("raw.x", "raw", 1)  # fuera del estándar
    standards = [Standard(id="S1", applies_to="table", check="has_business_steward", text=""),
                 Standard(id="S2", applies_to="column", check="has_business_term", text=""),
                 Standard(id="S3", applies_to="term", check="has_steward", text="")]
    g = Glossary(terms=[_term(), _term(term="P", domain="supplier")])
    result = {c.standard.id: c for c in evaluate(
        standards, [ok, bad, raw], g, {"sales": Stewards(["b"], ["t"])})}
    assert (result["S1"].passed, result["S1"].total) == (1, 2)
    assert result["S1"].by_domain == {"sales": (1, 1), "supplier": (0, 1)}
    assert result["S2"].failures == ["curated.b.c"]
    assert result["S3"].failures == ["P"]


def test_value_assumptions():
    v = ValueAssumptions(data_users=10, annual_cost_per_user=100000, search_time_share=0.5,
                         expected_reduction=0.5, reports_per_year=100, hours_saved_per_report=20,
                         hourly_rate=50)
    assert v.catalog_value == 250000 and v.glossary_value == 100000


# --- Extremo a extremo -------------------------------------------------------------------

def test_compute_documents_the_warehouse(compute_lesson, workspace_copy):
    db = workspace_copy.db_path
    with connect(db, read_only=True) as con:
        assert indicators(con)["documented_tables"] == 0.0
    sections = compute_lesson(LESSON, workspace=workspace_copy)
    assert sections[0].blocks[0].items[0].value == "0 % → 100 %"
    with connect(db, read_only=True) as con:
        assert indicators(con)["documented_tables"] == 1.0
        comment = con.execute("SELECT comment FROM duckdb_columns() WHERE schema_name = "
                              "'curated' AND table_name = 'agg_sales_daily_channel' AND "
                              "column_name = 'revenue'").fetchone()[0]
        found = search(con, "cifra de ventas")
    assert comment.startswith("Venta neta:")
    assert [t[0] for t in found["terms"]] == ["Venta neta"]  # se encuentra por sinónimo
