"""Data Governance Academy: el libro *Data Governance Handbook* como lecciones interactivas."""

__version__ = "0.1.0"


def main() -> None:
    """Arranca la app en local: uv run academy (sirve el frontend compilado si existe)."""
    import uvicorn

    uvicorn.run("academy.api:app", host="127.0.0.1", port=8000)
