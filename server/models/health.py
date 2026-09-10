from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from server.core.database import Base


class PatientCondition(Base):
    __tablename__ = "patient_condition"
    __table_args__ = {"schema": "clinical"}
    condition_id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.patient.patient_id"))
    recorded_by_provider_practice_id: Mapped[UUID | None] = mapped_column(ForeignKey("providers.provider_practice.provider_practice_id"))
    code_system: Mapped[str | None]
    diagnosis_code: Mapped[str | None]
    description: Mapped[str | None]
    clinical_status: Mapped[str | None]
    onset_date: Mapped[date | None]
    resolved_date: Mapped[date | None]
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientAllergy(Base):
    __tablename__ = "patient_allergy"
    __table_args__ = {"schema": "clinical"}
    allergy_id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.patient.patient_id"))
    substance: Mapped[str | None]
    reaction: Mapped[str | None]
    severity: Mapped[str | None]
    verification_status: Mapped[str | None]
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Encounter(Base):
    __tablename__ = "encounter"
    __table_args__ = {"schema": "clinical"}
    encounter_id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_practice_id: Mapped[UUID] = mapped_column(ForeignKey("patients.patient_practice.patient_practice_id"))
    provider_practice_id: Mapped[UUID] = mapped_column(ForeignKey("providers.provider_practice.provider_practice_id"))
    encounter_type: Mapped[str | None]
    reason_for_visit: Mapped[str | None]
    clinical_summary: Mapped[str | None]
    status: Mapped[str | None]
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientInsurance(Base):
    __tablename__ = "patient_insurance"
    __table_args__ = {"schema": "insurance"}
    insurance_id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.patient.patient_id"))
    payer_name: Mapped[str | None]
    plan_name: Mapped[str | None]
    plan_type: Mapped[str | None]
    member_id: Mapped[str | None]
    group_number: Mapped[str | None]
    subscriber_name: Mapped[str | None]
    relationship_to_subscriber: Mapped[str | None]
    authorization_phone: Mapped[str | None]
    coverage_start: Mapped[date | None]
    coverage_end: Mapped[date | None]
    coverage_priority: Mapped[int | None]


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = {"schema": "insurance"}
    claim_id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_practice_id: Mapped[UUID] = mapped_column(ForeignKey("patients.patient_practice.patient_practice_id"))
    insurance_id: Mapped[UUID] = mapped_column(ForeignKey("insurance.patient_insurance.insurance_id"))
    rendering_provider_practice_id: Mapped[UUID | None] = mapped_column(ForeignKey("providers.provider_practice.provider_practice_id"))
    encounter_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinical.encounter.encounter_id"))
    payer_claim_number: Mapped[str | None]
    claim_type: Mapped[str | None]
    status: Mapped[str | None]
    denial_code: Mapped[str | None]
    denial_reason: Mapped[str | None]
    currency: Mapped[str | None]
    service_start_date: Mapped[date | None]
    service_end_date: Mapped[date | None]
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    allowed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    patient_responsibility: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class PriorAuthorization(Base):
    __tablename__ = "prior_authorization"
    __table_args__ = {"schema": "insurance"}
    authorization_id: Mapped[UUID] = mapped_column(primary_key=True)
    prescription_id: Mapped[UUID] = mapped_column(ForeignKey("clinical.prescription.prescription_id"))
    insurance_id: Mapped[UUID] = mapped_column(ForeignKey("insurance.patient_insurance.insurance_id"))
    request_action_id: Mapped[UUID | None] = mapped_column(ForeignKey("kyron.action_executions.action_id"))
    payer_reference_number: Mapped[str | None]
    status: Mapped[str | None]
    decision_reason: Mapped[str | None]
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[date | None]
    valid_until: Mapped[date | None]
