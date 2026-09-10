# Local-model simulator

The background Python app waits for an authenticated trigger, selects an unused scenario, and alternates two separately prompted Qwen3 4B speakers. The assistant greets the caller and offers help. The other speaker acts as a patient, insurance representative, provider, or pharmacy. Generated turns stream to the server word by word.

## Run

From the repository root:

```sh
docker compose up --build -d
```

Compose starts Ollama and downloads `qwen3:4b` into the persistent `ollama_data` volume before starting the simulator. The model download is about 2.5 GB; inference needs additional memory. Docker uses CPU by default. The first model load and long prompts can take noticeably longer than subsequent turns. There is no cloud fallback. [Qwen model](https://ollama.com/library/qwen3/tags), [Ollama structured output API](https://docs.ollama.com/capabilities/structured-outputs).

For native Ollama acceleration on a Mac, install Ollama locally, run `ollama pull qwen3:4b`, set `OLLAMA_URL=http://host.docker.internal:11434` in `.env`, and recreate the server and simulator. Both services must use the same model endpoint. Native Ollama supports Apple GPU acceleration through Metal ([hardware support](https://docs.ollama.com/gpu)). After changing the endpoint, run `docker compose up -d --no-deps server simulator`. Compose's bundled Ollama remains available as the portable default.

| File | Responsibility |
| --- | --- |
| `main.py` | Trigger listener, serialized worker, maintenance reservation and follow-up queue |
| `database.py` | PostgreSQL connection |
| `randomize_conversation.py` | Select an unused scenario or a specific source |
| `local_model.py` | Local Ollama JSON generation with thinking disabled |
| `agent_conversation.py` | Separate speaker prompts, record/rule lookup, streaming and analysis dispatch |
| `generate_conversation.py` | Shared HTTP/event utilities; legacy replay function retained for protocol tests |

## Scenario context

`simulation.conversation.context` contains metadata links, an objective, counterpart role, situation, personality, and scenario background. It contains no scripted turns or expected-action answer key. Seed scripts preserve existing source IDs and usage. The legacy `next_conversation` links group the five original scenario families for the picker; the worker never follows them. Follow-ups reuse the same context source and receive a new objective/participant from the saved analysis. Every generated call has its own runtime ID and a unique optional `parent_conversation_id`.

## Call lifecycle

1. The server's authenticated practice simulation endpoint selects the source and calls simulator `POST /trigger`.
2. The worker creates the runtime record, fetches scoped patient/provider/health data and the current workflow checklist through `/agent-context`, and initializes separate role prompts. Patient prompts omit internal payer records and the assistant's checklist.
3. Speakers alternate. The assistant can submit observations through `/observations`; evidence must quote this call's transcript, action IDs must belong to the current rule, and field types, required values and branches are validated by the existing workflow engine. Accepted observations also create `kyron.action_executions` rows. These are simulation results, not calls to real external systems.
4. Speech ends with `conversation.ended`; the record remains processing, not completed. The worker calls `POST /api/conversations/{id}/analyze`.
5. The server runs the local model against the persisted transcript and workflow progress, stores the 1–3 sentence summary, sentiment, remaining work, proposed next call and metrics, commits, then reads that analysis to choose `stop`, `continue`, or `needs_review`.
6. For `continue`, `/dispatch` calls simulator `/continue`. The worker queues the next call, commits source usage, and runs it with the saved objective and participant. A child copies the parent's workflow checkpoint and observations. Duplicate child creation and dispatch are idempotent.
7. Terminal workflow outcomes stop. Missing evidence without a useful next contact, turn limits, and the four-call chain limit stop for review. Model/HTTP failures mark the runtime record failed and leave the current source transaction unconsumed. Failed calls are visible and are never labeled successful.

Model observations are not independent proof of clinical correctness. The backend verifies structure and transcript quotation, not semantic truth. Real prescribing, authorization submission, pharmacy dispensing and messaging integrations are outside this simulator.

## Configuration and endpoints

| Environment | Default |
| --- | --- |
| `OLLAMA_MODEL` | `qwen3:4b` |
| `OLLAMA_URL` | `http://ollama:11434` in Compose |
| `MODEL_TIMEOUT_SECONDS` | `300` per model response |
| `SIMULATION_MAX_TURNS` | `40` (bounded to 4–80) |
| `SIMULATION_WORD_SECONDS` | `0.08` |
| `SIMULATION_PAUSE_SECONDS` | `0.3` |

`SERVER_URL` points to the server's `/api`; `SERVER_TOKEN` is its simulator bearer token. The internal listener requires that same token for all POST requests. `POST /trigger` accepts `{ "conversation_id": "UUID" }`, or `{}` for random selection. `/continue` requires both source and parent IDs and is called by the server after analysis. `/status` reports idle/running/completed/failed/maintenance. State is in memory; database records and analyses persist. After a process restart, the internal `/dispatch` endpoint can retry a saved, undispatched continuation. A previously created child is never recreated automatically.

For faster playback, set `SIMULATION_WORD_SECONDS=0.04` and `SIMULATION_PAUSE_SECONDS=0.2` in `.env`; this changes playback pacing without changing model reasoning.

The worker reserves each source using `FOR NO KEY UPDATE SKIP LOCKED` until the call and its analysis finish. This is a deliberate long transaction for the local demo; idle transaction timeouts must accommodate model inference. Starting an unused source after an interrupted call creates a fresh runtime attempt. No automatic restart recovery for partially generated calls is implemented.

## Checks

```sh
python3 -m unittest discover -s simulator/tests -q
docker compose exec server python -m unittest discover -s server/tests -q
pnpm --dir client build
pnpm --dir client lint
```

Model doubles test stop/continue behavior, malformed output, word ordering and per-call transactions. PostgreSQL tests verify tenant isolation, evidence validation, analysis persistence, idempotent follow-ups and checkpoint continuity. Seed data creates supporting records and context scenarios only; it never creates runtime conversations.

## Speaker isolation and cancellation

`speaker.py` owns two independent agent histories: Emily (`ai_agent`) and the scenario's human role. Emily keeps structured action responses; the human keeps plain dialogue with Emily's latest utterance as the next user message. Opening scenario instructions are supplied only for the human's first reply. The model returns a fixed `speaker` field. Long copied utterances and known patient-identity adoption are rejected before streaming, with at most two corrective retries. Persistent violations fail the call rather than filling the transcript with repeated text.

The practice-scoped conversation Cancel button marks a live record failed and calls the simulator's authenticated `POST /cancel` with the runtime conversation ID. `cancellation.py` interrupts the current model socket, pauses, and word streaming. A cancelled call keeps its partial transcript, closes any open speaking turn, skips analysis/follow-up dispatch, and rolls back the source's used flag. Cancellation is scoped to the current runtime ID, so it cannot stop a different call.

For Qwen3, the model adapter explicitly closes the reasoning block before requesting structured output. This handles older model templates that open `<think>` even with `think: false`; without it, JSON-constrained reasoning can appear as repeated speech. Other model families retain their normal chat format.

Run the opt-in contact-question regression against native Ollama with `RUN_LOCAL_MODEL_TESTS=1 python3 -m unittest simulator.tests.test_local_human -q`. It uses fictional seed context and asserts the human answers Emily’s phone/pharmacy and identity questions across three runs; it does not write conversation records.

Both speakers aim to resolve a call in fewer than five replies each, with a target of ten messages total. Each turn receives the current reply count and call budget. This is a prompt goal; the default hard safety limit is 40 total messages per call, configurable via `SIMULATION_MAX_TURNS` (4–80). Hitting the hard limit still runs analysis and records the turn-limit condition; the model must not skip required checks to meet the target.

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
