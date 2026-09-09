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
| `GET /api/simulations` | Five scenario starting points and their used flags. |
| `POST /api/simulations/random` | Trigger one random unused scenario chain. |
| `POST /api/simulations/{conversation_id}/run` | Trigger a specific unused call and its successors. |
| `GET /api/simulations/status` | Current simulator state, active source, completed calls, or failure. |
| `POST /api/conversations` | Receive metadata and create a runtime conversation and analysis. |
| `POST /api/conversations/{id}/events` | Persist ordered word, turn, action, and completion events. |
| `GET /api/events` | Stream persisted events to the browser using SSE. |

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

Source rows live in [data/conversations.json](data/conversations.json). Each has a stable `conversation_id`, `name`, JSONB `transcript`, and nullable `next_conversation` UUID. The latter is the canonical link, rather than a duplicate pointer embedded inside transcript JSON. Seed validation rejects missing links and cycles. `ground_truth` is retained only in the source payload and never sent to the browser.

Startup creates the schemas and the tables needed by this replay slice, then inserts missing seed records. It preserves existing records and `is_used` flags, including across container rebuilds. Context models implement only the fields needed for this initial flow; the wider clinical and insurance tables in the root README remain outside this implementation. `create_all` bootstraps a fresh database; it is not a migration engine for older schemas.

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
