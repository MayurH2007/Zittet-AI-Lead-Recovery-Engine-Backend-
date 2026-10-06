# Zizzet AI Lead Recovery Engine

A production-quality backend API service that identifies inactive or high-intent leads, analyzes the lead and conversation history using an LLM, and generates a lead score, priority, customer intent, conversation stage, summary, next best action, recommended follow-up channel, personalized follow-up message, and a do-not-contact flag.

> This is a backend-only project. There is no CRM UI.

---

## 1. Project Overview

Zizzet analyzes leads using an LLM and returns a structured, validated analysis that a sales/recovery team can act on. It is multi-tenant, idempotent at the webhook layer, handles opt-out deterministically, and validates every LLM response with Pydantic before persisting it.

## 2. Problem Statement

Sales teams accumulate leads that go cold. Manually reviewing each lead's conversation history to decide priority, intent, and the next action is expensive and inconsistent. Zizzet automates that analysis: given a lead and its conversation, it produces a score, priority, intent, stage, summary, next best action, and a personalized follow-up message — while respecting explicit opt-out requests.

## 3. Architecture

```
HTTP Request (X-Tenant-ID)
        |
  FastAPI Route  ── validates tenant header + body
        |
   Service Layer ── orchestrates business logic
        |
  Repository     ── tenant-scoped DB access (SQLAlchemy async)
        |
  PostgreSQL

LLM path:
   AnalysisService ──> LLMProvider (OpenAI | Mock)
        |                    |
   Pydantic validation      structured JSON output
        |
   Business rules (opt-out, score clamp)
        |
   AnalysisRepository ──> PostgreSQL
```

Key layers:

- **Routes** (`app/api/routes`): thin HTTP handlers. Tenant header validation, request validation, then delegate to a service.
- **Services** (`app/services`): business logic. `AnalysisService` orchestrates the full analyze flow; `FollowUpService` returns stored follow-ups; `WebhookService` handles idempotent intake.
- **Repositories** (`app/repositories`): all DB access, always scoped by `tenant_id`.
- **LLM** (`app/llm`): provider abstraction (`LLMProvider`) with `OpenAIProvider` and `MockLLMProvider`. The service never trusts raw LLM output — it always validates with `AnalysisResponse`.
- **Workers** (`app/workers`): background processing for webhooks. Written so Redis/ARQ can replace FastAPI BackgroundTasks without changing the service layer.

## 4. Tech Stack

- Python 3.11+
- FastAPI + Pydantic v2
- SQLAlchemy 2.x (async) + asyncpg
- PostgreSQL 16
- Alembic (migrations)
- OpenAI Python SDK (structured JSON output)
- pytest + httpx (TestClient)
- Docker + docker-compose

## 5. Project Structure

```
app/
    main.py                  # FastAPI app factory + lifespan
    api/
        deps.py              # X-Tenant-ID dependency
        routes/
            health.py
            leads.py
            webhooks.py
    core/
        config.py            # env-driven settings (pydantic-settings)
        database.py          # async engine + session factory
        logging.py           # structured logging (structlog)
        exceptions.py        # domain exceptions + handlers
    models/                  # SQLAlchemy ORM models
        lead.py
        conversation.py
        analysis.py
        webhook_event.py
    schemas/                 # Pydantic v2 request/response schemas
        lead.py
        conversation.py
        analysis.py
        webhook.py
        common.py
    services/
        lead_service.py
        analysis_service.py
        followup_service.py
        webhook_service.py
    llm/
        base.py              # LLMProvider abstraction
        openai_provider.py   # real OpenAI integration
        mock_provider.py     # deterministic mock for tests/dev
        prompts.py           # versioned prompts
    workers/
        tasks.py             # background webhook processing
    repositories/
        lead_repository.py
        analysis_repository.py
        webhook_repository.py
    utils/
        idempotency.py
        opt_out.py

tests/
    test_health.py
    test_leads.py
    test_followup.py
    test_webhooks.py
    test_tenant_isolation.py
    test_idempotency.py
    test_opt_out.py
    test_llm_service.py

alembic/
    env.py
    versions/0001_initial.py
Dockerfile
docker-compose.yml
requirements.txt
.env.example
README.md
```

