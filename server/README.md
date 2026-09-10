# FastAPI server

Run the full stack from the repository root:

```sh
docker compose up --build -d --wait
```

Open [http://localhost:5173](http://localhost:5173), choose a practice, and sign in as **taylor.demo** with password **password**. The React client currently provides authentication and a protected practice landing page. The simulation and SSE APIs remain available to the authenticated practice; the legacy static demo page is no longer served.

FastAPI and the Vite client are exposed on loopback ports 8000 and 5173. PostgreSQL and the simulator communicate on Compose's internal network. Set `SERVER_PORT=8001` before starting Compose if port 8000 is occupied. The credentials in Compose are for this local demo.

## Structure

```text
server/
  core/            configuration, database sessions, startup seed
  models/          SQLAlchemy persistence models
  schemas/         validated request and event contracts
  app/
    main.py        lifespan, routes, static page
    api/           auth, conversations, simulations, SSE
    services/      JWT login and tenant authorization
    crud/          persistence and event ordering
    static/        legacy demo assets (not served)
  data/            fictional context and linked source conversations
  tests/           PostgreSQL-backed API tests
```

## Endpoints

| Method / path | Behavior |
| --- | --- |
| `GET /` | Redirect to the React provider portal. |
| `GET /health` | PostgreSQL connectivity check. |
| `GET /docs` | Interactive OpenAPI documentation. |
| `GET /api/practices/{practice}/simulations` | Five scenario starting points and their used flags. |
| `POST /api/practices/{practice}/simulations/random` | Generate a call from a random unused scenario. |
| `POST /api/practices/{practice}/simulations/{conversation_id}/run` | Generate a call from the chosen context scenario. |
| `GET /api/practices/{practice}/simulations/status` | Current simulator state, active source, completed calls, or failure. |
| `POST /api/conversations` | Receive metadata and create a runtime conversation and analysis. |
| `POST /api/conversations/{id}/events` | Persist ordered word, turn, action, and completion events. |
| `GET /api/practices/{practice}/events` | Stream persisted events to the browser using SSE. |

The simulator uses `SERVER_URL=http://server:8000/api`; the API forwards triggers to `http://simulator:8090`. Triggering returns `202`; another active replay returns `409`. Used specific calls return `409`. An exhausted random selection returns `409`.

## Seed scenarios

| Scenario | Insurer outcome / follow-up |
| --- | --- |
| Routine refill | Approval reference, followed by a patient update. |
| Missing records | Pending documentation, routed to the practice. |
| Authorization denied | Decision and review reference, routed to the clinician. |
| Coverage mismatch | Member information needed before review can proceed. |
| Time-sensitive refill | Expedited-review requirements; the call ends before a decision. |

Each scenario has three source rows: patient request, insurer call, and patient callback. Insurer calls follow the supplied example's introduction, callback details, provider identification, patient/member verification, questions, and confirmation. Identifiers and decisions are fictional. No real calls, claims, or clinical decisions are performed.

Source rows live in [data/conversations.json](data/conversations.json). Each has a stable `conversation_id`, `name`, JSONB `context`, and nullable `next_conversation` UUID. The legacy pointer groups the original scenario families for selection; generated follow-up calls use persisted analysis instead. Context includes objective, role and personality, with no scripted turns or ground-truth transcript. Seed validation checks context links.

Startup creates the application schemas and seeds supporting records while preserving runtime history and `is_used` flags. An explicit upgrade renames simulation `transcript` to `context`, adds nullable analysis/parent fields and preserves existing IDs. These demo upgrades are not a general migration framework.

## Persistence and failure handling

The simulator locks one source at a time using `FOR NO KEY UPDATE SKIP LOCKED`. This prevents duplicate workers while allowing the receiving server to reference that source through a foreign key. Completed calls are committed individually. If a later call fails, earlier calls stay used and the failing source remains unused; its UUID is returned in status so it can be retried specifically.

The API persists the event and its derived table changes in one transaction. Duplicate identical sequence numbers are acknowledged without appending duplicate words; conflicting duplicates and out-of-order events are rejected. Practice/patient/prescription links are checked on creation. Transcript and action IDs cannot be used across conversations.

The event log is serialized through commit so SSE cursor IDs cannot skip uncommitted events. SSE reads short batches from PostgreSQL every 200 ms, releases the session between reads, and sends keepalives. The server records simulated actions but does not perform LLM analysis or execute those actions.

If the simulator fails after the server has accepted part of a call, that partial runtime conversation remains visible. Retrying creates a new runtime conversation; automatic request retries and reset endpoints are not implemented.

## Development and checks

```sh
docker compose logs -f server simulator
docker compose exec server python -m unittest discover -s server/tests -v
docker compose exec simulator python -m unittest discover -s simulator/tests -v
docker compose down
```

Tests roll back their runtime records. The Compose volume retains seeded and runtime data when services stop. A fresh volume receives the seed automatically.

Browser checks cover practice selection, login, automatic session restoration, cross-practice rejection, logout, and a narrow viewport. The underlying replay was previously verified end to end with all three linked calls.

Implementation references: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [SQLAlchemy declarative models](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html), [Compose health dependencies](https://docs.docker.com/compose/how-tos/startup-order/).

## Provider authentication

The React client at **http://localhost:5173** is now the entry point; `GET /` redirects there. Choose a practice, then sign in at `/{practice}/auth`. The initial protected page displays the provider and practice with a sign-out button.

Credentials follow the requested demo convention: `lower(firstname.lastname)` and password **password**. The seed provider is **taylor.demo** at both Harbor Family Practice and Cedar Primary Care. Login verifies the `providers.provider_practice` affiliation. Practice slugs are derived from their names; ambiguous or unknown slugs are rejected.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/practices` | Public practice dropdown. |
| `GET /api/practices/{practice}` | Public practice name and slug. |
| `POST /api/practices/{practice}/auth/login` | JSON `{username, password}`; sets session cookie. |
| `GET /api/practices/{practice}/auth/me` | Verify cookie, provider membership, and selected practice. |
| `POST /api/practices/{practice}/auth/logout` | Delete the session cookie, including if expired. |

The `kyron_session` cookie is HttpOnly, SameSite=Lax, and expires after eight hours. It contains an HS256 JWT with provider ID, practice ID, issuer, audience, and expiry. No token is returned in the JSON response. Set `COOKIE_SECURE=true` when serving over HTTPS. Logout deletes the browser cookie; this simple stateless implementation does not keep a token revocation list or refresh tokens.

Simulation and SSE routes now live under `/api/practices/{practice}` and require the matching cookie. Queries filter by practice, specific triggers validate the entire linked call chain, and status does not expose another practice’s call details. Old unscoped read/trigger endpoints are removed. Ingestion at `/api/conversations` requires the separate simulator bearer token, which is configured only on the server and simulator.

Compose reads `JWT_SECRET` and `SIMULATOR_TOKEN` from the gitignored root `.env`. They have been generated for this workspace. On a new checkout, generate them once before starting Compose:

```sh
python3 - <<'PY'
from pathlib import Path
import secrets
path = Path('.env')
if not path.exists():
    path.write_text(''.join(f'{name}={secrets.token_urlsafe(48)}\n' for name in ('JWT_SECRET', 'SIMULATOR_TOKEN')))
    path.chmod(0o600)
PY
```

For a server outside Compose, export these variables and set the simulator's `SERVER_TOKEN` to the same value as `SIMULATOR_TOKEN`. `CLIENT_URL` defaults to `http://localhost:5173` and allows that origin for cookie-authenticated POSTs. Without `JWT_SECRET`, a standalone server generates a process-local key, so restarts invalidate sessions.

References: [FastAPI cookies](https://fastapi.tiangolo.com/advanced/response-cookies/) and [JWT validation](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).

### Demo controls

Authenticated `POST /api/practices/{practice}/demo/seed` invokes `/workspace/seed_data.py` (180-second timeout). `POST .../demo/clear` atomically deletes all Kyron conversation/event/transcript/analysis/action-execution and workflow-run rows, nulls insurance authorization action references, and sets all simulation sources to unused. Both are global local-demo operations, require a valid practice session and allowed origin, and reserve the simulator through its internal maintenance endpoints to prevent concurrent replay. The UI labels clear's global scope. Simulator ingress remains internal to Compose.

Workflow definitions and observation APIs are documented in the root [workflow design](../README.md#prescription-workflows-rules-and-actions). Clear preserves reusable actions, rules, and workflows.

## Local-model lifecycle

The simulator uses local Qwen3 4B via Ollama. Internal bearer-token endpoints are `POST /api/conversations/{id}/agent-context`, `/observations`, `/analyze`, `/dispatch`, and `/failed`. Analysis reads persisted transcript/observations, saves summary/sentiment/outstanding work/metrics, commits, and then decides continuation from the saved row. `/dispatch` starts the next call through simulator `/continue`. Calls preserve workflow checkpoints and use unique parent links for idempotency.

`GET /api/practices/{practice}/conversations/{id}/actions` provides the workflow definition, observations, completed path and analysis, scoped to the authenticated practice. `conversation.finalized` SSE events carry the terminal or follow-up status. The legacy `replay.completed` event is retained for existing protocol clients; the model simulator never uses it to bypass analysis. See [simulator setup](../simulator/README.md).

`POST /api/practices/{practice}/conversations/{id}/cancel` requires the matching practice session and an allowed origin. It accepts live calls (or retries against an already failed record), persists `failed` with `cancelled_by_user`, closes partial turns, then signals the simulator. Late transcript writes and observations are rejected. A late analysis response cannot overwrite a failed status. The endpoint preserves the stop even if the simulator is temporarily unavailable.

### Debugging calls

Follow both services with `docker compose logs -f --tail=200 server simulator`.
Structured JSON events include conversation/source IDs, stage, speaker, turn index,
retry attempt, HTTP request ID/status, timings, and model token counts when available.
`conversation.ending` distinguishes `agent_end_call` from `turn_limit`.
`speaker.response.rejected` identifies invalid/repeated speech and exhausted retries;
`model.request.failed`, `analysis.failed`, and `simulation.failed` include exception
classes and traceback frame locations. Analysis validation logs identify failing fields.

`LOG_LEVEL` defaults to `INFO`. Set `LOG_LEVEL=DEBUG` in the top-level `.env` and
recreate the services between calls with `docker compose up -d --no-deps --force-recreate server simulator`
to include individual word-delivery requests and polling. Debug events contain operational
metadata, not word content. Prompts, transcripts, patient records, credentials, HTTP bodies,
and arbitrary exception messages are excluded. Stack frames and explicit validation reasons
remain available. `X-Request-ID` connects a simulator HTTP request to its server logs and is
returned in server responses. These logs diagnose new runs; they cannot reconstruct errors
from earlier runs that only saved a generic failure.

### Intake, routing, and simulated actions

New initial calls use the `patient_intake` workflow: identity → reason → proposed next steps.
After the call, analysis summarizes the transcript, assesses sentiment, recovers missing intake
results from cited transcript turn indices (resolved to the original text), and independently selects a workflow from the catalog.
The seeded prescription cases are expected to match `new_prescription`; that expectation is used
only for the evaluation metric and is never sent to the analyzer.

`kyron.action_tasks` stores each selected log, notification, message, or call, its status, and its
simulated receipt. Analysis and plans commit before execution/continuation decisions. Local deliveries
produce simulated receipts; they never send real messages. Calls are queued serially and link to the
resulting conversation. Reanalysis reuses the same logical tasks and preserves completed deliveries.
Required intake and existing call/turn safety limits can block a task, with the reason recorded.

`POST /api/practices/{practice}/conversations/{id}/analyze` reruns analysis on an ended transcript with
provider cookie authentication and origin checks, then processes the saved plan and dispatches any
eligible follow-up. Live, empty, and cancelled conversations are rejected. The Evaluation tab exposes this
operation; the Actions tab keeps polling while open, including after the original call finishes.

The Ollama adapter inlines schema references and removes string-size/format constraints unsupported
by its grammar compiler; Pydantic still validates the full output. Analysis has a larger output budget
and at most three structured-output attempts. Invalid output remains an explicit failure, never a
fabricated successful analysis.
