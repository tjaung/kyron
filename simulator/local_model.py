"""Small local model adapter. No cloud fallback and no payload logging."""
import http.client
import logging
import time
from .debug_logging import bind, log, log_context
import json
import os
import socket
from urllib.parse import urlsplit


def inference_schema(schema):
    """Inline Pydantic refs and leave size/format validation to the server.

    Ollama's grammar compiler rejects some bounded-string/UUID schemas. Keep
    types, field names, enums, required fields and unions as generation guards.
    """
    definitions=schema.get('$defs', {})
    def visit(value):
        if isinstance(value,list): return [visit(item) for item in value]
        if not isinstance(value,dict): return value
        if '$ref' in value:
            name=value['$ref'].rsplit('/',1)[-1]
            if name not in definitions: raise ValueError('Unknown model schema reference')
            return visit(definitions[name])
        return {key:({name:visit(spec) for name,spec in item.items()} if key=='properties' else visit(item)) for key,item in value.items()
                if key not in ('$defs','title','default','format','minLength','maxLength','minimum','maximum','minItems')}
    return visit(schema)


class LocalModel:
    def __init__(self, output_tokens=1800):
        self.output_tokens = output_tokens
        self.url = os.getenv('OLLAMA_URL', 'http://localhost:11434').rstrip('/')
        self.name = os.getenv('OLLAMA_MODEL', 'qwen3:4b')
        self.timeout = float(os.getenv('MODEL_TIMEOUT_SECONDS', '300'))

    def generate(self, system, messages, schema, cancellation=None):
        started = time.monotonic()
        with log_context(model=self.name, model_phase='request'):
            log('model.request.started', history_messages=len(messages), timeout_seconds=self.timeout)
            try:
                result = self._generate(system, messages, schema, cancellation)
            except Exception:
                log('model.request.failed', level=logging.ERROR, exc_info=True,
                    duration_ms=round((time.monotonic()-started)*1000))
                raise
            log('model.request.completed', duration_ms=round((time.monotonic()-started)*1000))
            return result

    def _generate(self, system, messages, schema, cancellation=None):
        if cancellation: cancellation.check()
        chat = [{'role': 'system', 'content': system}, *messages]
        # Older Qwen3 templates unconditionally open <think>, ignoring think=False.
        # Close that block explicitly before JSON grammar starts constraining output.
        # Otherwise the model serializes its reasoning (often copied input) as speech.
        if self.name.rsplit('/', 1)[-1].startswith('qwen3:'):
            chat.append({'role': 'assistant', 'content': '<think>\n\n</think>\n\n'})
        payload = {'model': self.name, 'think': False, 'stream': False,
                   'messages': chat,
                   'format': inference_schema(schema), 'options': {'temperature': 0.4, 'num_ctx': 16384, 'num_predict': self.output_tokens}}
        url = urlsplit(self.url)
        if url.scheme not in ('http','https') or not url.hostname:
            raise ValueError('OLLAMA_URL must be an HTTP(S) URL')
        connection_type = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
        connection = connection_type(url.hostname,url.port,timeout=5)
        unregister = None
        try:
            bind(model_phase='connect')
            connection.connect()
            sock = connection.sock
            sock.settimeout(self.timeout)
            # Retain the socket even if HTTPConnection detaches it for a
            # Connection: close response. Shutdown interrupts a blocked read.
            if cancellation:
                unregister = cancellation.register(lambda: sock.shutdown(socket.SHUT_RDWR))
                cancellation.check()
            bind(model_phase='inference')
            connection.request('POST',url.path.rstrip('/')+'/api/chat',body=json.dumps(payload).encode(),
                               headers={'Content-Type':'application/json'})
            response = connection.getresponse()
            log('model.http.received', status_code=response.status)
            if response.status != 200:
                error_body=response.read(4096)
                if b'failed to parse grammar' in error_body:
                    log('model.schema.rejected', level=logging.ERROR, reason='grammar_parse_failed')
                raise ValueError(f'Local model HTTP {response.status}')
            body = response.read()
            bind(model_phase='decode_response')
            output = json.loads(body)
            if cancellation: cancellation.check()
        except Exception:
            if cancellation: cancellation.check()
            raise
        finally:
            if unregister: unregister()
            connection.close()
        log('model.output.received', done_reason=output.get('done_reason'),
            prompt_tokens=output.get('prompt_eval_count'), output_tokens=output.get('eval_count'))
        bind(model_phase='validate_output')
        if output.get('done_reason') == 'length':
            raise ValueError('Model response exceeded the output limit')
        bind(model_phase='parse_generated_json')
        result = json.loads(output['message']['content'])
        if not isinstance(result, dict):
            raise ValueError('Model must return a JSON object')
        return result