## 6. Database Schema

### leads
| column | type | notes |
|---|---|---|
| id | VARCHAR(64) PK | internal UUID |
| tenant_id | VARCHAR(64) | indexed |
| external_lead_id | VARCHAR(128) | tenant's CRM id |
| customer_name | VARCHAR(255) | nullable |
| customer_phone | VARCHAR(64) | nullable |
| source | VARCHAR(64) | nullable |
| status | VARCHAR(64) | default `new` |
| last_contacted_at | TIMESTAMPTZ | nullable |
| created_at / updated_at | TIMESTAMPTZ | |

Unique index: `(tenant_id, external_lead_id)`.

### conversations
| column | type | notes |
|---|---|---|
| id | VARCHAR(64) PK | |
| tenant_id | VARCHAR(64) | |
| lead_id | VARCHAR(64) FK → leads.id ON DELETE CASCADE | |
| role | VARCHAR(32) | customer / agent / system |
| message | TEXT | |
| created_at / updated_at | TIMESTAMPTZ | |

Index: `(tenant_id, lead_id)`.

### analyses
| column | type | notes |
|---|---|---|
| id | VARCHAR(64) PK | |
| tenant_id | VARCHAR(64) | |
| lead_id | VARCHAR(64) FK → leads.id ON DELETE CASCADE | |
| lead_score | INTEGER | 0–100 |
| priority | VARCHAR(16) | low/medium/high |
| intent | VARCHAR(32) | |
| stage | VARCHAR(32) | |
| summary | TEXT | |
| next_best_action | TEXT | |
| follow_up_channel | VARCHAR(16) | whatsapp/email/phone/none |
| follow_up_message | TEXT | empty when do_not_contact |
| do_not_contact | BOOLEAN | |
| model_name | VARCHAR(64) | which LLM produced it |
| prompt_version | VARCHAR(32) | e.g. `lead_recovery_v1` |
| created_at / updated_at | TIMESTAMPTZ | |

Indexes: `(tenant_id, lead_id)`, `(tenant_id, priority)`.

### webhook_events
| column | type | notes |
|---|---|---|
| id | VARCHAR(64) PK | |
| tenant_id | VARCHAR(64) | |
| event_id | VARCHAR(128) | external event id |
| event_type | VARCHAR(64) | |
| payload | TEXT | full JSON payload |
| status | VARCHAR(16) | received/processing/completed/failed |
| error | TEXT | nullable |
| created_at | TIMESTAMPTZ | |
| processed_at | TIMESTAMPTZ | nullable |

**Unique constraint: `(tenant_id, event_id)`** — the authoritative idempotency guarantee.

## 7. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| POST | `/api/v1/leads/analyze` | Analyze a lead + conversation |
| GET | `/api/v1/leads/{lead_id}/analysis` | Get latest analysis (tenant-scoped) |
| POST | `/api/v1/leads/{lead_id}/follow-up` | Get stored follow-up |
| POST | `/api/v1/webhooks/leads` | Idempotent webhook intake |

All endpoints (except `/health`) require the `X-Tenant-ID` header.

Interactive docs: `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc`.

## 8. Example Requests

### Analyze a lead
```bash
curl -X POST http://localhost:8000/api/v1/leads/analyze \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: business_001" \
  -d '{
    "tenant_id": "business_001",
    "lead_id": "lead_1024",
    "customer": {"name": "Arun Kumar", "phone": "+919876543210"},
    "lead": {"source": "whatsapp", "status": "contacted", "created_at": "2026-09-20", "last_contacted_at": "2026-09-25"},
    "conversation": [
      {"role": "customer", "message": "I am interested in your CRM."},
      {"role": "agent", "message": "How many users do you need?"},
      {"role": "customer", "message": "Around 25 users. What is the pricing?"}
    ]
  }'
```

