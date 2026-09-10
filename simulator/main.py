"""Local background app: generate calls, analyze them, and dispatch follow-up calls."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import threading
import hmac
from urllib.parse import urlsplit
from uuid import UUID

from .debug_logging import configure, log, log_context
from .database import connect
from .cancellation import Cancellation
from .generate_conversation import ServerClient
from .agent_conversation import generate_agent_conversation
from .randomize_conversation import get_conversation, mark_used, randomize_conversation

LOG = logging.getLogger("simulator")


class Simulator:
    def __init__(self, client, connection_factory=connect):
        self.client = client
        self.connection_factory = connection_factory
        self.lock = threading.Lock()
        self.state = {"status": "idle"}
        self.worker = None
        self.pending = None
        self.accepting_continuation = False
        self.cancellation = Cancellation()

    def status(self):
        with self.lock:
            return self.state.copy()

    def trigger(self, conversation_id=None, parent_id=None):
        with self.lock:
            if self.state["status"] in ("running", "maintenance"):
                return False
            self.cancellation = Cancellation()
            self.state = {"status": "running"}
            self.worker = threading.Thread(target=self.run, args=(conversation_id,parent_id))
            self.worker.start()
            log("simulation.trigger.accepted", source_conversation_id=conversation_id, parent_conversation_id=parent_id)
        return True

    def cancel(self, conversation_id):
        with self.lock:
            if self.state.get('conversation_id') != conversation_id or self.state['status'] != 'running':
                return False
            self.accepting_continuation = False
            self.pending = None
            cancellation = self.cancellation
        log("simulation.cancel.requested", conversation_id=conversation_id)
        cancellation.cancel()
        return True

    def begin_maintenance(self):
        with self.lock:
            if self.state['status'] in ('running', 'maintenance'):
                return False
            self.state = {'status': 'maintenance'}
            return True

    def end_maintenance(self):
        with self.lock:
            if self.state['status'] == 'maintenance':
                self.state = {'status': 'idle'}

    def continue_call(self, conversation_id, parent_id):
        with self.lock:
            if self.state['status'] == 'running':
                if (not self.accepting_continuation or self.state.get('source_conversation_id') != conversation_id
                        or self.state.get('conversation_id') != parent_id):
                    return False
                request = (conversation_id,parent_id)
                if self.pending and self.pending != request: return False
                log("simulation.continuation.queued", source_conversation_id=conversation_id, parent_conversation_id=parent_id)
                self.pending = request
                return True
        return self.trigger(conversation_id,parent_id)

    def run(self, conversation_id, parent_id=None):
        with log_context(service="simulator", source_conversation_id=conversation_id, parent_conversation_id=parent_id):
            self._run(conversation_id, parent_id)

    def _run(self, conversation_id, parent_id=None):
        completed = []
        source_id = conversation_id
        try:
            while True:
                self.cancellation.check()
                log("scenario.select.started", source_conversation_id=source_id, follow_up=bool(parent_id))
                with self.connection_factory() as connection:
                    if parent_id:
                        source = connection.execute("SELECT conversation_id, name, context FROM simulation.conversation WHERE conversation_id = %s",(source_id,)).fetchone()
                    else:
                        source = randomize_conversation(connection) if source_id is None else get_conversation(connection,source_id)
                    if source is None:
                        raise LookupError('No unused scenario is available')
                    source_id = str(source['conversation_id'])
                    log('scenario.select.completed', source_conversation_id=source_id)
                    with self.lock:
                        self.state = {'status':'running','source_conversation_id':source_id,'name':source['name'],
                                      'completed_conversations':completed.copy()}
                        self.pending = None
                        self.accepting_continuation = True
                    def created(runtime_id):
                        with self.lock: self.state['conversation_id'] = runtime_id
                    runtime_id = generate_agent_conversation(source_id,source['context'],self.client,
                        name=source['name'],parent_id=parent_id,on_created=created,cancellation=self.cancellation)
                    self.cancellation.check()
                    mark_used(connection,source_id)
                log('scenario.mark_used.committed', conversation_id=runtime_id, source_conversation_id=source_id)
                completed.append({'conversation_id':runtime_id,'source_conversation_id':source_id})
                with self.lock:
                    self.accepting_continuation = False
                    if self.pending:
                        source_id,parent_id = self.pending
                        self.pending = None
                    else:
                        self.state = {'status':'completed',**completed[-1],'completed_conversations':completed}
                        break
        except Exception as error:
            with self.lock:
                self.accepting_continuation = False
                self.pending = None
                self.state = {'status':'failed','error':type(error).__name__,'source_conversation_id':source_id,
                              'completed_conversations':completed}
            log('simulation.failed', level=logging.ERROR, exc_info=True, source_conversation_id=source_id,
                completed_calls=len(completed))


def handler_for(simulator):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def respond(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/status":
                self.respond(200, simulator.status())
            else:
                self.respond(404, {"error": "not_found"})

        def do_POST(self):
            token = os.getenv('SERVER_TOKEN','')
            if not token or not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token):
                self.respond(401, {'error':'unauthorized'})
                return
            if self.path == '/maintenance/start':
                accepted = simulator.begin_maintenance()
                self.respond(200 if accepted else 409, {'status': 'maintenance' if accepted else 'busy'})
                return
            if self.path == '/maintenance/end':
                simulator.end_maintenance()
                self.respond(200, {'status': 'idle'})
                return
            if self.path not in ("/trigger", "/continue", "/cancel"):
                self.respond(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 4096 or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Unsupported request size or encoding")
                payload = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(payload, dict) or set(payload) - {"conversation_id", "parent_conversation_id"}:
                    raise ValueError("Expected an object with an optional conversation_id")
                source_id = payload.get("conversation_id")
                if source_id is not None:
                    source_id = str(UUID(str(source_id)))
            except (ValueError, UnicodeDecodeError, TimeoutError):
                self.respond(400, {"error": "invalid_trigger"})
                return
            if self.path == '/cancel':
                if source_id is None or payload.get('parent_conversation_id') is not None:
                    self.respond(400, {'error':'invalid_cancel'})
                    return
                self.respond(200, {'status':'cancelling' if simulator.cancel(source_id) else 'not_running'})
                return
            parent_id = payload.get('parent_conversation_id')
            try:
                if self.path == '/continue':
                    parent_id = str(UUID(str(parent_id)))
                    if source_id is None: raise ValueError()
                elif parent_id is not None: raise ValueError()
            except ValueError:
                self.respond(400, {'error':'invalid_parent'})
                return
            if (simulator.continue_call(source_id,parent_id) if self.path == '/continue' else simulator.trigger(source_id)):
                self.respond(202, {"status": "accepted"})
            else:
                self.respond(409, {"error": "simulation_in_progress"})

        def log_message(self, format, *args):
            LOG.info(format, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL") or not os.environ.get("SERVER_URL"):
        parser.error("Set DATABASE_URL and SERVER_URL before starting")
    server_url = os.environ["SERVER_URL"]
    if urlsplit(server_url).scheme not in ("http", "https") or not urlsplit(server_url).netloc:
        parser.error("SERVER_URL must be an HTTP(S) URL")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    configure("simulator")
    try:
        with connect() as connection:
            connection.execute("SELECT 1")
    except Exception as error:
        log("database.connect.failed", level=logging.ERROR, exc_info=True)
        parser.exit(1, f"Database connection failed ({type(error).__name__})\n")
    simulator = Simulator(ServerClient(server_url, os.environ.get("SERVER_TOKEN"), timeout=620))
    with ThreadingHTTPServer((args.host, args.port), handler_for(simulator)) as server:
        LOG.info("Waiting for POST /trigger on %s:%s", args.host, args.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            LOG.info("Stopping listener; waiting for the active simulation to finish")
    if simulator.worker:
        simulator.worker.join()


if __name__ == "__main__":
    main()
