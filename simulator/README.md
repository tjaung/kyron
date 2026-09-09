# Simulator

A background Python app that waits for an HTTP trigger and replays a stored conversation and its linked follow-up calls to the Kyron server. Run it from the repository root; there is no package build or installation step.

| File | Responsibility |
| --- | --- |
| `main.py` | Trigger listener, background worker, and replay status. |
| `database.py` | PostgreSQL connection configuration. |
| `randomize_conversation.py` | Random starting-call selection, specific-ID lookup, and marking completed sources used. |
| `generate_conversation.py` | Validate source JSON, create a conversation, and stream timed events. |

## Run

The full stack runs with `docker compose up --build -d --wait` from the repository root. Open [localhost:5173](http://localhost:5173) for provider login. Simulation APIs are now practice-scoped; see [server authentication](../server/README.md#provider-authentication). Compose seeds five scenarios, each with three linked calls.

For running this app outside Docker, use Python 3.10+ and PostgreSQL. The FastAPI server in `server/` implements the contract below.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r simulator/requirements.txt
export DATABASE_URL='postgresql://user:password@localhost:5432/kyron'
export SERVER_URL='http://localhost:8000/api'
psql "$DATABASE_URL" -f simulator/schema.sql
```

`schema.sql` creates only `simulation.conversation`. It does not change an existing text column to JSONB or create the application's other schemas. Practice and patient links must already exist on the receiving server. Update the placeholder IDs in `simulator/example_conversation.json` to match them; nullable patient registration and prescription links can be omitted.

Load the example as an unused source:

```sh
python - <<'PY'
import json
from pathlib import Path
from uuid import uuid4
from psycopg.types.json import Jsonb
from simulator.database import connect

with connect() as connection:
    connection.execute(
        "INSERT INTO simulation.conversation (conversation_id, name, transcript) VALUES (%s, %s, %s)",
        (uuid4(), "Example prescription call", Jsonb(json.loads(Path('simulator/example_conversation.json').read_text()))),
    )
PY
python -m simulator.main
```

The listener defaults to `127.0.0.1:8090`; use `--host` and `--port` to configure it. It is an internal trigger listener with no authentication. `SERVER_TOKEN` is sent as a bearer token to the receiving server and must match the server’s `SIMULATOR_TOKEN`. Compose configures both from the root `.env`. Environment variables are read directly; `.env` files are not loaded automatically.

From another terminal or the server:

```sh
curl -X POST http://localhost:8090/trigger
curl http://localhost:8090/status
```

To select a specific unused source, send `{"conversation_id":"<source UUID>"}` as the trigger's JSON body. The trigger runs that call and follows its `next_conversation` links. A trigger returns `202` immediately, or `409` when a replay is already running. Invalid bodies return `400`. Status is `idle`, `running`, `completed`, `empty` (no matching unlocked unused row), or `failed`. Status includes `completed_conversations`; while running it also includes the current name and source ID. Completed status includes the final source and runtime IDs. Failure status identifies the source that needs attention. Status is in memory and resets when the app restarts.

## Source JSON

Each source row has `conversation_id`, required `name`, JSONB `transcript`, `is_used`, and nullable `next_conversation`. `next_conversation` is a foreign key to another source row; null ends the chain. Random selection excludes rows referenced as a next conversation. The `get_conversation` function retrieves a specific unused row for explicit triggers and chain traversal.

The `transcript` column stores a JSONB object. [example_conversation.json](example_conversation.json) is a complete example.

| Field | Meaning |
| --- | --- |
| `metadata.practice_id` | Required practice UUID. |
| `metadata.patient_practice_id`, `metadata.prescription_id` | Nullable linked UUIDs. |
| `turns` | Nonempty array, replayed in array order. |
| `turns[].speaker`, `turns[].transcript` | Required nonempty text. |
| `turns[].pause_before_ms` | Pause before the turn; defaults to 600 ms. |
| `turns[].word_delay_ms` | Delay before each word; defaults to 150 ms. |
| `turns[].action` | Nullable object with `action`, `reason`, and optional `after_word`. |
| `after_call_actions` | Array of `{action, reason}` objects; defaults to empty. |

`after_word` is a one-based word position; it defaults to the turn's last word. Delays must be finite numbers from 0 to 60,000 ms. Set them to zero for a fast replay. Words preserve their surrounding whitespace, so concatenated `delta` values reconstruct the original turn exactly. Extra top-level fields can hold evaluation ground truth; the simulator does not forward them.

## Receiving server contract

The server implementation is the FastAPI app in `server/`. `SERVER_URL` can include an API path prefix. Requests are sequential JSON POSTs with a 15-second timeout; successful event responses can be empty or JSON.

1. `POST /conversations` receives `{practice_id, patient_practice_id, prescription_id, source_conversation_id, start_time, name}`. The server validates the links, creates `kyron.conversation_record` and its analysis, and returns `{"id":"<runtime conversation UUID>"}`. Source ID is a foreign key to `simulation.conversation`, distinct from the runtime primary key.
2. `POST /conversations/{id}/events` receives the events below. Every event has `type`, a one-based increasing `sequence`, and UTC `occurred_at`.

| Event | Additional fields / server behavior |
| --- | --- |
| `transcript.started` | `transcript_id`, zero-based `turn_index`, `speaker`; create a turn with its start time. |
| `transcript.word` | `transcript_id`, one-based `word_index`, `delta`; append the text. |
| `action.simulated` | `action_id`, nullable `transcript_id`, `action`, `reason`, `simulated: true`; record a scripted action associated with the conversation's analysis. |
| `transcript.completed` | `transcript_id`; set the turn's end time. |
| `conversation.ended` | Set the call's end time; post-call actions follow. |
| `replay.completed` | All turns and post-call actions have been sent. |

Only metadata is sent when creating the call. Transcript text and actions arrive at their scheduled point. Scripted actions are simulation events, not instructions for the simulator to call insurers or execute tools, and do not imply `is_completed = true` in the action table. The server can forward accepted events to its frontend through SSE.

## Selection and failures

The worker selects unused starting rows with `ORDER BY random() LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED`. It holds the database transaction throughout one call, then sets `is_used = true` and commits before selecting the next linked call. Other workers skip the locked row, while the server can still insert a foreign key pointing to it. Repeated IDs and chains over 100 calls are rejected. This deliberately uses a long transaction for a small simulation dataset; database idle-transaction timeouts must accommodate the replay duration. [PostgreSQL locking behavior](https://www.postgresql.org/docs/current/sql-select.html).

Validation happens before server creation. A failed validation or HTTP request stops the chain and rolls back only the current call’s transaction. Previously completed calls remain used. An unavailable linked row reports failure; trigger that specific unused source to resume after resolving the issue. The app remains available for another trigger. Requests are not retried automatically: the server may already contain a partial conversation, and replaying the unused source creates a new runtime conversation. A server success followed by a database commit failure can also leave a source unused. Resetting or reconciling those runtime records belongs to the server. [Psycopg transaction behavior](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

Ctrl-C stops the listener and waits for an active replay to finish. There is no trigger queue, automatic polling, or reset endpoint in this app.

## Tests

```sh
python -m unittest discover -s simulator/tests -v
```

Tests exercise paced replay and trigger handling against a local HTTP receiver, plus per-call commits, linked-call failures, and cycle detection with database test doubles. PostgreSQL-backed API tests run in the server container; see [server checks](../server/README.md#development-and-checks).
