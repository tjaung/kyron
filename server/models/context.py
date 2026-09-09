"""Practice and patient context needed by the initial replay workflow."""

from datetime import date
from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class Practice(Base):
    __tablename__ = "practice"
    __table_args__ = {"schema": "providers"}
    practice_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    address: Mapped[str]
    specialty: Mapped[str]


class Provider(Base):
    __tablename__ = "provider"
    __table_args__ = {"schema": "providers"}
    provider_id: Mapped[UUID] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    npi: Mapped[str | None] = mapped_column(unique=True)


class ProviderPractice(Base):
    __tablename__ = "provider_practice"
    __table_args__ = {"schema": "providers"}
    provider_practice_id: Mapped[UUID] = mapped_column(primary_key=True)
    provider_id: Mapped[UUID] = mapped_column(ForeignKey("providers.provider.provider_id"))
    practice_id: Mapped[UUID] = mapped_column(ForeignKey("providers.practice.practice_id"))


class Patient(Base):
    __tablename__ = "patient"
    __table_args__ = {"schema": "patients"}
    patient_id: Mapped[UUID] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    date_of_birth: Mapped[date]


class PatientPractice(Base):
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
