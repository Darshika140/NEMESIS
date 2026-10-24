# NEMESIS diagnostic and healing services

The dashboard chat and instruction-healing endpoints use stateless request
context. They do not store chat history, embeddings, or vector indexes. The
frontend sends the current run/scenario JSON on each diagnostic request.

## Local Windows setup

Install the backend dependencies and start the API from the repository root:

```powershell
python -m pip install -e .
python -m uvicorn nemesis.api.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The API defaults to `http://127.0.0.1:8000`; the frontend defaults to that same
base URL. Set `VITE_API_BASE_URL` in `frontend/.env` when the API is elsewhere.
Set `NEMESIS_CORS_ORIGINS` to a comma-separated allowlist if the frontend origin
differs from `localhost:5173` and `127.0.0.1:5173`.

## Inference providers

The provider switch routes `/api/chat` and `/api/heal` requests to one of:

- **Cloud / Groq:** Uses the Groq SDK and `GROQ_API_KEY`. The default model is
  `openai/gpt-oss-20b` hosted by Groq. Agent review uses separately configured
  Fixer and Red Team models (`NEMESIS_GROQ_FIXER_MODEL` and
  `NEMESIS_GROQ_RED_TEAM_MODEL`) so adjudication is not performed by the same
  model. Confirm both model IDs are available to your Groq account. Groq's
  developer access/quota is subject to Groq's current terms and limits; cloud
  use is not guaranteed to remain free.
- **Local / Ollama:** Uses only the Ollama HTTP endpoint on the backend machine.
  The default is `gemma4:e2b`, matching the model tag installed locally. Confirm
  model tags with `ollama list`; if needed, run `ollama pull gemma4:e2b`.
  Configure
  `NEMESIS_OLLAMA_MODEL` if needed. Local mode rejects non-loopback Ollama URLs,
  makes no Groq fallback, and uses the configured local model for both roles.
  The default
  `gemma4:e2b` tag is 7.2 GB on this development machine.

Put `GROQ_API_KEY` in `.secrets/.env` or the backend process environment. API
credentials are never sent to the browser or included in API response bodies.
Choose **Local** to avoid sending diagnostic context to a cloud provider.

## Endpoints

- `POST /api/chat`: `{ "message": "...", "execution_logs": {}, "provider": "groq" }`.
  Responses are JSON with `answer`, evidence citations, `insufficient_data`,
  `provider`, and `model`. The service validates each citation path and quote
  against the supplied JSON. Unsupported citations yield an insufficient-data
  response.
- `POST /api/heal`: accepts an instruction, failure evidence, test cases, a
  provider, and a bounded review-iteration count. The Fixer proposes instruction
  text; a distinct Red Team adjudicator evaluates only supplied regression cases
  and returns high-level findings, not generated jailbreak payloads.
- `POST /api/heal/stream`: streams completed Fixer and Red Team turns as
  server-sent events for the Agent Boardroom UI.
- `POST /api/audits`: extracts recorded unsupported claims into strict,
  timestamped JSON compliance records. Because the pipeline does not currently
  persist its generator model ID, `model_version` is honestly reported as
  `not_recorded`. Audit creation is deterministic and does not ask an LLM to
  invent a reason.
- A proposal is marked `verified` only when the Red Team model approves it. This
  is an LLM review, not execution of tests or a proof of correctness, and it
  does not edit project files.
- `POST /api/run`: starts the pipeline. Use `live_llm` for Groq,
  `local_llm` for loopback-only Ollama, or `mock_llm` for offline deterministic
  execution. The dashboard selects `local_llm` automatically when Local is
  active; every pipeline inference call (scenario generation, agent steps, and
  model-backed checking) uses the selected provider.

For a no-network API smoke test, call `/api/run` with
`{ "mode": "mock_llm", "n_scenarios": 1 }`.

## Operational boundaries

The diagnostic assistant is not given server-side filesystem access. It sees
only the JSON included in the current request and must cite evidence from that
payload. Requests are size-limited by the API schema. Protect the API with
authentication, rate limiting, and TLS before making it reachable outside a
trusted local development environment.
