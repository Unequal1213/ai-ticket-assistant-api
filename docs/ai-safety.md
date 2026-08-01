# AI safety boundaries

## Human responsibility

This service is a support copilot. It suggests classification and a draft reply.
It does not send messages, call tools, change orders, issue refunds, make account
changes, or decide a customer outcome. An operator must review the result and
remains responsible for any action.

## Data sent externally

Only the ticket title and description are candidates for an external request.
Before sending them, the provider converts HTML/entities to plain text, removes
unsafe controls, applies predictable Unicode normalization, then performs PII
pattern masking and final outbound validation. It never returns to the original
text after masking. The database continues to store the original ticket according to
the existing application business logic; the redacted form is not stored again.

Current masking targets:

- conventional email addresses;
- phone-like sequences containing 7 through 15 digits;
- card-like sequences containing 13 through 19 digits with common separators;
- identifiers following explicit labels such as passport, SSN, tax ID, national
  ID, `паспорт`, `СНИЛС`, or `ИНН`.

Placeholders such as `[REDACTED_EMAIL]` are sent instead. HTML tags are reduced to
plain text and unsafe control characters are removed. Markdown remains text and
must be escaped by any UI that later renders it.

Pattern matching is not semantic data-loss prevention. It can miss uncommon
formats, names, addresses, free-form secrets, or obfuscated values, and it can
mask benign number-like text. Do not describe it as removing or protecting all
PII. Do not use real customer data for demos or uncontrolled provider tests.

## Provider-side response storage

Every Responses API request explicitly sends `store=False`. The application does
not use a server-side conversation or previous-response ID: it validates the
structured result and persists only its own limited audit metadata. This reduces
the provider-side application state requested by this integration, but it is not
a promise of absolute Zero Data Retention. Processing real customer data still
requires a privacy review and suitable contractual/provider data controls. The
controlled smoke procedure uses only a synthetic ticket.

## Prompt-injection controls

The versioned developer prompt says that ticket fields are untrusted data and
must never override instructions. Ticket fields are serialized as JSON in the
Responses input field, separately from developer instructions. Prompt-like text
inside a ticket is not necessarily removed: it remains isolated as untrusted
data and must not be followed as an instruction. The provider receives no tools
and is forbidden from performing or claiming actions. Strict JSON Schema
constrains output shape, followed by local Pydantic validation.

These measures reduce risk; they do not prove immunity to every prompt injection
or unsafe model output. Operator review remains mandatory.

## Failure handling

- Raw model output is not returned to clients, stored, or included in application
  logs.
- Invalid output gets no more than one fresh repair request and then follows the
  explicit fallback/error policy.
- API errors contain a safe category, message, and sanitized request ID only.
- Authentication errors do not retry. Transient errors use bounded retries.
- Oversized input and exhausted process-local quota return controlled errors (or
  a transparent deterministic fallback when configured for provider errors).
- Async cancellation propagates instead of being converted into a fallback.
- Initial, transient retry, and repair calls share one bounded attempt budget. A
  timeout can still duplicate token usage or charges if the remote provider
  processed the timed-out request.

## Secret and logging rules

`AI_API_KEY` is read from the environment into `SecretStr`. It is absent from
models, schemas, responses, persistence, tests, and repository examples. The
example contains only `replace_with_provider_api_key`.

Application logs contain ticket ID, fixed provider label, configured model,
sanitized request ID, latency, fallback flag, and safe error category. They must
not contain ticket title/description, email, phone, API key, prompt, or full model
response. Avoid enabling verbose third-party HTTP/SDK logging in environments
that process sensitive input.

## Operational limitations

- Daily quota and concurrency are per process, not distributed.
- `provider_attempts` and `repair_attempts` are operational counters. Known token
  usage is cumulative, but these fields are not a billing ledger.
- Token metadata is provider-reported and may be absent on failed calls.
- No monetary price is hard-coded or estimated.
- A configurable base URL does not prove every OpenAI-compatible service supports
  the same structured-output behavior.
- The external integration has not received a controlled real-provider smoke test
  in this development phase.
- `AI_MODEL` must be selected explicitly; availability and cost depend on the
  operator's provider/account configuration.
- `AI_BASE_URL` is the only supported endpoint override. SDK-specific
  `OPENAI_BASE_URL` cannot redirect requests.
