# Reproducible provider smoke validation

The tracked smoke tool has three deliberately separate modes. It uses only
synthetic tickets and never treats a deterministic rehearsal as proof that an
external model works.

## Modes

### Preflight

```bash
.venv/bin/python scripts/provider_smoke.py preflight
```

`preflight` is network-free and needs neither Docker nor an API key. It runs the
production normalization, PII masking, prompt builder, provider request
construction, and strict response validation against `httpx.MockTransport`.
Every PII and prompt-boundary rule has a named invariant, so a failure identifies
one specific condition.

### Deterministic rehearsal

```bash
.venv/bin/python scripts/provider_smoke.py rehearsal
```

The rehearsal requires a clean worktree. It derives the image tag from the
current commit, builds the image, verifies its labels and non-root runtime user,
then starts disposable PostgreSQL and application containers with
`AI_PROVIDER=deterministic`. It creates one synthetic ticket, explicitly analyzes
it once, reads it back, checks audit persistence, scans logs, proves the provider
request count is zero, and removes all resources.

`--allow-dirty-tooling` exists only while developing the tracked smoke files. It
rejects dirty runtime/application files and must not be used for a live smoke.

### Controlled live smoke

Live mode is implemented but must be explicitly authorized and must never be run
as part of CI:

```bash
.venv/bin/python scripts/provider_smoke.py live \
  --env-file /absolute/path/outside/repository/provider-smoke.env \
  --expected-provider groq \
  --expected-model openai/gpt-oss-20b \
  --max-provider-requests 1 \
  --confirm-live-smoke
```

The command fails before reading the env file unless every live flag is present.
It then requires a clean expected branch, runs preflight, builds and verifies the
HEAD image, and completes a deterministic disposable runtime gate. Only after
those checks does it inspect and read the external env file.

The env file must:

- be an absolute path outside the repository;
- be owned by the current user and have permissions no wider than `600`;
- select `AI_PROVIDER=llm` and `AI_BASE_URL=https://api.groq.com/openai/v1`;
- set an operator-verified `AI_MODEL` matching the command;
- set fallback false, retries and repairs to zero, quota to one, and concurrency
  to one;
- contain a short-lived API key that is never printed by the tool.

Use only Docker-style `NAME=value` lines. Shell expansion is not performed.

## Image identity

The runner reads `git rev-parse HEAD` and derives:

```text
ai-ticket-assistant-api:smoke-${HEAD first 12 characters}
```

The build writes and subsequently verifies these labels:

- `org.opencontainers.image.revision=<full HEAD>`
- `ai.ticket.smoke.commit=<full HEAD>`
- `ai.ticket.smoke.mode=provider-validation`

The runner does not fall back to an older tag or an arbitrary existing image.
It also verifies that `.env` is absent from the image, the application imports,
`pip check` succeeds, and the configured runtime user is not root. An amended
commit therefore requires a newly tagged and labeled image.

## Client and request count

`scripts/provider_smoke_client.py` uses only the HTTP API and Python standard
library. It does not import the application, ORM, services, or provider code, so
its behavior is independent of the current directory and `PYTHONPATH`.

The application container mounts the tracked request instrumentation as
`sitecustomize.py`. It stores counters and boolean safety evidence only—never
headers, bodies, prompts, raw responses, or secrets. A future live PASS requires
both `provider_attempts=1` in persisted metadata and exactly one counted request
to the configured Responses endpoint. Retries, repairs, fallback, and repeated
analyze are disabled.

## Cleanup and credential handling

Every runtime uses uniquely labeled containers, network, and volume. Cleanup runs
from `finally`, removes temporary credentials, logs, results, and captures, then
verifies that resources for that run ID are gone. The user-provided live env file
is not deleted automatically.

Create that file immediately before an authorized smoke, use only synthetic data,
and delete it afterward. Revoke the key in Groq Console even if the smoke fails,
and review Groq Usage to confirm the expected single request/token record. Do not
place the file in this repository or shell history.

## Controlled real-provider verification

On 2026-08-01, commit
`99989ee904254399b062e10b2aedfaf8de7a7bbf` was checked with one controlled
request to the Groq OpenAI-compatible Responses API using model
`openai/gpt-oss-20b` and synthetic data only. Retries, repairs, and deterministic
fallback were disabled by the smoke policy.

The verified flow produced these results:

- `POST /tickets` returned HTTP 201 without invoking the provider;
- one explicit `POST /tickets/{id}/analyze` returned HTTP 200 and produced
  exactly one provider request;
- the structured result passed local Pydantic/schema validation;
- the validated result and bounded audit metadata were persisted in PostgreSQL,
  and a subsequent ticket read confirmed persistence;
- outbound PII-masking checks passed before the provider boundary;
- the Responses request used `store=false`, with no tools, conversation, or
  `previous_response_id`;
- the application did not persist the raw provider response or full prompt;
- log and database safety scans passed; and
- all disposable Docker resources were removed after verification.

This evidence is deliberately narrow. It covers one provider flow and one model
at one point in time; provider model availability and limits can change. It is
not load testing, production SLA verification, an absolute guarantee that every
class of PII is removed, or proof of immunity to every prompt-injection attack.
Real customer data still requires separate privacy, legal, and contractual
review.

## Limits

A successful smoke validates one provider request for one configured model and
account at one point in time. It does not prove production readiness, universal
model availability, complete PII removal, immunity to prompt injection, stable
pricing, or suitability for real customer data. Privacy and contractual review
remain required before processing customer information.
