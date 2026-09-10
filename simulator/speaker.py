"""Two conversational agents with fixed identities and independent chat histories."""
import json
import logging
from .debug_logging import log
import re


def normalized(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


class SpeakerAgent:
    def __init__(self, role, system, model, cancellation=None, opening=None):
        self.role = role
        self.system = system
        self.model = model
        self.cancellation = cancellation
        self.opening = opening
        self.messages = []
        self.spoken = []

    def respond(self, incoming, instructions, schema, patient_name=''):
        request = {
            'instruction': f'It is YOUR turn as {self.role}. Respond to the other speaker in character. Never copy their utterance or assume their identity.',
            'other_speaker': incoming,
            'turn_instructions': instructions,
        }
        human = self.role != 'ai_agent'
        # Human history is plain dialogue. Keep opening instructions out of it,
        # so later requests focus on the latest question instead of restarting.
        content = incoming['text'] if human and incoming else json.dumps(request)
        messages = [*self.messages, {'role':'user','content':content}]
        system = self.system
        if human:
            if instructions.get('turn_budget'):
                system += '\nCurrent call budget: ' + json.dumps(instructions['turn_budget'])
            if not self.spoken:
                system += '\nThis is your first reply. Introduce yourself and explain the following situation: ' + json.dumps(self.opening)
            else:
                system += ('\nThe call is already underway. Answer the LAST user message directly using your facts. '
                           'If asked for multiple details, answer each one. If a detail is absent, say you do not know it. '
                           'Do not restart the call or repeat why you called. Your answer must move this exchange forward.')
        schema = {**schema, 'properties': {**schema['properties'], 'speaker':{'type':'string','const':self.role}},
                  'required': [*schema['required'],'speaker']}
        for attempt in range(3):
            if self.cancellation: self.cancellation.check()
            kwargs = {'cancellation':self.cancellation} if self.cancellation else {}
            log('speaker.attempt.started', speaker=self.role, attempt=attempt+1, history_messages=len(messages))
            result = self.model.generate(system,messages,schema,**kwargs)
            text = result.get('text')
            error = None
            if (result.get('speaker') != self.role or not isinstance(text,str) or not text.strip()
                    or len(text)>6000 or type(result.get('end_call')) is not bool):
                error = 'Return valid JSON with your assigned speaker and a nonempty spoken response.'
            else:
                previous = [*self.spoken[-3:], *([incoming['text']] if incoming else [])]
                if len(normalized(text)) >= 40 and any(normalized(text)==normalized(old) for old in previous):
                    error = 'You copied a previous utterance. Answer the other person or ask the next relevant question; do not repeat their request.'
                if self.role == 'ai_agent' and patient_name and re.search(
                        r"\b(?:i am|i'm|my name is|this is)\s+"+re.escape(patient_name.casefold()), text.casefold()):
                    error = 'You adopted the patient identity. You are Emily, the practice assistant, and must respond to the patient.'
            if error is None:
                self.messages = [*self.messages, {'role':'user','content':incoming['text'] if human and incoming else content},
                                 {'role':'assistant','content':text if human else json.dumps(result)}]
                self.spoken.append(text)
                return result
            log('speaker.response.rejected', level=logging.WARNING, speaker=self.role, attempt=attempt+1,
                reason=error, exhausted=attempt == 2)
            if attempt == 2:
                raise ValueError('Speaker failed role or repetition validation')
            # Do not add the invalid speech to either history or the transcript.
            messages = [*self.messages, {'role':'user','content':
                content + '\n\nResponse correction: ' + error if human else json.dumps({**request,'correction':error})}]
