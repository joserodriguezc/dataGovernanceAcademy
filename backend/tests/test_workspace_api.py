import pytest
from fastapi.testclient import TestClient

from academy.api import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(data_dir=tmp_path, frontend_dist=tmp_path / "no-dist"))


def test_lesson_8_needs_the_warehouse(client):
    lesson = client.get("/api/lessons/8").json()["lesson"]
    assert lesson["status"] == "available" and lesson["requires_warehouse"]
    r = client.post("/api/lessons/8/run")
    assert r.status_code == 409 and "Datos de NovaMercado" in r.json()["detail"]


def test_workspace_settings_validate_and_track_changes(client):
    ws = client.get("/api/workspace").json()
    assert not ws["status"]["built"]
    assert ws["json_schema"]["properties"]["persons"]["title"].startswith("Clientes reales")
    bad = ws["status"]["settings"] | {"persons": 5}
    r = client.put("/api/workspace/settings", json={"data": bad})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == "persons"


def test_build_run_and_reset(client):
    settings = client.get("/api/workspace").json()["status"]["settings"]
    small = settings | {"persons": 300}
    client.put("/api/workspace/settings", json={"data": small})
    status = client.post("/api/workspace/build").json()["status"]
    assert status["built"] and not status["pending_changes"]
    assert status["seeded_defects"]["crm_duplicates"] > 0
    assert any(t["table"] == "curated.fct_sales" for t in status["tables"])

    assert client.post("/api/lessons/8/run").status_code == 200

    more = small | {"defects": small["defects"] | {"crm_null_email": 0.2}}
    status = client.put("/api/workspace/settings", json={"data": more}).json()["status"]
    assert status["pending_changes"]

    status = client.delete("/api/workspace").json()["status"]
    assert not status["built"] and status["settings"]["defects"]["crm_null_email"] == 0.2
