import pytest
from fastapi.testclient import TestClient

from academy.api import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(data_dir=tmp_path, frontend_dist=tmp_path / "no-dist"))


def test_lesson_1_is_available(client):
    lessons = client.get("/api/lessons").json()["lessons"]
    assert lessons[0]["status"] == "available" and lessons[5]["status"] == "planned"
    assert client.get("/api/lessons/6/content").status_code == 404


def test_content_has_ideas_and_challenges(client):
    content = client.get("/api/lessons/1/content").json()
    assert content["ideas"] and content["challenges"]


def test_inputs_have_spanish_labels(client):
    inputs = {i["id"]: i for i in client.get("/api/lessons/1/inputs").json()}
    assert set(inputs) == {"program", "data_equity", "business_case", "policy", "scorecard"}
    schema = inputs["business_case"]["json_schema"]
    assert schema["properties"]["horizon_months"]["title"] == "Horizonte (meses)"
    assert schema["$defs"]["TimelineOption"]["title"] == "Opción"
    scorecard = inputs["scorecard"]["json_schema"]["$defs"]["SystemStatus"]["properties"]
    assert scorecard["glossary"]["title"] == "Glosario de negocio"  # Modelo.campo gana
    assert not inputs["business_case"]["custom"]


def test_edit_run_and_reset_input(client):
    bc = next(i for i in client.get("/api/lessons/1/inputs").json()
              if i["id"] == "business_case")
    base = client.post("/api/lessons/1/run").json()
    npv = base["sections"][0]["blocks"][0]["items"][2]["value"]

    data = bc["data"] | {"discount_rate_annual": 0.2}
    saved = client.put("/api/lessons/1/inputs/business_case", json={"data": data}).json()
    assert saved["custom"] and saved["data"]["discount_rate_annual"] == 0.2
    changed = client.post("/api/lessons/1/run").json()
    assert changed["sections"][0]["blocks"][0]["items"][2]["value"] != npv
    assert client.get("/api/lessons/1/result").json()["ran_at"] == changed["ran_at"]

    reset = client.delete("/api/lessons/1/inputs/business_case").json()
    assert not reset["custom"] and reset["data"]["discount_rate_annual"] == 0.08


def test_invalid_input_is_rejected_with_details(client):
    bc = next(i for i in client.get("/api/lessons/1/inputs").json()
              if i["id"] == "business_case")
    data = bc["data"] | {"recommended_option": "no-existe", "horizon_months": 0}
    r = client.put("/api/lessons/1/inputs/business_case", json={"data": data})
    assert r.status_code == 422
    locs = [d["loc"] for d in r.json()["detail"]]
    assert "horizon_months" in locs
    assert client.get("/api/lessons/1/result").json() is None


def _unlabeled(model, labels: dict[str, str]) -> list[str]:
    """Campos de un modelo (y de sus submodelos) sin etiqueta en español."""
    schema = model.model_json_schema()
    out = []
    for obj_name, obj in [(model.__name__, schema), *schema.get("$defs", {}).items()]:
        for name in obj.get("properties", {}):
            if name not in labels and f"{obj_name}.{name}" not in labels:
                out.append(f"{obj_name}.{name}")
    return out


def test_every_form_field_has_a_spanish_label():
    from academy.lessons.registry import LESSONS
    from academy.schema import COMMON_LABELS
    from academy.workspace import LABELS, WorkspaceSettings

    missing = {}
    for lesson in LESSONS.values():
        labels = COMMON_LABELS | lesson.content().labels
        for spec in lesson.inputs:
            fields = _unlabeled(spec.model, labels)
            if fields:
                missing[f"{lesson.number}/{spec.id}"] = fields
    assert not missing, missing
    assert not _unlabeled(WorkspaceSettings, LABELS)