### Get analysis
```bash
curl http://localhost:8000/api/v1/leads/lead_1024/analysis \
  -H "X-Tenant-ID: business_001"
```

### Get follow-up
```bash
curl -X POST http://localhost:8000/api/v1/leads/lead_1024/follow-up \
  -H "X-Tenant-ID: business_001"
```

### Webhook
```bash
curl -X POST http://localhost:8000/api/v1/webhooks/leads \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: business_001" \
  -d '{
    "event_id": "evt_123",
    "event_type": "lead.updated",
    "tenant_id": "business_001",
    "lead_id": "lead_1024",
    "customer": {"name": "Arun Kumar", "phone": "+919876543210"},
    "lead": {"source": "whatsapp", "status": "contacted"},
    "conversation": [{"role": "customer", "message": "50 employees and we need pricing."}]
  }'
```

## 9. Example Response

```json
{
  "lead_score": 85,
  "priority": "high",
  "intent": "purchase",
  "stage": "pricing_interest",
  "summary": "Customer mentioned team size. Customer asked about pricing.",
  "next_best_action": "Send a tailored pricing quote for the mentioned team size.",
  "follow_up_channel": "whatsapp",
  "follow_up_message": "Hi Arun, thanks for sharing your team size. Here's a pricing plan tailored for you — would you like to proceed?",
  "do_not_contact": false
}
```

## 10. AI Approach

- The `LLMProvider` abstraction (`app/llm/base.py`) defines `analyze_lead(context) -> str` (raw JSON).
- `OpenAIProvider` calls the OpenAI Chat Completions API with `response_format={"type": "json_object"}` to enforce JSON output, then returns the raw string.
- `MockLLMProvider` is a deterministic, rule-based mock used when no `OPENAI_API_KEY` is set and in all tests. It returns JSON in the same schema.
- The `AnalysisService` **always** validates the raw output with the `AnalysisResponse` Pydantic model. Invalid JSON or schema violations raise `LLMOutputInvalid` (502) — no invalid analysis is ever stored.
- Retry: up to 2 retries with exponential backoff on transient errors (timeouts, rate limits, connection errors).

## 11. Prompt Versioning

The system prompt lives in `app/llm/prompts.py` with `PROMPT_VERSION = "lead_recovery_v1"`. Every stored analysis row records the `prompt_version` and `model_name` that produced it, so changes can be A/B tested and audited.

## 12. Structured Output Validation

The LLM is instructed to return only the required JSON schema. The raw string is parsed and validated with `AnalysisResponse` (Pydantic v2), which enforces:
- `lead_score`: int 0–100
- `priority`, `intent`, `stage`, `follow_up_channel`: enums
- `summary`, `next_best_action`: non-empty bounded strings
- `do_not_contact`: bool
- cross-field rule: `follow_up_message` must be empty when `do_not_contact` is true
- `extra="forbid"`: unknown fields are rejected

If validation fails, the API returns 502 and nothing is persisted.

## 13. Tenant Isolation

- Every request requires `X-Tenant-ID`.
- For `POST /leads/analyze` and `POST /webhooks/leads`, the `tenant_id` in the body must match the header (403 on mismatch).
- Every repository query includes `tenant_id` in its `WHERE` clause. No query ever selects by `lead_id` alone.
- `GET /leads/{lead_id}/analysis` and `POST /leads/{lead_id}/follow-up` resolve the lead by `(tenant_id, external_lead_id)` — a tenant cannot access another tenant's lead even with the same external id.
- Tests in `tests/test_tenant_isolation.py` prove this.

## 14. Webhook Idempotency

- `webhook_events` has a `UNIQUE(tenant_id, event_id)` constraint — the final database-level guarantee.
- On intake, the service attempts to insert; if a row already exists it returns `duplicate=true` with the original status and does **not** enqueue another job.
- The background task re-checks the event status before processing, guarding against double-enqueue.
- A duplicate delivery produces exactly one processing result.
- Tests in `tests/test_idempotency.py` and `tests/test_webhooks.py` (Case E).

