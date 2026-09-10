"""Replay a stored JSON conversation to the server, one word at a time."""

from datetime import datetime, timezone
import json
import logging
from .debug_logging import log
import math
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def delay(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Delays must be numbers in milliseconds")
    if not math.isfinite(value) or not 0 <= value <= 60_000:
        raise ValueError("Delays must be between 0 and 60000 milliseconds")
    return value / 1000


def words(text):
    # Preserve whitespace so concatenated word events reconstruct the source.
    return re.findall(r"\s*\S+\s*", text)


def validate_action(action):
    if not isinstance(action, dict):
        raise ValueError("An action must be an object")
    for key in ("action", "reason"):
        if not isinstance(action.get(key), str) or not action[key].strip():
            raise ValueError(f"Action {key} must be nonempty text")


def validate_payload(payload):
    """Validate every turn before creating anything on the destination server."""
    if not isinstance(payload, dict) or not isinstance(payload.get("metadata"), dict):
        raise ValueError("Payload must contain a metadata object")
    metadata = payload["metadata"]
    UUID(str(metadata.get("practice_id")))
    for key in ("patient_practice_id", "prescription_id", "patient_id", "provider_id", "provider_practice_id"):
        if metadata.get(key) is not None:
            UUID(str(metadata[key]))
    turns = payload.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("Payload must contain a nonempty turns array")
    for turn in turns:
        if not isinstance(turn, dict):
            raise ValueError("Each turn must be an object")
        for key in ("speaker", "transcript"):
            if not isinstance(turn.get(key), str) or not turn[key].strip():
                raise ValueError(f"Turn {key} must be nonempty text")
        delay(turn.get("pause_before_ms", 600))
        delay(turn.get("word_delay_ms", 150))
        if turn.get("action") is not None:
            validate_action(turn["action"])
            position = turn["action"].get("after_word", len(words(turn["transcript"])))
            if type(position) is not int or not 1 <= position <= len(words(turn["transcript"])):
                raise ValueError("after_word must be a one-based word position in the turn")
    after_call = payload.get("after_call_actions", [])
    if not isinstance(after_call, list):
        raise ValueError("after_call_actions must be an array")
    for action in after_call:
        validate_action(action)
        if "after_word" in action:
            raise ValueError("after_word only applies to turn actions")


class ServerClient:
    def __init__(self, base_url, token=None, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def post(self, path, payload):
        started = time.monotonic()
        request_id = str(uuid4())
        level = logging.DEBUG if payload.get('type') == 'transcript.word' else logging.INFO
        fields = {'request_id':request_id, 'endpoint':path, 'event_type':payload.get('type'),
                  'sequence':payload.get('sequence')}
        log('server.request.started', level=level, **fields)
        headers = {"Content-Type": "application/json", "X-Request-ID":request_id}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            self.base_url + path,
            data=json.dumps(payload, allow_nan=False).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except HTTPError as error:
            log('server.request.rejected', level=logging.ERROR, status_code=error.code,
                duration_ms=round((time.monotonic()-started)*1000), **fields)
            error.close()
            raise
        except Exception:
            log('server.request.failed', level=logging.ERROR, exc_info=True,
                duration_ms=round((time.monotonic()-started)*1000), **fields)
            raise
        log('server.request.completed', level=level, duration_ms=round((time.monotonic()-started)*1000), **fields)
        return json.loads(body) if body else None

    def create_conversation(self, metadata):
        response = self.post("/conversations", metadata)
        if not isinstance(response, dict) or "id" not in response:
            raise ValueError("Server must return a conversation object with a UUID id")
        return str(UUID(str(response["id"])))

    def send_event(self, conversation_id, event):
        self.post(f"/conversations/{conversation_id}/events", event)


def generate_conversation(source_id, payload, client, sleep=time.sleep, name=None):
    validate_payload(payload)
    metadata = {
        key: payload["metadata"].get(key)
        for key in ("practice_id", "patient_practice_id", "prescription_id", "patient_id", "provider_id", "provider_practice_id")
    }
    # Send only links and runtime metadata, never future transcript or ground truth.
    metadata.update(source_conversation_id=str(source_id), start_time=timestamp())
    if name:
        metadata["name"] = name
    conversation_id = client.create_conversation(metadata)
    sequence = 0

    def emit(event_type, **fields):
        nonlocal sequence
        sequence += 1
        client.send_event(conversation_id, {
            "type": event_type,
            "sequence": sequence,
            "occurred_at": timestamp(),
            **fields,
        })

    def emit_action(action, transcript_id):
        emit("action.simulated", action_id=str(uuid4()), transcript_id=transcript_id,
             action=action["action"], reason=action["reason"], simulated=True)

    for turn_index, turn in enumerate(payload["turns"]):
        sleep(delay(turn.get("pause_before_ms", 600)))
        transcript_id = str(uuid4())
        emit("transcript.started", transcript_id=transcript_id,
             turn_index=turn_index, speaker=turn["speaker"])
        chunks = words(turn["transcript"])
        action = turn.get("action")
        for word_index, chunk in enumerate(chunks, start=1):
            sleep(delay(turn.get("word_delay_ms", 150)))
            emit("transcript.word", transcript_id=transcript_id,
                 word_index=word_index, delta=chunk)
            if action and action.get("after_word", len(chunks)) == word_index:
                emit_action(action, transcript_id)
        emit("transcript.completed", transcript_id=transcript_id)

    emit("conversation.ended")
    for action in payload.get("after_call_actions", []):
        emit_action(action, None)
    emit("replay.completed")
    return conversation_id
