"""JSON Schema de las entradas, con etiquetas en español para generar los formularios.

Pydantic titula cada campo a partir de su nombre en inglés ("Hourly Rate Usd"). Las
etiquetas de la lección los sustituyen: la clave puede ser `campo` o `Modelo.campo`, y la
segunda gana cuando un mismo nombre significa cosas distintas en dos modelos.
"""

from typing import Any

from pydantic import BaseModel


def _label_object(schema: dict[str, Any], model_name: str, labels: dict[str, str]) -> None:
    if model_name in labels:
        schema["title"] = labels[model_name]
    for name, prop in schema.get("properties", {}).items():
        label = labels.get(f"{model_name}.{name}") or labels.get(name)
        if label:
            prop["title"] = label


def form_schema(model: type[BaseModel], labels: dict[str, str]) -> dict[str, Any]:
    schema = model.model_json_schema()
    _label_object(schema, model.__name__, labels)
    schema.pop("title", None)  # la pestaña ya nombra la entrada
    for name, definition in schema.get("$defs", {}).items():
        _label_object(definition, name, labels)
    return schema
