"""Structured diagnostic events shared by server and simulator.

Only pass operational metadata. Never pass prompts, transcripts, HTTP bodies,
credentials, or arbitrary exception messages (which can contain record data).
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
import sys
import traceback

_context = ContextVar('diagnostic_context', default={})
LOG = logging.getLogger('kyron.debug')
LOG.addHandler(logging.NullHandler())
LOG.propagate = False


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {'timestamp':datetime.now(timezone.utc).isoformat(), 'level':record.levelname,
                'event':record.getMessage(), **getattr(record, 'fields', {})}
        if record.exc_info and record.exc_info[1]:
            error = record.exc_info[1]
            data['error_type'] = type(error).__name__
            # Preserve stack locations and chained error types without printing
            # SQL parameters, model output, Pydantic inputs or authorization data.
            chain, seen = [], set()
            while error is not None and id(error) not in seen:
                seen.add(id(error))
                chain.append({'type':type(error).__name__, 'frames':[
                    {'file':frame.filename, 'line':frame.lineno, 'function':frame.name}
                    for frame in traceback.extract_tb(error.__traceback__)]})
                error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
            data['traceback'] = chain
        return json.dumps(data, default=str)


def configure(service):
    level = os.getenv('LOG_LEVEL', 'INFO').upper()
    if level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        level = 'INFO'
    LOG.setLevel(level)
    LOG.propagate = False
    if not any(isinstance(handler, logging.StreamHandler) for handler in LOG.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        LOG.addHandler(handler)
    bind(service=service)


def bind(**fields):
    _context.set({**_context.get(), **fields})


@contextmanager
def log_context(**fields):
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def log(event, level=logging.INFO, exc_info=False, **fields):
    LOG.log(level, event, extra={'fields':{**_context.get(), **fields}}, exc_info=exc_info)
