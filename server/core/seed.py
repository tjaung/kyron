"""Idempotent fictional fixtures. Runtime records and source usage are preserved."""
from datetime import date, datetime
import json
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import Date, DateTime, Uuid, inspect, text
from sqlalchemy.schema import CreateColumn, AddConstraint
from sqlalchemy.orm import Session

from server.core.database import Base, engine
from server.models.context import Patient, PatientPractice, Practice, Prescription, Provider, ProviderPractice
from server.models.health import PatientCondition, PatientAllergy, Encounter, PatientInsurance, Claim, PriorAuthorization
from server.models import workflow  # Register reusable definitions.
from server.models import conversation  # Register runtime models.
from server.models.simulation import SimulationConversation

DATA = Path(__file__).resolve().parents[1] / 'data'
MODELS = {'practices': Practice, 'providers': Provider, 'provider_practices': ProviderPractice,
          'patients': Patient, 'patient_practices': PatientPractice, 'conditions': PatientCondition,
          'allergies': PatientAllergy, 'encounters': Encounter, 'prescriptions': Prescription,
          'coverage': PatientInsurance, 'claims': Claim, 'authorizations': PriorAuthorization}


def stable_id(label):
    return uuid5(NAMESPACE_URL, 'kyron-demo/' + label)


def load_sources():
    return json.loads((DATA / 'conversations.json').read_text())


def validate_dataset(context, sources):
    from server.core.simulation_context import scenario_context
    indices = {}
    for group, model in MODELS.items():
        pk = next(iter(model.__table__.primary_key)).name
        rows = context[group]
        indices[model.__table__.fullname] = {row[pk]: row for row in rows}
        if len(indices[model.__table__.fullname]) != len(rows):
            raise ValueError(f'Duplicate seed IDs in {group}')
    for group, model in MODELS.items():
        for row in context[group]:
            for fk in model.__table__.foreign_keys:
                value = row.get(fk.parent.name)
                if value is not None and value not in indices.get(fk.column.table.fullname, {}):
                    raise ValueError(f'Invalid {group}.{fk.parent.name}')
    registrations = indices['patients.patient_practice']
    affiliations = indices['providers.provider_practice']
    prescriptions = indices['clinical.prescription']
    for registration in registrations.values():
        affiliation = affiliations[registration['primary_provider_practice_id']]
        if affiliation['practice_id'] != registration['practice_id']:
            raise ValueError('Patient primary provider belongs to another practice')
    by_id = {row['conversation_id']: row for row in sources}
    if len(by_id) != len(sources):
        raise ValueError('Duplicate conversation IDs')
    for row in sources:
        payload = scenario_context(row)
        if not payload.get('objective') or payload.get('counterpart') not in ('patient','insurance_agent','provider','pharmacy'):
            raise ValueError('Invalid model scenario context')
        links = payload['metadata']
        registration = registrations[links['patient_practice_id']]
        affiliation = affiliations[links['provider_practice_id']]
        prescription = prescriptions[links['prescription_id']]
        if not (registration['patient_id'] == links['patient_id'] and
                registration['practice_id'] == affiliation['practice_id'] == links['practice_id'] and
                affiliation['provider_id'] == links['provider_id'] and
                prescription['patient_practice_id'] == links['patient_practice_id'] and
                prescription['prescriber_provider_practice_id'] == links['provider_practice_id']):
            raise ValueError('Inconsistent conversation context')
        encounter = indices['clinical.encounter'][links['encounter_id']]
        coverage = indices['insurance.patient_insurance'][links['insurance_id']]
        if not (encounter['patient_practice_id'] == links['patient_practice_id'] and
                encounter['provider_practice_id'] == links['provider_practice_id'] and
                prescription['encounter_id'] == links['encounter_id'] and
                coverage['patient_id'] == links['patient_id']):
            raise ValueError('Inconsistent encounter or insurance context')
        seen, current = set(), row['conversation_id']
        while current:
            if current in seen or current not in by_id:
                raise ValueError('Seed chain contains a cycle or missing conversation')
            seen.add(current)
            following = by_id[current]
            if any(scenario_context(following)['metadata'][key] != links[key] for key in
                   ('practice_id', 'patient_id', 'provider_id', 'prescription_id')):
                raise ValueError('Conversation chain crosses patient or practice context')
            current = following['next_conversation']


