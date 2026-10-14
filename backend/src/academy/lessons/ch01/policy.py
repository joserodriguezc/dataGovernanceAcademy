"""Política de gobierno de datos según el esquema de 10 secciones del capítulo."""

from datetime import date

from pydantic import BaseModel, Field

POLICY_SECTIONS = (
    "Propósito y alcance",
    "Responsable",
    "Revisores y contribuidores",
    "Aprobación",
    "Requisitos de gobierno de datos",
    "Roles y responsabilidades",
    "Bucles de feedback",
    "Medidas de éxito",
    "Cumplimiento y auditoría",
    "Glosario de términos",
)


class Role(BaseModel):
    name: str
    responsibilities: str


class RequirementGroup(BaseModel):
    name: str
    purpose: str
    items: list[str] = Field(min_length=1)


class PolicyInput(BaseModel):
    title: str
    version: str
    owner: str
    policy_leader: str
    contributors: list[str] = Field(min_length=1)
    approvers: list[str] = Field(min_length=1)
    last_approval: date
    review_frequency: str
    purpose: str
    scope: str
    outcomes: list[str] = Field(min_length=1)
    roles: list[Role] = Field(min_length=1)
    requirements: list[RequirementGroup] = Field(min_length=1)
    feedback: str
    measures_of_success: str
    compliance: str
