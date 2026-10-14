from datetime import date

import duckdb
import pytest
from pydantic import ValidationError

from academy.lessons.base import LessonContext
from academy.lessons.ch08.lesson import LESSON
from academy.lessons.ch08.profiling import profile_table
from academy.lessons.ch08.quality import evaluate_detection
from academy.lessons.ch08.rules import Rule, RuleResult, run_rule

AS_OF = date(2026, 10, 12)


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA s")
    c.execute("""CREATE TABLE s.t AS SELECT * FROM (VALUES
        ('a', 'x@y.com', 10.0, 2, 20.0, '28013', DATE '2026-10-11', 'p1'),
        ('b', NULL,      -5.0, 1, -5.0, '2801',  DATE '2026-10-01', 'p9'),
        ('c', 'mal',      3.0, 2,  7.0, '28A13', DATE '2026-10-02', 'p1'),
        ('d', 'x@y.com',  4.0, 1,  4.0, '08001', DATE '2026-10-03', 'p2'))
        AS v(k, email, price, qty, amount, cp, d, sku)""")
    c.execute("CREATE TABLE s.p AS SELECT * FROM (VALUES ('p1'), ('p2')) AS v(sku)")
    yield c
    c.close()


def _rule(**kw) -> Rule:
    base = dict(id="R", table="s.t", column="email", dimension="validez", severity=2,
                threshold=0.9, remediation="corregir_en_origen", description="d")
    return Rule(**(base | kw))


@pytest.mark.parametrize(("kw", "failed"), [
    (dict(type="not_null"), ["b"]),
    (dict(type="regex", pattern=r"^[^@]+@[^@]+\.\w+$"), ["c"]),  # los nulos no cuentan
    (dict(type="unique"), ["a", "d"]),
    (dict(type="positive", column="price"), ["b"]),
    (dict(type="regex", column="cp", pattern=r"^\d{5}$"), ["b", "c"]),
    (dict(type="condition", column="amount", condition="abs(amount - qty * price) < 0.01"),
     ["c"]),
    (dict(type="references", column="sku", ref="s.p.sku"), ["b"]),
    (dict(type="in_set", column="sku", values=["p1", "p2", "p9"]), []),
])
def test_rule_types_find_the_failing_records(con, kw, failed):
    result = run_rule(con, _rule(**kw), "k", AS_OF)
    assert (result.failed_keys, result.total) == (failed, 4)


def test_freshness_is_a_dataset_rule(con):
    fresh = run_rule(con, _rule(type="freshness", column="d", max_age_days=3), "k", AS_OF)
    stale = run_rule(con, _rule(type="freshness", column="d", max_age_days=0), "k", AS_OF)
    assert fresh.meets_threshold and not stale.meets_threshold
    assert "11/10/2026" in fresh.note


def test_rule_requires_its_parameters():
    with pytest.raises(ValidationError):
        _rule(type="regex")


def test_threshold():
    r = RuleResult(_rule(type="not_null", threshold=0.75), 4, ["b"])
    assert r.pass_rate == 0.75 and r.meets_threshold


def test_detection_recall():
    results = [RuleResult(_rule(id="R1", type="not_null"), 10, ["a", "b", "x"])]
    d = evaluate_detection(results, {"defect": ["a", "b", "c"]}, {"defect": "R1"})[0]
    assert (d.true_positives, round(d.recall, 2), d.detected) == (2, 0.67, 3)


def test_profile_patterns_describe_shape(con):
    con.execute("CREATE TABLE s.dates AS SELECT * FROM (VALUES ('2025-01-02'), ('2025-03-04'),"
                " ('03/04/2025')) AS v(f)")
    profile = profile_table(con, "s.dates")[0]
    assert profile.top_patterns[0] == ("9-9-9", 2 / 3)
    assert profile.mixed_formats


def _compute(workspace):
    inputs = {spec.id: spec.model.model_validate(spec.default()) for spec in LESSON.inputs}
    return LESSON.compute(inputs, LessonContext(workspace.db_path, workspace.raw_dir))


def _kpis(sections):
    return {k.label: k.value for k in sections[0].blocks[0].items}


def test_compute_detects_all_seeded_defects(small_workspace):
    sections = _compute(small_workspace)
    assert [s.title for s in sections] == ["Resumen", "Reglas", "Incidencias", "Certificación",
                                           "Detección y valor", "Documentos"]
    assert _kpis(sections)["Defectos sembrados detectados"] == "100 %"
    detection = sections[4].blocks[0].rows
    assert len(detection) == 9 and all(row["recall"] == "100 %" for row in detection)


def test_without_lessons_6_and_7_nothing_is_certified(small_workspace):
    sections = _compute(small_workspace)
    assert _kpis(sections)["Datasets curados certificados"] == "0 de 3"
    assert sections[3].blocks[1].title == "La certificación necesita las lecciones 6 y 7"
    with duckdb.connect(str(small_workspace.db_path), read_only=True) as c:
        assert c.execute("SELECT count(*) FROM meta.dq_results").fetchone()[0] == 17
