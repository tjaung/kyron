"""Deterministic fictional prescription scenarios; no external patient data."""
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5


def uid(label):
    return str(uuid5(NAMESPACE_URL, 'kyron-demo/' + label))


def build_dataset(base_context, base_sources):
    context = {'practices': deepcopy(base_context['practices'])}
    for key in ('providers', 'provider_practices', 'patients', 'patient_practices', 'conditions',
                'allergies', 'encounters', 'prescriptions', 'coverage', 'claims', 'authorizations'):
        context[key] = []
    for index, practice in enumerate(context['practices']):
        practice.update(address=f'{120 + index * 80} Meadow Lane', city='Brookfield', state='MA',
                        postal_code='01506', country='US', phone=f'202-555-01{10+index}',
                        fax=f'202-555-01{20+index}', timezone='America/New_York', is_active=True)
    provider_specs = [('Taylor', 'Demo'), ('Elena', 'Morris'), ('Daniel', 'Reed')]
    for index, (first, last) in enumerate(provider_specs):
        provider_id = uid('demo-provider' if index == 0 else 'provider/' + last)
        context['providers'].append(dict(provider_id=provider_id, first_name=first, last_name=last,
            npi=None, credentials='MD', specialty='Family medicine', license_number=f'DEMO-MA-{index+1:04}',
            license_state='MA', phone=f'202-555-01{30+index}', email=f'{first.lower()}.{last.lower()}@example.com', is_active=True))
        for practice_index, practice in enumerate(context['practices']):
            if index and index != practice_index + 1:
                continue
            context['provider_practices'].append(dict(
                provider_practice_id=uid(practice['name'] + '/provider' if index == 0 else practice['name'] + '/' + last),
                provider_id=provider_id, practice_id=practice['practice_id'], role='Physician',
                start_date='2022-01-01', end_date=None, accepting_new_patients=True))
    specs = [
        ('Atorvastatin', '20 mg', 'Hyperlipidemia', 'approved', 'positive',
         'The authorization was approved. The pharmacy can rerun the claim.', 'notify_pharmacy',
         'Oh, that is a relief. I was sure this was going to take all week. Thank you.'),
        ('Adalimumab', '40 mg/0.4 mL', 'Rheumatoid arthritis', 'pending', 'negative',
         'The request is pending because the insurer needs the most recent visit note.', 'request_visit_note',
         'Still pending? I already called twice. Sorry, I know it is not you, but this is exhausting.'),
        ('Levothyroxine', '75 mcg', 'Hypothyroidism', 'not_required', 'neutral',
         'Prior authorization is not required. The pharmacy needs a new prescription because the previous order has expired.', 'request_prescriber_renewal',
         'Okay, so it is the prescription, not insurance. Got it. Please send the request to my doctor.'),
        ('Budesonide-formoterol', '160 mcg/4.5 mcg', 'Asthma', 'denied', 'negative',
         'The authorization was denied under the plan formulary. The prescriber must review the decision and available next steps.', 'route_denial_to_prescriber',
         'Wait—denied? This is the inhaler on my record. I do not want to change anything without talking to my doctor.'),
        ('Semaglutide', '0.5 mg', 'Type 2 diabetes', 'coverage_inactive', 'mixed',
         'The old insurance plan is inactive. Updated coverage information is needed before an authorization can be reviewed.', 'request_updated_coverage',
         'Oh! I changed jobs last month. Hang on, yes, I have a new card. I can send it through the portal.'),
    ]
    roots = [source for source in base_sources if source['transcript']['ground_truth']['call_number'] == 1]
    source_by_patient = {s['transcript']['metadata']['patient_practice_id']: s for s in roots}
    by_id = {s['conversation_id']: s for s in base_sources}
    sources = []
    for index, original in enumerate(base_context['patients']):
        # Existing fixture IDs remain stable across upgrades and repeated seeding.
        patient_id = original['patient_id']
        registration_id = original['patient_practice_id']
        prescription_id = original['prescription_id']
        practice = next(p for p in context['practices'] if p['practice_id'] == original['practice_id'])
        affiliation = next(a for a in context['provider_practices'] if a['practice_id'] == practice['practice_id'] and a['provider_id'] != uid('demo-provider'))
        provider = next(p for p in context['providers'] if p['provider_id'] == affiliation['provider_id'])
        medication, strength, condition, outcome, sentiment, result, action, human_result = specs[index]
        name = original['first_name'] + ' ' + original['last_name']
        doctor = 'Dr. ' + provider['first_name'] + ' ' + provider['last_name']
        encounter_id, insurance_id = uid(patient_id + '/encounter'), uid(patient_id + '/coverage')
        patient = {key: original[key] for key in ('patient_id', 'first_name', 'last_name', 'date_of_birth')}
        patient.update(preferred_name=original['first_name'], sex_assigned_at_birth=None, gender_identity=None,
                       pronouns='they/them', race=None, ethnicity=None, preferred_language='English',
                       interpreter_required=False, phone=f'202-555-01{40+index}',
                       email=f'{original["first_name"].lower()}.{original["last_name"].lower()}@example.com',
                       address=f'{40+index} Willow Court', city='Brookfield', state='MA', postal_code='01506',
                       country='US', preferred_contact_method='phone')
        context['patients'].append(patient)
        context['patient_practices'].append(dict(patient_practice_id=registration_id, patient_id=patient_id,
            practice_id=practice['practice_id'], medical_record_number=f'DEMO-{index+1:03}',
            primary_provider_practice_id=affiliation['provider_practice_id'], status='active', registration_date='2023-02-01'))
        context['conditions'].append(dict(condition_id=uid(patient_id+'/condition'), patient_id=patient_id,
            recorded_by_provider_practice_id=affiliation['provider_practice_id'], description=condition,
            code_system=None, diagnosis_code=None, clinical_status='active', onset_date='2023-02-01',
            resolved_date=None, recorded_at='2026-08-10T14:00:00+00:00'))
        context['allergies'].append(dict(allergy_id=uid(patient_id+'/allergy'), patient_id=patient_id,
            substance='Latex', reaction='Contact rash', severity='mild', verification_status='patient-reported',
            recorded_at='2026-08-10T14:00:00+00:00'))
        context['encounters'].append(dict(encounter_id=encounter_id, patient_practice_id=registration_id,
            provider_practice_id=affiliation['provider_practice_id'], encounter_type='outpatient',
            reason_for_visit=f'{condition} follow-up', clinical_summary=f'Fictional follow-up with {doctor}; existing {medication} prescription reviewed. No new treatment instructions in this simulation.',
            status='completed', start_time='2026-08-10T14:00:00+00:00', end_time='2026-08-10T14:25:00+00:00'))
        context['prescriptions'].append(dict(prescription_id=prescription_id, patient_practice_id=registration_id,
            prescriber_provider_practice_id=affiliation['provider_practice_id'], encounter_id=encounter_id,
            medication_name=medication, strength=strength, dose='As recorded by prescriber',
            route=['oral','subcutaneous','oral','inhaled','subcutaneous'][index], frequency='Per existing prescription',
            quantity=[30,2,30,1,1][index], quantity_unit=['tablets','pens','tablets','inhaler','pen'][index], days_supply=30, refills_authorized=3,
            refills_remaining=0 if index==2 else 2, pharmacy_name='Meadow Community Pharmacy', pharmacy_phone='202-555-0160',
            status='expired' if index==2 else 'active', written_at='2026-02-01T14:00:00+00:00',
            expires_at='2026-08-31T23:59:59+00:00' if index==2 else '2027-02-01T14:00:00+00:00'))
        context['coverage'].append(dict(insurance_id=insurance_id, patient_id=patient_id,
            payer_name='Meadow Health Assurance', plan_name='Meadow Choice', plan_type='PPO',
            member_id=f'DEMO-MHA-{index+1:06}', group_number='DEMO-GRP-240', subscriber_name=name,
            relationship_to_subscriber='self', authorization_phone='202-555-0170', coverage_start='2026-01-01',
            coverage_end='2026-08-31' if index==4 else '2026-12-31', coverage_priority=1))
        context['claims'].append(dict(claim_id=uid(patient_id+'/claim'), patient_practice_id=registration_id,
            insurance_id=insurance_id, rendering_provider_practice_id=affiliation['provider_practice_id'],
            encounter_id=encounter_id, payer_claim_number=f'DEMO-CLM-{index+1:06}', claim_type='professional',
            status='paid', service_start_date='2026-08-10', service_end_date='2026-08-10',
            submitted_at='2026-08-11T09:00:00+00:00', adjudicated_at='2026-08-18T09:00:00+00:00',
            billed_amount=180, allowed_amount=120, paid_amount=100, patient_responsibility=20, currency='USD',
            denial_code=None, denial_reason=None))
        context['authorizations'].append(dict(authorization_id=uid(patient_id+'/authorization'),
            prescription_id=prescription_id, insurance_id=insurance_id, request_action_id=None,
            payer_reference_number=f'DEMO-PA-{index+1:06}', status=outcome, decision_reason=result,
            submitted_at='2026-09-01T09:00:00+00:00', decided_at=None if outcome=='pending' else '2026-09-02T09:00:00+00:00',
            valid_from='2026-09-02' if outcome=='approved' else None, valid_until='2027-09-01' if outcome=='approved' else None))
        scenario_name = ['Routine refill — authorization approved', 'Missing records — authorization pending', 'Expired prescription — renewal needed', 'Formulary denial — prescriber review', 'Inactive coverage — insurance update'][index]
        root = source_by_patient[registration_id]
        chain = [root]
        while chain[-1]['next_conversation']:
            chain.append(by_id[chain[-1]['next_conversation']])
        calls = [
            [('patient', f'Hi, um, this is {name}. I am calling about my {medication}. The pharmacy said to call you, and I am not really sure what is holding it up.'),
             ('ai_agent', f'Thank you for calling {practice["name"]}. I am Emily, the automated assistant. Please confirm your date of birth so I can locate the correct record.'),
             ('patient', f'It is {patient["date_of_birth"]}. Sorry, there is a little noise here. Can you hear me?'),
             ('ai_agent', f'Yes, I can hear you. Your record lists {doctor} and {medication}, {strength}, at Meadow Community Pharmacy. Is that the prescription you are asking about?'),
             ('patient', 'Yes, that one. I went over yesterday—no, sorry, Monday. They said there was a problem with the refill.'),
             ('ai_agent', 'I will check the prescription and insurance records, then—'),
             ('patient', 'Sorry to interrupt. Does that mean I have to call the insurance company myself?'),
             ('ai_agent', 'I can contact the insurance team for the administrative status. I cannot change your prescription or guarantee approval. I will record any next step for your care team.'),
             ('patient', ['Okay, great. That would save me a lot of running around.', 'Fine, but please do call me back. I have been passed around all morning.', 'That makes sense. I just need to know who has to do what.', 'All right. I am worried this is going to turn into another long wait.', 'Thanks. I am on my lunch break, so a callback would be better.'][index]),
             ('ai_agent', f'I will call you at the number ending in {patient["phone"][-4:]}. Is that correct?'),
             ('patient', 'Yes, that is my number. Thanks.'),
             ('ai_agent', 'Thank you. I have recorded your request and will call back after the status check.')],
            [('ai_agent', f'Hello. I am Emily, the automated assistant for {practice["name"]}. I am calling about the administrative status of an existing prescription.'),
             ('insurance_agent', 'Sure, I can take a look. This is Jay. Give me a second to open the right screen… Okay. Your callback number?'),
             ('ai_agent', f'Our callback number is {practice["phone"]}. The prescriber is {doctor}. The practice reference is {practice["practice_id"]}.'),
             ('insurance_agent', 'Got it. And the patient name, date of birth, and member ID?'),
             ('ai_agent', f'The patient is {name}, date of birth {patient["date_of_birth"]}, member ID DEMO-MHA-{index+1:06}.'),
             ('insurance_agent', 'Sorry, the last digits cut out. Can you repeat just the member ID?'),
             ('ai_agent', f'The member ID is DEMO-MHA-{index+1:06}.'),
             ('insurance_agent', 'Thanks. Found the record. Which medication are you checking?'),
             ('ai_agent', f'{medication}, {strength}. The prescription is linked to the August 10 follow-up for {condition}. Please confirm the status and any required administrative next step.'),
             ('insurance_agent', 'Let me read the latest note. Hmm… ' + result),
             ('ai_agent', f'To confirm: {result} Is that an accurate summary?'),
             ('insurance_agent', f'Yes, exactly. The reference is DEMO-PA-{index+1:06}. Please include it if you contact us again.'),
             ('ai_agent', 'Thank you. I will document that status and relay the next step to the patient and practice.'),
             ('insurance_agent', 'You are welcome. Hope the rest of your day is a little quieter than mine!')],
            [('ai_agent', f'Hello, this is Emily, the automated assistant from {practice["name"]}, returning your prescription inquiry. May I speak with {name}?'),
             ('patient', 'Yes, speaking. Oh, good, you called back.'),
             ('ai_agent', 'Before discussing the record, please confirm your date of birth.'),
             ('patient', patient['date_of_birth'] + '. Go ahead.'),
             ('ai_agent', result),
             ('patient', human_result),
             ('ai_agent', {'approved':'I will notify the pharmacy of the authorization reference. Please confirm availability with the pharmacy before traveling there.',
                           'pending':'I will request the missing note from your practice. The authorization is still pending; I do not have an approval date.',
                           'not_required':'I will send a renewal request to your prescriber. The prescription remains expired until the prescriber issues a new order.',
                           'denied':'I will route the denial to your prescriber for review. I will not substitute medication or present the denial as an approval.',
                           'coverage_inactive':'Please submit your updated insurance card through the practice portal. I will flag the record for a coverage update; no approval has been issued.'}[outcome]),
             ('patient', 'Right. Could you repeat the next step once more? I am writing it down.'),
             ('ai_agent', {'approved':'The pharmacy will be notified. Check with them before pickup.', 'pending':'Your practice needs to provide the recent visit note. The request remains pending.', 'not_required':'Your prescriber needs to review and issue a renewal.', 'denied':'Your prescriber needs to review the denial and discuss next steps with you.', 'coverage_inactive':'Send your new insurance card through the practice portal so coverage can be updated.'}[outcome]),
             ('patient', ['Perfect. Thanks for explaining it.', 'Okay. I am still frustrated, but at least I know what is missing.', 'Got it. Thank you for clearing that up.', 'All right. Please make sure my doctor sees it.', 'Will do. Thanks for catching that.'][index]),
             ('ai_agent', 'I have documented the outcome and the follow-up request. Thank you for your time.')],
        ]
        for call_index, (old, lines) in enumerate(zip(chain, calls)):
            turns = []
            for turn_index, (speaker, speech) in enumerate(lines):
                human = speaker != 'ai_agent'
                turn = dict(speaker=speaker, transcript=speech,
                            pause_before_ms=70 if 'interrupt' in speech else [300,750,450,1100][(turn_index+index)%4] if human else 450,
                            word_delay_ms=[95,130,165,110][(turn_index+index)%4] if human else 105)
                if turn_index == (7 if call_index==0 else 12 if call_index==1 else 8):
                    turn['action'] = dict(action='review_prescription_record' if call_index==0 else 'document_insurance_status' if call_index==1 else 'record_patient_followup',
                                          reason=f'Administrative follow-up for {name} and the linked {medication} prescription.', after_word=3)
                turns.append(turn)
            next_action = 'call_insurance' if call_index==0 else 'call_patient' if call_index==1 else action
            sources.append(dict(conversation_id=old['conversation_id'], name=f'{scenario_name} · {call_index+1}. ' + ['Patient prescription inquiry', 'Insurance status check', 'Patient status callback'][call_index], next_conversation=old['next_conversation'],
                transcript=dict(metadata=dict(practice_id=practice['practice_id'], patient_id=patient_id,
                    patient_practice_id=registration_id, provider_id=provider['provider_id'],
                    provider_practice_id=affiliation['provider_practice_id'], prescription_id=prescription_id,
                    scenario_name=scenario_name, encounter_id=encounter_id, insurance_id=insurance_id),
                    turns=turns, after_call_actions=[dict(action=next_action, reason='Continue the documented administrative workflow; no clinical changes are authorized.')],
                    ground_truth=dict(scenario=['routine-refill', 'missing-records', 'expired-prescription', 'formulary-denial', 'inactive-coverage'][index], call_number=call_index+1,
                        overall_sentiment=sentiment if call_index!=1 else 'neutral', reason_for_call=f'{medication} prescription status',
                        expected_outcome=outcome, expected_next_action=next_action))))
    from server.core.simulation_context import scenario_context
    return context, [{**{key:value for key,value in source.items() if key != 'transcript'}, 'context':scenario_context(source)} for source in sources]
