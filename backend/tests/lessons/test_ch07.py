
import pytest

from academy.core.warehouse import connect
from academy.lessons.ch04.evidence import indicators
from academy.lessons.ch07.analysis import (
    CriticalMetric,
    Validation,
    impact,
    reach_curated,
    roots,
    validate,
)
from academy.lessons.ch07.impact import load_graph
from academy.lessons.ch07.lesson import LESSON
from academy.lessons.ch07.lineage import column_graph, parse_sql

SCHEMA = {
    "raw": {"orders": {"id": "VARCHAR", "qty": "VARCHAR", "price": "VARCHAR",
                       "status": "VARCHAR", "sku": "VARCHAR"},
            "products": {"sku": "VARCHAR", "cat": "VARCHAR"}},
    "staging": {"orders": {"id": "VARCHAR", "amount": "DOUBLE", "status": "VARCHAR",
                       "sku": "VARCHAR"},
            "products": {"sku": "VARCHAR", "cat": "VARCHAR"}},
    "curated": {"sales": {"id": "VARCHAR", "amount": "DOUBLE", "status": "VARCHAR",
                      "cat": "VARCHAR", "channel": "VARCHAR"}},
}
SQL = """
CREATE TABLE staging.orders AS
SELECT id, CAST(qty AS INT) * CAST(price AS DOUBLE) AS amount, status, sku FROM raw.orders;
CREATE TABLE staging.products AS SELECT sku, cat FROM raw.products;
CREATE TABLE curated.sales AS
SELECT o.id, o.amount, o.status, p.cat, 'online' AS channel
FROM staging.orders AS o LEFT JOIN staging.products AS p ON o.sku = p.sku;
CREATE TABLE curated.total AS
SELECT sum(amount) AS revenue FROM curated.sales WHERE status <> 'cancelado';
"""


@pytest.fixture(scope="module")
def parsed():
    return parse_sql(SQL, "test.sql", SCHEMA)


def _kinds(edges, target):
    return {(e.source, e.kind) for e in edges if e.target == target}


def test_transformation_kinds(parsed):
    edges, _ = parsed
    assert _kinds(edges, "staging.orders.amount") == {("raw.orders.qty", "calculado"),
                                                  ("raw.orders.price", "calculado")}
    assert ("raw.orders.status", "directo") in _kinds(edges, "staging.orders.status")
    assert ("curated.sales", "constante") in _kinds(edges, "curated.sales.channel")
    assert ("curated.sales.amount", "agregado") in _kinds(edges, "curated.total.revenue")


def test_filters_and_join_keys_are_dependencies(parsed):
    edges, steps = parsed
    assert ("curated.sales.status", "filtro") in _kinds(edges, "curated.total.revenue")
    assert ("staging.orders.sku", "clave de unión") in _kinds(edges, "curated.sales.cat")
    assert steps[-1].filters == ["sales.status <> 'cancelado'"]


def test_roots_and_impact(parsed):
    g = column_graph(parsed[0])
    assert roots(g, "curated.total.revenue") == {"raw.orders.qty", "raw.orders.price",
                                             "raw.orders.status"}
    critical = [CriticalMetric(term="Venta", column="curated.total.revenue")]
    i = impact(g, "raw.orders.status", critical)
    assert "curated.total.revenue" in i.affected and i.critical == ["Venta"]
    # cambiar la categoría no afecta a la venta
    affected = impact(g, "raw.products.cat", []).affected
    assert affected == ["curated.sales.cat", "staging.products.cat"]


def test_validation_finds_gaps(parsed):
    edges, steps = parsed
    v = Validation(report="r", business_element="curated.total.revenue", producer="p", sample="s",
                   narrative="n", claimed_sources=["raw.orders.qty", "raw.products.cat"],
                   claimed_filters=["cancelado", "devuelto"])
    r = validate(column_graph(edges), steps, v)
    assert r.confirmed == ["raw.orders.qty"]
    assert r.claimed_not_used == ["raw.products.cat"]
    assert set(r.undocumented) == {"raw.orders.price", "raw.orders.status"}
    assert (r.filters_found, r.filters_missing) == (["cancelado"], ["devuelto"])


def test_reach_curated(parsed):
    g = column_graph(parsed[0])
    reach = {r.table: r for r in reach_curated(g, ["raw.orders.qty", "raw.orders.id",
                                                    "raw.products.cat", "raw.products.sku"])}
    assert reach["raw.products"].rate == 1.0  # sku llega por la clave de unión


def test_compute_publishes_lineage(compute_lesson, workspace_copy):
    db = workspace_copy.db_path
    with connect(db, read_only=True) as con:
        assert indicators(con)["lineage_coverage"] == 0.0
    sections = compute_lesson(LESSON, workspace=workspace_copy)
    with connect(db, read_only=True) as con:
        assert indicators(con)["lineage_coverage"] == 1.0
    g = load_graph(db)
    assert "raw.pos_sales.amount" in roots(g, "curated.agg_sales_daily_channel.revenue")
    validation = {r["column"]: r for r in sections[2].blocks[0].rows}
    assert validation["raw.erp_products.unit_price"]["actual"] == "No"  # la narrativa se equivoca
    graph = sections[1].blocks[1]
    assert graph.type == "graph" and graph.focus == "curated.agg_sales_daily_channel.revenue"


def test_lessons_6_and_7_unlock_certification(compute_lesson, workspace_copy):
    from academy.lessons.ch06.lesson import LESSON as CH06
    from academy.lessons.ch08.lesson import LESSON as CH08

    compute_lesson(CH06, workspace=workspace_copy)
    compute_lesson(LESSON, workspace=workspace_copy)
    certification = compute_lesson(CH08, workspace=workspace_copy)[3].blocks[0].rows
    assert [r["table"] for r in certification if r["cert"].startswith("✅")] == \
        ["curated.dim_store"]


CTE_SQL = """
CREATE TABLE curated.sales AS
WITH paid AS (SELECT o.id, o.amount, o.sku FROM staging.orders AS o WHERE o.status = 'paid'),
     enriched AS (SELECT p.id, p.amount, pr.cat FROM paid AS p
                  JOIN staging.products AS pr ON pr.sku = p.sku)
SELECT id, sum(amount) AS amount, cat FROM enriched GROUP BY id, cat;
"""


def test_cte_lineage_reaches_source_tables():
    import networkx as nx
    edges, steps = parse_sql(CTE_SQL, "cte.sql", SCHEMA)
    g = column_graph(edges)
    roots = {n for n in nx.ancestors(g, "curated.sales.amount") if g.in_degree(n) == 0}
    assert "staging.orders.amount" in roots and "staging.orders.status" in roots
    assert not any(r.startswith(".") for r in roots)
    assert "curated.sales__paid.amount" in nx.ancestors(g, "curated.sales.amount")
    assert set(steps[0].sources) == {"staging.orders", "staging.products"}
