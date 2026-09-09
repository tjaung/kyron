"""Local background app: accept a trigger, replay once, then wait again."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import threading
from urllib.parse import urlsplit
from uuid import UUID

from .database import connect
from .generate_conversation import ServerClient, generate_conversation
from .randomize_conversation import get_conversation, mark_used, randomize_conversation

LOG = logging.getLogger("simulator")


class Simulator:
    def __init__(self, client, connection_factory=connect):
        self.client = client
        self.connection_factory = connection_factory
        self.lock = threading.Lock()
        self.state = {"status": "idle"}
        self.worker = None

    def status(self):
        with self.lock:
            return self.state.copy()

    def trigger(self, conversation_id=None):
        with self.lock:
            if self.state["status"] == "running":
                return False
            self.state = {"status": "running"}
            self.worker = threading.Thread(target=self.run, args=(conversation_id,))
            self.worker.start()
        return True

    def run(self, conversation_id):
        completed = []
        visited = set()
        source_id = conversation_id
        try:
            # Keep the row lock until every event is acknowledged. Exceptions
            # roll back the transaction, leaving the source unused.
            while True:
                if source_id is not None and str(source_id) in visited:
                    raise ValueError("Conversation chain contains a cycle")
                with self.connection_factory() as connection:
                    source = (randomize_conversation(connection) if source_id is None
                              else get_conversation(connection, source_id))
                    if source is None:
                        if completed:
                            raise LookupError("Follow-up conversation is unavailable")
                        result = {"status": "empty", "completed_conversations": []}
                        break
                    source_id = str(source["conversation_id"])
                    if source_id in visited or len(visited) >= 100:
                        raise ValueError("Conversation chain contains a cycle or is too long")
                    visited.add(source_id)
                    with self.lock:
                        self.state = {"status": "running", "source_conversation_id": source_id,
                                      "name": source.get("name"),
                                      "completed_conversations": completed.copy()}
                    runtime_id = generate_conversation(
                        source["conversation_id"], source["transcript"], self.client,
                        name=source.get("name"),
                    )
                    mark_used(connection, source["conversation_id"])
                    next_id = source.get("next_conversation")
                # Record completion only after the per-call transaction commits.
                completed.append({"conversation_id": runtime_id,
                                  "source_conversation_id": source_id})
                if next_id is None:
                    result = {"status": "completed", **completed[-1],
                              "completed_conversations": completed.copy()}
                    break
                source_id = str(next_id)
            LOG.info("Replay result: %s", result["status"])
        except Exception as error:
            # Do not log patient payloads, server response bodies, or DB credentials.
            result = {"status": "failed", "error": type(error).__name__,
                      "source_conversation_id": source_id,
                      "completed_conversations": completed.copy()}
            LOG.error("Replay failed (%s); source remains unused", type(error).__name__)
        with self.lock:
            self.state = result


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
            if self.path != "/trigger":
                self.respond(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 4096 or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Unsupported request size or encoding")
                payload = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(payload, dict) or set(payload) - {"conversation_id"}:
                    raise ValueError("Expected an object with an optional conversation_id")
                source_id = payload.get("conversation_id")
                if source_id is not None:
                    source_id = str(UUID(str(source_id)))
            except (ValueError, UnicodeDecodeError, TimeoutError):
                self.respond(400, {"error": "invalid_trigger"})
                return
            if simulator.trigger(source_id):
                self.respond(202, {"status": "accepted"})
            else:
                self.respond(409, {"error": "replay_in_progress"})

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
    try:
        with connect() as connection:
            connection.execute("SELECT 1")
    except Exception as error:
        parser.exit(1, f"Database connection failed ({type(error).__name__})\n")
    simulator = Simulator(ServerClient(server_url, os.environ.get("SERVER_TOKEN")))
    with ThreadingHTTPServer((args.host, args.port), handler_for(simulator)) as server:
        LOG.info("Waiting for POST /trigger on %s:%s", args.host, args.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            LOG.info("Stopping listener; waiting for the active replay to finish")
    if simulator.worker:
        simulator.worker.join()


if __name__ == "__main__":
    main()
