"""Arquitectura de NovaMercado: as-is (almacenes y flujos), to-be, principios y transición."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

MANUAL_WORDS = ("manual", "copia", "email")


class Store(BaseModel):
    id: str
    name: str
    kind: str


class Flow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    from_: str = Field(alias="from")
    to: str
    how: str
    pii: bool

    @property
    def manual(self) -> bool:
        return any(w in self.how.lower() for w in MANUAL_WORDS)


class AsIs(BaseModel):
    stores: list[Store]
    flows: list[Flow]


class Layer(BaseModel):
    name: str
    components: list[str]


class ToBe(BaseModel):
    layers: list[Layer]
    retired: list[str]


class Principle(BaseModel):
    id: str
    text: str


class Architecture(BaseModel):
    as_is: AsIs
    to_be: ToBe
    principles: list[Principle]
    program: dict
    roadmap: list[dict]

    @model_validator(mode="after")
    def _known_stores(self) -> "Architecture":
        stores = {s.id for s in self.as_is.stores}
        bad = [f"{f.from_}->{f.to}" for f in self.as_is.flows if {f.from_, f.to} - stores]
        unknown = set(self.to_be.retired) - stores
        if bad or unknown:
            raise ValueError(f"flujos o retiradas con almacenes desconocidos: "
                             f"{bad + sorted(unknown)}")
        return self
