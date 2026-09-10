"""Convert legacy fixture scripts into model inputs, retaining source IDs/history."""
from copy import deepcopy


def scenario_context(source):
    if 'context' in source:
        context=deepcopy(source['context'])
        context.setdefault('counterpart_facts',{}).setdefault('patient',{}).setdefault('contact_permission',True)
        return context
    payload = source['transcript']
    truth = payload.get('ground_truth', {})
    outcome = truth.get('expected_outcome', 'unknown')
    return {
        'metadata': payload['metadata'],
        'objective': 'Help the caller resolve the linked prescription request using the new-prescription workflow. Confirm facts, obtain missing information, and arrange the appropriate next contact.',
        'counterpart': 'insurance_agent' if truth.get('call_number') == 2 else 'patient',
        'situation': truth.get('reason_for_call', source['name']),
        'personality': {'positive': 'Friendly, conversational, occasionally corrects a detail.',
                        'negative': 'Frustrated about the delay; asks concrete questions and sometimes interrupts.',
                        'neutral': 'Matter-of-fact; answer briefly and request clarification when needed.'}.get(truth.get('overall_sentiment'), 'Natural and conversational.'),
        'scenario_outcome': outcome,
        'counterpart_facts': {
            'pharmacy': {
                'reference': 'SIM-PHARM-' + source['conversation_id'][:8],
                'claim_status': 'paid' if outcome == 'approved' else 'rejected',
                'claim_reason': {'approved':'none','pending':'prior_authorization','denied':'non_formulary',
                                 'not_required':'expired prescription','coverage_inactive':'inactive coverage'}.get(outcome,'unknown'),
                'fill_status': 'ready' if outcome == 'approved' else 'delayed',
                'patient_cost': '$12.50' if outcome == 'approved' else 'Not yet known',
                'pickup_or_delivery': 'Ready for pickup during regular pharmacy hours' if outcome == 'approved' else 'Not ready for pickup',
            },
            'patient': {'contact_permission': True, 'reported_urgent_symptoms': False, 'request': 'Help me resolve the prescription delay.'},
        },
        'instructions': 'Only report facts available in the linked records. Do not invent receipts, approvals, costs, documents, or a completed prescription. Unknown facts remain unknown.',
    }
