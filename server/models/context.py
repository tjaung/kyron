"""Practice and patient context needed by the initial replay workflow."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint, DateTime, Numeric
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class Practice(Base):
    city: Mapped[str | None]
    state: Mapped[str | None]
    postal_code: Mapped[str | None]
    country: Mapped[str | None]
    phone: Mapped[str | None]
    fax: Mapped[str | None]
    timezone: Mapped[str | None]
    is_active: Mapped[bool | None]
    __tablename__ = "practice"
    __table_args__ = {"schema": "providers"}
    practice_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    address: Mapped[str]
    specialty: Mapped[str]


class Provider(Base):
    credentials: Mapped[str | None]
    specialty: Mapped[str | None]
    license_number: Mapped[str | None]
    license_state: Mapped[str | None]
    phone: Mapped[str | None]
    email: Mapped[str | None]
    is_active: Mapped[bool | None]
    __tablename__ = "provider"
    __table_args__ = {"schema": "providers"}
    provider_id: Mapped[UUID] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    npi: Mapped[str | None] = mapped_column(unique=True)


class ProviderPractice(Base):
    role: Mapped[str | None]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    accepting_new_patients: Mapped[bool | None]
    __tablename__ = "provider_practice"
    __table_args__ = {"schema": "providers"}
    provider_practice_id: Mapped[UUID] = mapped_column(primary_key=True)
    provider_id: Mapped[UUID] = mapped_column(ForeignKey("providers.provider.provider_id"))
    practice_id: Mapped[UUID] = mapped_column(ForeignKey("providers.practice.practice_id"))


class Patient(Base):
    preferred_name: Mapped[str | None]
    sex_assigned_at_birth: Mapped[str | None]
    gender_identity: Mapped[str | None]
    pronouns: Mapped[str | None]
    race: Mapped[str | None]
    ethnicity: Mapped[str | None]
    preferred_language: Mapped[str | None]
    phone: Mapped[str | None]
    email: Mapped[str | None]
    address: Mapped[str | None]
    city: Mapped[str | None]
    state: Mapped[str | None]
    postal_code: Mapped[str | None]
    country: Mapped[str | None]
    preferred_contact_method: Mapped[str | None]
    interpreter_required: Mapped[bool | None]
    __tablename__ = "patient"
    __table_args__ = {"schema": "patients"}
    patient_id: Mapped[UUID] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    date_of_birth: Mapped[date]


class PatientPractice(Base):
    status: Mapped[str | None]
    registration_date: Mapped[date | None]
    primary_provider_practice_id: Mapped[UUID | None] = mapped_column(ForeignKey("providers.provider_practice.provider_practice_id"))
    __tablename__ = "patient_practice"
    __table_args__ = (
        UniqueConstraint("patient_id", "practice_id"),
        UniqueConstraint("practice_id", "medical_record_number"),
        {"schema": "patients"},
    )
    patient_practice_id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.patient.patient_id"))
    practice_id: Mapped[UUID] = mapped_column(ForeignKey("providers.practice.practice_id"))
    medical_record_number: Mapped[str]


class Prescription(Base):
    strength: Mapped[str | None]
    dose: Mapped[str | None]
    route: Mapped[str | None]
    frequency: Mapped[str | None]
    quantity_unit: Mapped[str | None]
    pharmacy_name: Mapped[str | None]
    pharmacy_phone: Mapped[str | None]
    status: Mapped[str | None]
    days_supply: Mapped[int | None]
    refills_authorized: Mapped[int | None]
    refills_remaining: Mapped[int | None]
    written_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    encounter_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinical.encounter.encounter_id"))
    __tablename__ = "prescription"
    __table_args__ = {"schema": "clinical"}
    prescription_id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_practice_id: Mapped[UUID] = mapped_column(
        ForeignKey("patients.patient_practice.patient_practice_id")
    )
    prescriber_provider_practice_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.provider_practice.provider_practice_id")
    )
    medication_name: Mapped[str]
