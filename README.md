# NEMESIS

**Find unsupported AI claims, review defensive fixes, and keep sensitive inference on your own machine.**

[![License: not specified](https://img.shields.io/badge/license-not%20specified-lightgrey.svg)](#project-status)
[![CI: not configured](https://img.shields.io/badge/CI-not%20configured-lightgrey.svg)](#project-status)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

## What is NEMESIS?

NEMESIS is an experimental AI security and LLMOps platform for exercising AI-agent workflows, surfacing failures such as unsupported success claims, and reviewing proposed defensive instructions against supplied evidence and regression cases.

The React dashboard presents pipeline metrics, scenario traces, claim differences, audit records, and a streamed multi-agent review. A FastAPI service coordinates pipeline execution and routes inference to Groq or a loopback-only Ollama service. NEMESIS is a hackathon and development project; it is not a certified security product or an autonomous production patching system.

## Key features

- **Multi-agent review:** A Fixer proposes a defensive instruction; a separate Red Team adjudicator evaluates it against the selected scenario's evidence and supplied cases. This is model-based review, not test execution or proof of correctness.
- **Provider separation:** Configure distinct Groq models for the Fixer and Red Team to reduce single-model bias.
- **Local-first inference switch:** Select Ollama for local inference. Local mode requires a loopback Ollama endpoint and does not fall back to Groq.
- **Claim-level compliance records:** Turn recorded unsupported claims into timestamped, exportable audit entries with the isolated claim and divergence reason.
- **Visual hallucination diffing:** Compare the original output with the verified response and the expected ground truth.
- **Evidence-grounded diagnostics:** Ask questions about a run; diagnostic answers must cite values in the JSON supplied with the request.
- **Pipeline modes:** Run with Groq (`live_llm`), local Ollama (`local_llm`), or deterministic offline execution (`mock_llm`).

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, Vite, Tailwind CSS 4 |
| Backend API | Python 3.11+, FastAPI, Uvicorn |
| Pipeline and validation | Python, Pydantic, LiteLLM |
| Persistence | SQLite via SQLAlchemy |
| Cloud inference | Groq API |
| Local inference | Ollama |

## Quick start

### Prerequisites

- Python 3.11 or newer
- Node.js and npm
- For cloud inference: a Groq API key and access to the configured models
- For local inference: Ollama installed with the configured model available

### 1. Clone the repository

```powershell
git clone https://github.com/Darshika140/NEMESIS.git
cd NEMESIS
```

### 2. Install backend dependencies

From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks activation, either allow it for the current terminal with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, or use the virtual environment's interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 3. Configure inference

Create the backend environment file:

```powershell
Copy-Item .secrets\.env.example .secrets\.env
```

For **Groq**, set `GROQ_API_KEY` in `.secrets\.env`. The example file also contains separate Fixer and Red Team model settings; use model IDs available to your Groq account.

For **Ollama**, install/start Ollama and ensure the configured model exists. Check available models with:

```powershell
ollama list
```

The example defaults to `gemma4:e2b`. If needed, download it with `ollama pull gemma4:e2b`. Ollama may already be running in the background; if port `11434` is occupied, check that the Ollama service is available rather than starting a second server.

You can also use `mock_llm` mode for an offline smoke test without configuring either provider.

### 4. Start the backend

In a terminal at the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn nemesis.api.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `http://127.0.0.1:8000/docs`.

### 5. Install and start the frontend

In a second terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the Vite URL printed in the terminal, usually `http://localhost:5173`. The frontend's `.env.example` points to the default backend at `http://127.0.0.1:8000`.

### 6. Run a quick check

From the repository root, run the tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

To create a deterministic run without calling an LLM, send a request to the API in another terminal:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/run `
  -ContentType "application/json" `
  -Body '{"mode":"mock_llm","n_scenarios":1}'
```

## System architecture

1. The **React dashboard** submits pipeline requests and displays run metrics, selected scenarios, review events, and audit data.
2. The **FastAPI backend** validates requests, runs the NEMESIS pipeline, stores run/scenario data in SQLite, and exposes the dashboard API.
3. The backend's **inference boundary** routes model requests to Groq or to the configured loopback-only Ollama endpoint. Mock mode provides a deterministic path for offline development.
4. For an Agent Boardroom review, the **Fixer** proposes an instruction and the **Red Team adjudicator** reviews it against only the selected failure evidence and supplied regression cases. The streamed results return to the dashboard.
5. The diagnostic endpoint receives the current run/scenario JSON from the browser and validates citations against that payload. It does not have server-side filesystem access.

## Hackathon impact

AI agents can confidently report success even when their tools or the world state show an operation is still pending or has failed. NEMESIS makes these discrepancies visible, helps teams review a narrowly scoped defensive instruction, and records unsupported claims for inspection. Its Local option demonstrates a privacy-oriented workflow by keeping inference on the Ollama service running on the backend machine instead of routing those requests to Groq.

These capabilities are intended to support development and evaluation. Before using NEMESIS with sensitive data or exposing it outside a trusted development environment, add appropriate authentication, authorization, rate limiting, secure transport, monitoring, and operational review.

## Project status

NEMESIS is an actively developed hackathon project. There is currently no declared open-source license or configured CI workflow; the badges above intentionally reflect that status. Until a license is added, reuse and redistribution permissions are not explicitly granted.

## Contributing

Issues and pull requests are welcome. For a proposed change, include the problem it addresses, steps to reproduce or verify it, and any relevant test coverage. Do not submit API keys, `.env` files, database files, or other secrets.

## Security

Please do not include credentials, personal data, or confidential prompts in public issues. Do not expose the development API to an untrusted network. See [docs/diagnostic-and-healing.md](./docs/diagnostic-and-healing.md) for provider behavior and API details.
