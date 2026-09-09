"""Idempotent demo bootstrap. Existing source usage and runtime data are preserved."""

from datetime import date
import json
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from server.core.database import Base, engine
from server.models.context import Patient, PatientPractice, Practice, Prescription, Provider, ProviderPractice
from server.models import conversation  # Register runtime models with the metadata.
from server.models.simulation import SimulationConversation

DATA = Path(__file__).resolve().parents[1] / "data"


def stable_id(label):
    return uuid5(NAMESPACE_URL, "kyron-demo/" + label)


def load_sources():
    sources = json.loads((DATA / "conversations.json").read_text())
    by_id = {row["conversation_id"]: row for row in sources}
    if len(by_id) != len(sources):
        raise ValueError("Seed conversation IDs must be unique")
    for row in sources:
        seen = set()
        current = row["conversation_id"]
        while current:
            if current in seen or current not in by_id:
                raise ValueError("Seed chain contains a cycle or missing conversation")
            seen.add(current)
            current = by_id[current]["next_conversation"]
    return sources


def seed(session):
    context = json.loads((DATA / "context.json").read_text())
    for item in context["practices"]:
        practice_id = UUID(item["practice_id"])
        if session.get(Practice, practice_id) is None:
            session.add(Practice(**{**item, "practice_id": practice_id}))
    provider_id = stable_id("demo-provider")
    if session.get(Provider, provider_id) is None:
        session.add(Provider(provider_id=provider_id, first_name="Taylor", last_name="Demo", npi=None))
    session.flush()
    for item in context["practices"]:
        affiliation_id = stable_id(item["name"] + "/provider")
        if session.get(ProviderPractice, affiliation_id) is None:
            session.add(ProviderPractice(provider_practice_id=affiliation_id,
                                        provider_id=provider_id, practice_id=UUID(item["practice_id"])))
    for item in context["patients"]:
        patient_id = UUID(item["patient_id"])
        if session.get(Patient, patient_id) is None:
            session.add(Patient(patient_id=patient_id, first_name=item["first_name"],
                                last_name=item["last_name"], date_of_birth=date.fromisoformat(item["date_of_birth"])))
    session.flush()
    for index, item in enumerate(context["patients"], 1):
        registration_id = UUID(item["patient_practice_id"])
        if session.get(PatientPractice, registration_id) is None:
            session.add(PatientPractice(patient_practice_id=registration_id,
                patient_id=UUID(item["patient_id"]), practice_id=UUID(item["practice_id"]),
                medical_record_number=f"DEMO-{index:03}"))
    session.flush()
    for item in context["patients"]:
        prescription_id = UUID(item["prescription_id"])
        practice = next(p for p in context["practices"] if p["practice_id"] == item["practice_id"])
        if session.get(Prescription, prescription_id) is None:
            session.add(Prescription(prescription_id=prescription_id,
                patient_practice_id=UUID(item["patient_practice_id"]),
                prescriber_provider_practice_id=stable_id(practice["name"] + "/provider"),
                medication_name=item["medication_name"]))
    session.flush()
    for item in load_sources():
        source_id = UUID(item["conversation_id"])
        if session.get(SimulationConversation, source_id) is None:
            session.add(SimulationConversation(conversation_id=source_id, name=item["name"],
                transcript=item["transcript"],
                next_conversation=UUID(item["next_conversation"]) if item["next_conversation"] else None))


def initialize_database():
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(714202)"))
        for schema in ("providers", "patients", "clinical", "insurance", "simulation", "kyron"):
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            seed(session)
            session.flush()
