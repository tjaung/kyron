"""Conservative checks for the seeded intake identity/permission evidence."""
import re


def permission(turns):
    answer=None; previous=''
    for turn in sorted(turns,key=lambda item:item.turn_index):
        text=turn.transcript.casefold()
        if turn.speaker=='ai_agent':
            previous=text; continue
        prompted=any(word in previous for word in ('permission','consent','discuss','share this','share your'))
        negative=bool(re.search(r"\b(i (?:do not|don't) consent|you may not|do not (?:share|discuss)|don't (?:share|discuss)|i refuse)\b",text))
        positive=bool(re.search(r'\b(i consent|you may (?:share|discuss)|permission is confirmed|i give (?:my )?permission)\b',text))
        if negative or (prompted and re.search(r'^\s*no[,.!\s]',text)): answer=False
        elif positive or (prompted and re.search(r'\b(yes|okay|go ahead)\b',text)): answer=True
        previous=''
    return answer


def identity_matches(patient, turns):
    if patient is None or patient.date_of_birth is None: return False
    text=' '.join(turn.transcript.casefold() for turn in turns if turn.speaker!='ai_agent')
    if not all(name.casefold() in text for name in (patient.first_name,patient.last_name)): return False
    birth=patient.date_of_birth
    formats=(birth.isoformat(),birth.strftime('%B %-d, %Y').casefold(),birth.strftime('%B %-d %Y').casefold(),
             birth.strftime('%m/%d/%Y'),f'{birth.month}/{birth.day}/{birth.year}')
    return any(value in text for value in formats)
