from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PatientSummary(BaseModel):
    patient_id: UUID
    first_name: str
    last_name: str
    date_of_birth: date
    medical_record_number: str


class ProviderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider_id: UUID
    first_name: str
    last_name: str
    npi: str | None


class PatientPage(BaseModel):
    items: list[PatientSummary]
    total: int


class ProviderPage(BaseModel):
    items: list[ProviderSummary]
    total: int