## 15. Background Processing

- Webhooks use FastAPI `BackgroundTasks` to run analysis after returning 202.
- The task (`process_webhook_event`) takes only primitives (tenant_id, event_id, payload string) and opens its own DB session — so it can be moved to Redis/ARQ without changing the service layer.
- The webhook event status transitions: `received → processing → completed` (or `failed`).

## 16. Error Handling

Consistent JSON error envelope:
```json
{ "error": { "code": "...", "message": "...", "details": {...} } }
```

Handled cases: malformed request (422), missing tenant header (400), tenant mismatch (403), lead not found (404), analysis not found (404), duplicate webhook (200 idempotent), follow-up prohibited for opt-out (409), LLM timeout (504), LLM error (502), malformed LLM output (502), database errors (503), unhandled exceptions (500). Internal stack traces are never exposed.

## 17. Opt-Out Handling

- `app/utils/opt_out.py` detects opt-out signals (STOP, unsubscribe, opt out, remove me, do not contact me, etc.) in customer messages.
- If detected **before** the LLM call, the LLM is skipped and a canonical do-not-contact response is returned.
- If the LLM is called, deterministic business rules **after** the LLM force `do_not_contact=true`, `follow_up_channel=none`, `follow_up_message=""` — the LLM can never override an explicit opt-out.
- The follow-up endpoint returns 409 for opted-out leads.

## 18. Testing

Tests use `MockLLMProvider` (no network, no API key). Run with:

```bash
pytest
```

Coverage:
- Health endpoint
- Successful analysis (Cases A–D)
- Validation failures
- Tenant isolation
- STOP / opt-out (Case D)
- Duplicate webhook idempotency (Case E)
- LLM malformed output → 502
- LLM failure → 502
- LLM timeout → 504
- Follow-up endpoint + prohibited follow-up
- High-intent / low-intent / demo-request scenarios

## 19. Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set DATABASE_URL to your Postgres
alembic upgrade head
uvicorn app.main:app --reload
```

Without an `OPENAI_API_KEY`, the service uses `MockLLMProvider` so you can test locally immediately.

## 20. Docker Setup

```bash
docker compose up --build
```

This starts PostgreSQL and the backend. Migrations run automatically on container start. The API is available at `http://localhost:8000`.

To run migrations manually inside the container:
```bash
docker compose exec backend alembic upgrade head
```

## 21. Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://...` | Async SQLAlchemy DB URL |
| `OPENAI_API_KEY` | no | empty | If set, uses OpenAI; otherwise Mock |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | OpenAI model name |
| `LLM_MAX_RETRIES` | no | `2` | Max retries on transient LLM errors |
| `LLM_TIMEOUT_SECONDS` | no | `30` | OpenAI request timeout |
| `APP_ENV` | no | `development` | development/staging/production/test |
| `LOG_LEVEL` | no | `INFO` | Logging level |

## 22. Swagger URL

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## 23. Assumptions

- The `lead_id` in API paths is the **external** lead id (the one the caller sends in `analyze`), not the internal UUID. The service resolves it per tenant.
- Conversation history sent in each request is treated as the authoritative snapshot — existing messages for the lead are replaced.
- No authentication is implemented (per spec). Tenant isolation is via the `X-Tenant-ID` header.
- The mock provider is deterministic and rule-based so evaluation cases produce stable, assertable outputs.

## 24. Limitations

- Background processing is in-process (FastAPI BackgroundTasks). For horizontal scaling, Redis/ARQ should be added — the service layer is already designed for this.
- No rate limiting on the webhook endpoint.
- Conversation replacement (vs. append) may not suit all CRM integrations.
- No pagination on analysis history (only latest is exposed).

## 25. Future Improvements

- Redis/ARQ worker for durable background processing.
- Per-tenant API keys / authentication.
- Analysis diffing between runs to track lead progression.
- Streaming LLM responses for large conversations.
- Prompt A/B testing via the `prompt_version` field.
- Prometheus metrics + tracing.
