# AI Ticket Assistant API

[![CI](https://github.com/Unequal1213/ai-ticket-assistant-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Unequal1213/ai-ticket-assistant-api/actions/workflows/ci.yml)

AI Ticket Assistant API is a portfolio FastAPI backend for support tickets. A
human operator can explicitly request classification, priority, a bounded
summary, and a draft reply. The application supports an offline deterministic
rule provider and an optional external LLM provider behind the same interface.

The external-provider path was verified with one controlled Groq
OpenAI-compatible Responses API smoke using synthetic data. That check covered
strict structured output with local schema validation, PII masking before the
provider boundary, a stateless request with `store=false`, transparent
provider/model/fallback audit metadata, and PostgreSQL persistence. The default
remains `AI_PROVIDER=deterministic`; CI and automated tests never call an
external AI service. The deterministic provider remains available for offline
development and tests.

See the [provider smoke guide](docs/provider-smoke.md#controlled-real-provider-verification)
for the verified scope and its limitations.

## What the project demonstrates

- FastAPI ticket CRUD and an explicit analysis endpoint.
- SQLAlchemy models, PostgreSQL runtime configuration, and Alembic migrations.
- A typed provider contract with deterministic and external implementations.
- Strict Pydantic validation for structured analysis output.
- PII risk reduction before external requests.
- Bounded timeouts, retries, concurrency, input/output limits, and daily quota.
- Transparent fallback and persisted audit metadata.
- Network-independent Pytest coverage, Ruff, Docker, and GitHub Actions CI.

The copilot proposes a classification and draft. It does not send a reply,
change an order, issue a refund, or make the operator's decision.

## Architecture

```text
app/
  ai/
    base.py                     # TicketAnalysisProvider protocol
    schemas.py                  # strict result and provider schemas
    deterministic_provider.py   # offline rule-based provider
    llm_provider.py             # official async OpenAI Responses client
    factory.py                  # provider/service construction
    pii.py                      # detectable PII masking and plain-text handling
    limits.py                   # process-local daily request counter
    retry.py                    # bounded exponential backoff with jitter
    prompts/ticket_analysis_v1.py
  services/
    ticket_analysis_service.py  # fallback, persistence, and audit orchestration
    ticket_service.py           # CRUD business/database logic
  api/routes.py
  config.py
```

See [AI architecture](docs/ai-architecture.md) and
[AI safety](docs/ai-safety.md) for the detailed flow and boundaries. The
[provider smoke guide](docs/provider-smoke.md) documents the reproducible offline,
deterministic, and explicitly controlled live validation modes.

## Analysis result

Both providers must produce this validated structure:

```json
{
  "category": "technical",
  "priority": "medium",
  "summary": "The synthetic application reports an error.",
  "suggested_reply": "Thanks. An operator will review the technical issue.",
  "confidence": 0.82,
  "reasoning_tags": ["error_signal"]
}
```

`category` and `priority` are enums. Summary, draft, tag count, tag format, and
confidence are bounded. Extra fields are rejected. `reasoning_tags` are short
observable-signal labels, not chain-of-thought. Raw model JSON and full provider
responses are never returned by the API or stored in the database.

The analysis response keeps the existing ticket fields at the top level and adds
safe audit fields, so existing clients can continue reading `category`,
`priority`, `summary`, and `suggested_reply`.

## Provider configuration

`.env.example` is a placeholder-only template. The application deliberately does
not discover or load `.env` files: pass configuration through the process
environment, a secret manager, or an explicit Docker Compose `--env-file`:

```bash
docker compose --env-file .env up --build
```

If you create a local `.env` from the template, keep it untracked and treat it as
a secret-bearing file. Merely placing it in the repository does not configure a
Python, Alembic, test, or Uvicorn process.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_PROVIDER` | `deterministic` | `deterministic` or `llm` |
| `AI_MODEL` | none | Required operator-selected model identifier in `llm` mode |
| `AI_API_KEY` | none | Required only in `llm` mode; never log or commit it |
| `AI_BASE_URL` | official HTTPS endpoint | Only supported endpoint override; HTTPS required at runtime |
| `AI_TIMEOUT_SECONDS` | `15` | Per-request timeout |
| `AI_MAX_RETRIES` | `2` | Shared transient retry budget |
| `AI_MAX_REPAIRS` | `1` | Fresh repair phases; limited to `0` or `1` |
| `AI_MAX_INPUT_CHARS` | `8000` | Combined ticket title/description limit |
| `AI_MAX_OUTPUT_TOKENS` | `800` | Provider output budget |
| `AI_FALLBACK_ENABLED` | `true` | Permit explicit deterministic fallback |
| `AI_DAILY_REQUEST_LIMIT` | `100` | Process-local external HTTP request quota; `0` blocks all |
| `AI_MAX_CONCURRENT_REQUESTS` | `4` | Per-process external request concurrency |
| `AI_PROMPT_VERSION` | `ticket-analysis-v1` | Supported versioned prompt |

If `AI_PROVIDER=llm` has no key or explicit `AI_MODEL`, application startup fails
closed. Deterministic mode needs neither. The operator selects the model; this
project does not guarantee availability or pricing for any model ID. Verify both
against the configured provider/account before a controlled smoke test. Secrets
remain environment configuration and are represented with Pydantic `SecretStr`;
they are not part of API schemas or logs.

`AI_BASE_URL` is the only supported endpoint override. When absent, the client is
given the official HTTPS endpoint explicitly, so SDK-specific `OPENAI_BASE_URL`
cannot redirect the API key. Insecure loopback URLs are accepted only by an
explicit test-only constructor option, not runtime environment configuration.

The SDK is pinned to `openai==2.52.0`. The provider uses the official
`AsyncOpenAI` Responses API with a deliberately limited strict JSON Schema. SDK automatic retries are
disabled so the application's retry policy is bounded and testable. This
implementation choice follows the official
[OpenAI Python SDK](https://github.com/openai/openai-python) and
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).
The provider-side schema intentionally uses only confirmed object, array, enum,
required, and `additionalProperties` constructs. Full length, pattern, range,
array-size, and extra-field checks run locally through `TicketAnalysisResult`.

## Deterministic provider and fallback

The deterministic provider is an offline keyword-rule implementation, not an AI
model. Its main classification behavior remains compatible with the initial
project and is suitable for reproducible review, demos, and CI.

When `AI_PROVIDER=llm`, transient/provider/output failures use the deterministic
provider only if `AI_FALLBACK_ENABLED=true`. The response and database state show:

- `provider_requested`
- `provider_used`
- `fallback_used`
- `model_requested`
- `model_used`
- `prompt_version`
- `error_category` when fallback followed a provider failure

Authentication errors are not retried. Timeouts, connections, HTTP 429, and 5xx
responses can be retried with bounded exponential backoff and jitter. Initial,
retry, and repair calls share the total budget
`1 + AI_MAX_RETRIES + AI_MAX_REPAIRS`; repair does not create another independent
retry chain. The invalid raw response is not echoed into the repair prompt or API
error. A timeout may occur after the provider processed an attempt, so retry can
duplicate token usage or charges; these controls are not a billing guarantee.

## PII and prompt safety

Before an external request, HTML/entities are converted to plain text, unsafe
controls are removed, Unicode is normalized, and only then detectable email,
phone, card-like, and explicitly labeled document/identifier patterns are
replaced with typed placeholders. Prompt instructions
treat ticket content, including Markdown and prompt-like text, as untrusted data;
the provider has no tools and is told not to perform actions.

Pattern masking can have false positives and cannot guarantee removal of every
kind of personal or confidential information. Only synthetic data is used in this
repository. Read [AI safety](docs/ai-safety.md) before enabling an external
provider.

Ticket descriptions have a 20,000-character API storage limit. The separate
provider input limit defaults to 8,000 combined title/description characters and
can be lowered independently to reduce external exposure and spend.

## Audit metadata

Analysis uses separate short database units before and after the provider await;
no database session is kept open during that await. Each explicit analysis
updates the ticket with result fields plus:

- status, requested/used provider, requested/used model, prompt version, and fallback flag;
- original input character count and provider-reported input/output tokens;
- provider/repair attempt counts, latency, safe provider request ID, error
  category, and analysis timestamp.

API keys, full prompts, full raw responses, and a duplicate copy of redacted input
are not persisted. Token counts are stored without hard-coded price claims. The
daily counter and semaphore are process-local controls, not distributed billing
or rate-limit infrastructure.

## API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health status |
| `POST` | `/tickets` | Create a ticket |
| `GET` | `/tickets` | List/filter/sort tickets |
| `GET` | `/tickets/{ticket_id}` | Read one ticket |
| `PATCH` | `/tickets/{ticket_id}` | Partially update a ticket |
| `DELETE` | `/tickets/{ticket_id}` | Delete a ticket |
| `POST` | `/tickets/{ticket_id}/analyze` | Explicitly analyze or re-analyze a ticket |

Provider failures use a controlled error shape and never expose a stack trace or
raw provider response:

```json
{
  "error": {
    "code": "provider_timeout",
    "message": "The configured analysis provider timed out.",
    "request_id": "req_synthetic"
  }
}
```

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
export DATABASE_URL
export AI_PROVIDER=deterministic
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

In the commands above, `DATABASE_URL` must already have been supplied by the
operator's shell or secret manager. The application never reads repository
`.env` implicitly.

For Docker-based PostgreSQL development:

```bash
cp .env.example .env
docker compose --env-file .env up --build
```

Here `.env` is passed to Compose explicitly; do not commit it. The Compose app
runs `python -m alembic upgrade head` before Uvicorn.

## Synthetic deterministic demo

Start the API with `AI_PROVIDER=deterministic`, then run:

```bash
python scripts/demo_deterministic.py
```

The script creates six synthetic tickets covering delivery, return, payment,
technical, order-change, and general-question cases, explicitly analyzes each,
and prints validated results. It contains no real names, contacts, companies, or
customer data.

Example deterministic result excerpt:

```json
{
  "category": "billing",
  "priority": "medium",
  "provider_requested": "deterministic",
  "provider_used": "deterministic",
  "fallback_used": false,
  "model_requested": null,
  "model_used": null,
  "provider_attempts": 0,
  "repair_attempts": 0,
  "prompt_version": "ticket-analysis-v1"
}
```

An LLM command is prepared in [manual smoke test](docs/manual-smoke-test.md), but
must not be run without a separate decision, a user-owned restricted API key,
and synthetic input.

## Quality checks

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
git diff --check
```

Migration round-trip against a disposable database:

```bash
DATABASE_URL=sqlite+pysqlite:////tmp/ai-ticket-migration-check.db \
PYTHON_DOTENV_DISABLED=1 python -m alembic upgrade head
DATABASE_URL=sqlite+pysqlite:////tmp/ai-ticket-migration-check.db \
PYTHON_DOTENV_DISABLED=1 python -m alembic downgrade base
DATABASE_URL=sqlite+pysqlite:////tmp/ai-ticket-migration-check.db \
PYTHON_DOTENV_DISABLED=1 python -m alembic upgrade head
```

CI passes deterministic configuration explicitly, runs Ruff, checks the
migration round-trip on disposable SQLite, and runs the complete Pytest suite.
It does not need `AI_API_KEY` and does not perform external LLM requests.
