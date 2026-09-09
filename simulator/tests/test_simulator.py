import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from simulator.generate_conversation import ServerClient, generate_conversation
from simulator.main import Simulator, handler_for


EXAMPLE = Path(__file__).resolve().parents[1] / "example_conversation.json"


class Transaction:
    """Small transaction double, including rollback of an uncommitted used flag."""

    def __init__(self, payload):
        self.source = {"conversation_id": uuid4(), "transcript": payload}
        self.used = False
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        self.committed = error_type is None
        self.rolled_back = error_type is not None
        if self.rolled_back:
            self.used = False

    def execute(self, sql, params=None):
        if sql.strip().startswith("UPDATE"):
            self.used = True
        return self

    def fetchone(self):
        return None if self.used else self.source


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(EXAMPLE.read_text())
        self.requests = []
        self.runtime_id = str(uuid4())
        self.fail_words = False
        test = self

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.requests.append((self.path, payload))
                status = 503 if test.fail_words and payload.get("type") == "transcript.word" else 200
                body = json.dumps({"id": test.runtime_id}).encode() if self.path == "/conversations" else b""
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.client = ServerClient(f"http://127.0.0.1:{self.server.server_port}")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_metadata_words_pauses_actions_and_completion(self):
        self.payload["turns"][0]["transcript"] = "  Hello,\tthere!  "
        self.payload["ground_truth"] = {"future_decision": "denied"}
        pauses = []
        result = generate_conversation(uuid4(), self.payload, self.client, sleep=pauses.append)
        self.assertEqual(result, self.runtime_id)
        self.assertEqual(self.requests[0][0], "/conversations")
        self.assertNotIn("turns", self.requests[0][1])
        self.assertNotIn("ground_truth", self.requests[0][1])
        self.assertEqual(self.requests[0][1]["practice_id"], self.payload["metadata"]["practice_id"])
        events = [payload for _, payload in self.requests[1:]]
        self.assertEqual([e["sequence"] for e in events], list(range(1, len(events) + 1)))
        starts = [e for e in events if e["type"] == "transcript.started"]
        for turn, start in zip(self.payload["turns"], starts):
            reconstructed = "".join(e["delta"] for e in events
                                    if e["type"] == "transcript.word"
                                    and e["transcript_id"] == start["transcript_id"])
            self.assertEqual(reconstructed, turn["transcript"])
        actions = [i for i, e in enumerate(events) if e["type"] == "action.simulated"]
        self.assertEqual(events[actions[0] - 1]["word_index"], 6)
        self.assertEqual(events[actions[0]]["transcript_id"], starts[1]["transcript_id"])
        self.assertEqual(events[actions[1] - 1]["type"], "conversation.ended")
        self.assertIsNone(events[actions[1]]["transcript_id"])
        self.assertEqual(events[-1]["type"], "replay.completed")
        self.assertEqual(pauses[:3], [0.3, 0.18, 0.18])
        self.assertIn(0.8, pauses)

    def test_invalid_later_turn_fails_before_any_server_request(self):
        for bad_value in (float("nan"), -1, True, "slow"):
            with self.subTest(bad_value=bad_value):
                payload = copy.deepcopy(self.payload)
                payload["turns"][1]["word_delay_ms"] = bad_value
                with self.assertRaises(ValueError):
                    generate_conversation(uuid4(), payload, self.client, sleep=lambda _: None)
        self.payload["turns"][1]["action"]["after_word"] = 1000
        with self.assertRaises(ValueError):
            generate_conversation(uuid4(), self.payload, self.client)
        self.assertEqual(self.requests, [])

    def test_success_commits_used_and_next_trigger_is_empty(self):
        for turn in self.payload["turns"]:
            turn.update(pause_before_ms=0, word_delay_ms=0)
        transaction = Transaction(self.payload)
        app = Simulator(self.client, lambda: transaction)
        app.run(None)
        self.assertTrue(transaction.committed)
        self.assertTrue(transaction.used)
        self.assertEqual(app.status()["status"], "completed")
        app.run(None)
        self.assertEqual(app.status()["status"], "empty")

    def test_http_failure_rolls_back_and_does_not_emit_completion(self):
        self.fail_words = True
        for turn in self.payload["turns"]:
            turn.update(pause_before_ms=0, word_delay_ms=0)
        transaction = Transaction(self.payload)
        app = Simulator(self.client, lambda: transaction)
        app.run(None)
        self.assertTrue(transaction.rolled_back)
        self.assertFalse(transaction.used)
        self.assertEqual(app.status()["status"], "failed")
        self.assertFalse(any(body.get("type") == "replay.completed" for _, body in self.requests))

    def test_trigger_is_async_rejects_overlap_and_validates_input(self):
        entered = threading.Event()
        release = threading.Event()
        transaction = Transaction(self.payload)
        app = Simulator(self.client, lambda: transaction)

        def replay(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release worker")
            return self.runtime_id

        listener = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(app))
        thread = threading.Thread(target=listener.serve_forever)
        thread.start()
        base = f"http://127.0.0.1:{listener.server_port}"
        try:
            with patch("simulator.main.generate_conversation", side_effect=replay):
                with urlopen(Request(base + "/trigger", data=b"{}")) as response:
                    self.assertEqual(response.status, 202)
                self.assertTrue(entered.wait(2))
                with urlopen(base + "/status") as response:
                    self.assertEqual(json.load(response)["status"], "running")
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + "/trigger", data=b"{}"))
                self.assertEqual(error.exception.code, 409)
                error.exception.close()
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + "/trigger", data=b'{"conversation_id":"invalid"}'))
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
                release.set()
                app.worker.join(3)
                self.assertEqual(app.status()["status"], "completed")
        finally:
            release.set()
            listener.shutdown()
            listener.server_close()
            thread.join()
            if app.worker:
                app.worker.join(3)

    def test_linked_conversations_commit_individually_in_order(self):
        first, second = Transaction(self.payload), Transaction(self.payload)
        first.source["next_conversation"] = second.source["conversation_id"]
        connections = iter([first, second])
        app = Simulator(self.client, lambda: next(connections))
        with patch("simulator.main.generate_conversation", return_value=self.runtime_id) as replay:
            app.run(None)
        self.assertEqual([call.args[0] for call in replay.call_args_list],
                         [first.source["conversation_id"], second.source["conversation_id"]])
        self.assertTrue(first.committed and second.committed)
        self.assertTrue(first.used and second.used)
        self.assertEqual(len(app.status()["completed_conversations"]), 2)

    def test_failed_follow_up_preserves_completed_first_call(self):
        first, second = Transaction(self.payload), Transaction(self.payload)
        first.source["next_conversation"] = second.source["conversation_id"]
        connections = iter([first, second])
        app = Simulator(self.client, lambda: next(connections))
        with patch("simulator.main.generate_conversation", side_effect=[self.runtime_id, ValueError("bad source")]):
            app.run(None)
        self.assertTrue(first.used)
        self.assertFalse(second.used)
        self.assertTrue(second.rolled_back)
        self.assertEqual(app.status()["status"], "failed")
        self.assertEqual(len(app.status()["completed_conversations"]), 1)

    def test_cycle_is_stopped(self):
        first, second = Transaction(self.payload), Transaction(self.payload)
        first.source["next_conversation"] = second.source["conversation_id"]
        second.source["next_conversation"] = first.source["conversation_id"]
        repeated = Transaction(self.payload)
        repeated.source = first.source
        connections = iter([first, second, repeated])
        app = Simulator(self.client, lambda: next(connections))
        with patch("simulator.main.generate_conversation", return_value=self.runtime_id) as replay:
            app.run(None)
        self.assertEqual(replay.call_count, 2)
        self.assertEqual(app.status()["error"], "ValueError")


if __name__ == "__main__":
    unittest.main()
