"""Configuración del PDM de cliente y de los datos de referencia."""

from pydantic import BaseModel, Field, model_validator


class Source(BaseModel):
    table: str
    key: str
    label: str


class Matching(BaseModel):
    name_scorer: str = "token_set_ratio"
    auto_match_score: float = Field(ge=0, le=100)
    review_score: float = Field(ge=0, le=100)
    review_if_postal_differs: bool = True

    @model_validator(mode="after")
    def _order(self) -> "Matching":
        if self.review_score > self.auto_match_score:
            raise ValueError("review_score debe ser menor que auto_match_score")
        return self


class Attribute(BaseModel):
    sources: list[str] = Field(min_length=1)
    validate_: str | None = Field(None, alias="validate")
    default: object = None
    steward: str
    definition: str


class Value(BaseModel):
    campaigns_per_year: int = Field(ge=0)
    cost_per_contact: float = Field(ge=0)
    hours_manual_dedup: float = Field(ge=0)
    automation_share: float = Field(ge=0, le=1)
    cost_per_hour: float = Field(ge=0)


class PdmConfig(BaseModel):
    purpose: str
    customer_definition: str
    sources: dict[str, Source]
    matching: Matching
    attributes: dict[str, Attribute]
    value: Value

    @model_validator(mode="after")
    def _known_sources(self) -> "PdmConfig":
        unknown = {s for a in self.attributes.values() for s in a.sources} - set(self.sources)
        if unknown:
            raise ValueError(f"atributos con fuentes desconocidas: {sorted(unknown)}")
        return self


class ReferenceData(BaseModel):
    steward: str
    source: str
    provinces: dict[str, tuple[str, str]]  # prefijo -> (provincia, comunidad)
    sales_regions: dict[str, list[str]]     # región comercial -> comunidades

    @model_validator(mode="after")
    def _complete(self) -> "ReferenceData":
        communities = {c for _, c in self.provinces.values()}
        mapped = [c for cs in self.sales_regions.values() for c in cs]
        if sorted(mapped) != sorted(communities):
            raise ValueError("cada comunidad debe estar en exactamente una región comercial")
        return self

    @property
    def region_of(self) -> dict[str, str]:
        return {c: region for region, cs in self.sales_regions.items() for c in cs}