def seed(session):
    from server.core.workflow_seed import seed_workflow, seed_intake
    seed_workflow(session)
    seed_intake(session)
    session.execute(text("""UPDATE kyron.action_executions e SET action_definition_id = a.action_id
        FROM kyron.actions a WHERE e.action_definition_id IS NULL AND e.action = a.code AND a.version = 1"""))
    context = json.loads((DATA / 'context.json').read_text())
    sources = load_sources()
    validate_dataset(context, sources)
    for group, model in MODELS.items():
        pk = next(iter(model.__table__.primary_key)).name
        for item in context[group]:
            values = {}
            for key, value in item.items():
                column = model.__table__.c[key]
                if value is not None:
                    if isinstance(column.type, Uuid): value = UUID(value)
                    elif isinstance(column.type, DateTime): value = datetime.fromisoformat(value)
                    elif isinstance(column.type, Date): value = date.fromisoformat(value)
                values[key] = value
            row = session.get(model, values[pk])
            if row is None:
                session.add(model(**values))
            else:
                for key, value in values.items(): setattr(row, key, value)
        session.flush()
    for item in sources:
        source_id = UUID(item['conversation_id'])
        row = session.get(SimulationConversation, source_id)
        if row is None:
            row = SimulationConversation(conversation_id=source_id)
            session.add(row)
        row.name = item['name']
        from server.core.simulation_context import scenario_context
        row.context = scenario_context(item)
        row.next_conversation = UUID(item['next_conversation']) if item['next_conversation'] else None
        # Never reset is_used: generated history and trigger consumption are separate.


def upgrade_demo_schema(connection):
    """Add nullable columns to existing demo databases, including their foreign keys."""
    inspector = inspect(connection)
    for table in Base.metadata.sorted_tables:
        existing = {column['name'] for column in inspector.get_columns(table.name, schema=table.schema)}
        for column in table.columns:
            if column.name in existing:
                continue
            if not column.nullable:
                raise ValueError(f'An explicit migration is required for {table.fullname}.{column.name}')
            definition = str(CreateColumn(column).compile(dialect=connection.dialect))
            connection.execute(text(f'ALTER TABLE {table.fullname} ADD COLUMN {definition}'))
            for fk in column.foreign_keys:
                constraint = fk.constraint
                constraint.name = f'{table.name}_{column.name}_fk'
                connection.execute(AddConstraint(constraint))
    connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS conversation_parent_unique ON kyron.conversation_record(parent_conversation_id)'))
    connection.execute(text('''UPDATE kyron.conversation_record c SET
        patient_id = p.patient_id
        FROM patients.patient_practice p
        WHERE c.patient_practice_id = p.patient_practice_id AND c.patient_id IS NULL'''))
    connection.execute(text('''UPDATE kyron.conversation_record c SET
        provider_id = pp.provider_id, provider_practice_id = pp.provider_practice_id
        FROM clinical.prescription rx JOIN providers.provider_practice pp
        ON rx.prescriber_provider_practice_id = pp.provider_practice_id
        WHERE c.prescription_id = rx.prescription_id AND c.provider_id IS NULL'''))


def initialize_database():
    with engine.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(714202)'))
        for schema in ('providers', 'patients', 'clinical', 'insurance', 'simulation', 'kyron'):
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema}'))
        inspector = inspect(connection)
        if inspector.has_table('actions', schema='kyron') and any(c['name'] == 'analysis_id' for c in inspector.get_columns('actions', schema='kyron')):
            connection.execute(text('ALTER TABLE kyron.actions RENAME TO action_executions'))
        if inspector.has_table('conversation', schema='simulation') and any(c['name'] == 'transcript' for c in inspector.get_columns('conversation', schema='simulation')):
            connection.execute(text('ALTER TABLE simulation.conversation RENAME COLUMN transcript TO context'))
        Base.metadata.create_all(connection)
        upgrade_demo_schema(connection)
        with Session(bind=connection) as session:
            seed(session)
            session.flush()
