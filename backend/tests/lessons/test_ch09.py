import duckdb
import pytest

from academy.lessons.ch09.lesson import INPUTS, LESSON
from academy.lessons.ch09.lint import Linter, lint_files
from academy.lessons.ch09.review import make_linter

SCHEMA = {
    "raw": {"crm_customers": {"customer_id": "VARCHAR", "email": "VARCHAR", "phone": "VARCHAR"}},
    "staging": {"stg_pos_sales": {"line_id": "VARCHAR", "amount": "DOUBLE"},
                "stg_crm_customers": {"customer_id": "VARCHAR", "email": "VARCHAR"}},
}


@pytest.fixture(scope="module")
def linter() -> Linter:
    return make_linter()


def _standards(findings) -> list[str]:
    return sorted({f.standard for f in findings})


def test_good_sql_passes(linter):
    sql = ("CREATE TABLE curated.fct_x AS SELECT line_id, amount AS net_amount "
           "FROM staging.stg_pos_sales")
    assert linter.lint_sql(sql, SCHEMA) == []


@pytest.mark.parametrize(("sql", "expected"), [
    ("CREATE TABLE curated.report AS SELECT line_id FROM staging.stg_pos_sales", ["ARQ-01"]),
    ("CREATE TABLE curated.fct_x AS SELECT * FROM staging.stg_pos_sales", ["ARQ-04"]),
    ("CREATE TABLE curated.fct_x AS SELECT customer_id FROM raw.crm_customers", ["ARQ-03"]),
    ("CREATE TABLE staging.stg_x AS SELECT line_id FROM staging.stg_pos_sales", ["ARQ-03"]),
    ("CREATE TABLE curated.fct_x AS SELECT line_id AS lineId FROM staging.stg_pos_sales",
     ["ARQ-02"]),
    ("CREATE TABLE curated.dim_x AS SELECT customer_id, email FROM staging.stg_crm_customers",
     ["ARQ-09"]),
])
def test_each_standard_is_detected(linter, sql, expected):
    assert _standards(linter.lint_sql(sql, SCHEMA)) == expected


def test_select_star_with_pii_is_caught_after_expansion(linter):
    sql = "CREATE TABLE curated.dim_x AS SELECT * FROM staging.stg_crm_customers"
    assert "ARQ-09" in _standards(linter.lint_sql(sql, SCHEMA))


def test_warehouse_lint_types_keys_and_pii():
    con = duckdb.connect()
    for s in ("raw", "staging", "curated"):
        con.execute(f"CREATE SCHEMA {s}")
    con.execute("CREATE TABLE staging.stg_pos_sales AS SELECT * FROM (VALUES "
                "('a', 1.5::DOUBLE, '2025-01-01'), ('a', 2.0::DOUBLE, NULL)) "
                "AS v(line_id, amount, sale_date)")
    con.execute("CREATE TABLE staging.stg_crm_customers AS SELECT 'c' AS customer_id, "
                "'x@y.es' AS email")
    con.execute("CREATE TABLE staging.stg_ecom_customers AS SELECT 'e' AS ecom_user_id, "
                "'x@y.es' AS email")
    con.execute("CREATE TABLE curated.fct_y AS SELECT 'a' AS id")  # sin documentar
    linter = make_linter()
    linter.std.keys = {"staging.stg_pos_sales": "line_id"}
    found = {(f.standard, f.target) for f in linter.lint_warehouse(con)}
    assert ("ARQ-06", "staging.stg_pos_sales.amount") in found
    assert ("ARQ-05", "staging.stg_pos_sales.sale_date") in found
    assert ("ARQ-07", "staging.stg_pos_sales") in found
    assert ("ARQ-08", "curated.fct_y") in found
    assert ("ARQ-10", "PII directa - email") in found
    assert linter.pii_places["PII directa - email"] == {"staging.stg_crm_customers",
                                                        "staging.stg_ecom_customers"}


def test_review_rejects_the_proposal(small_workspace):
    proposal = INPUTS / "proposals" / "20_curated_customer_report.sql"
    with duckdb.connect(str(small_workspace.db_path), read_only=True) as con:
        findings = lint_files(make_linter(), con, [proposal])[str(proposal)]
    found = {f.standard for f in findings}
    for sid in ("ARQ-01", "ARQ-02", "ARQ-03", "ARQ-04", "ARQ-09"):
        assert sid in found


def test_compute_generates_report(compute_lesson):
    sections = compute_lesson(LESSON)
    text = sections[-1].blocks[0].markdown
    assert "| Flujos punto a punto | 17 | 8 |" in text
    assert "ARQ-06" in text and "sin medir" in text  # sin las lecciones 6-8
    assert sections[1].blocks[0].type == "graph"
