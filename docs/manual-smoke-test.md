# Manual smoke tests with synthetic data

No real external-provider request was executed while implementing this phase.
Run the LLM procedure only after a separate explicit decision.

## Offline deterministic demo

1. Configure `AI_PROVIDER=deterministic` and a disposable local database.
2. Start the API and confirm `GET /health` returns `{"status":"ok"}`.
3. Run:

   ```bash
   python scripts/demo_deterministic.py
   ```

4. Confirm every response has `provider_requested=deterministic`,
   `provider_used=deterministic`, `fallback_used=false`,
   `model_requested=null`, `model_used=null`, and `provider_attempts=0`.

The script uses only synthetic delivery, return, payment, technical,
order-change, and general-question tickets.

## Prepared controlled external-provider smoke test — do not run by default

Safety prerequisites:

1. Use a dedicated, revocable, least-privilege key with a very small provider
   budget. Never paste it into Git, chat, a command committed to shell history,
   screenshots, or logs.
2. Use a disposable local database and only the synthetic request below.
3. Verify the operator-selected provider/model supports Responses API strict JSON
   Schema, is available to the test account, and has acceptable current pricing.
4. Set fallback off so a deterministic result cannot be mistaken for a successful
   external call. Set quota/concurrency/retries to the smallest useful values.
5. Keep SDK/HTTP debug logging disabled.

Prepare environment variables through a secure local secret mechanism. The
following placeholders show the required non-secret configuration; they were not
executed during development:

```bash
AI_PROVIDER=llm
AI_MODEL=replace_with_provider_model
AI_API_KEY=replace_with_provider_api_key
AI_FALLBACK_ENABLED=false
AI_DAILY_REQUEST_LIMIT=1
AI_MAX_CONCURRENT_REQUESTS=1
AI_MAX_RETRIES=0
AI_MAX_REPAIRS=0
AI_TIMEOUT_SECONDS=15
AI_MAX_INPUT_CHARS=1000
AI_MAX_OUTPUT_TOKENS=400
AI_PROMPT_VERSION=ticket-analysis-v1
```

Start the application, then create exactly one synthetic ticket:

```bash
curl --fail-with-body \
  -H 'Content-Type: application/json' \
  -d '{"title":"Synthetic payment error","description":"The test checkout reports an error after a fictional payment attempt."}' \
  http://127.0.0.1:8000/tickets
```

Use the returned synthetic ticket ID for the one explicitly authorized analysis:

```bash
curl --fail-with-body -X POST \
  http://127.0.0.1:8000/tickets/REPLACE_WITH_SYNTHETIC_ID/analyze
```

Acceptance checks:

- HTTP 200 and every analysis field validates;
- `provider_requested=llm`, `provider_used=llm`, `fallback_used=false`;
- `model_requested` matches the configured model, `model_used` reports the
  provider response model, and `prompt_version=ticket-analysis-v1`;
- `provider_attempts=1` and `repair_attempts=0`;
- a safe request ID and token usage are present if the provider returns them;
- database audit fields match the response;
- logs contain no ticket text, API key, prompt, or raw provider response.

If any check fails, stop. Do not broaden retries, input data, or budget to hide the
failure. Record only safe error metadata, then return to deterministic mode. After
the test, revoke or rotate the temporary key, remove it from the local environment,
and delete the disposable database using an approved local cleanup procedure.

Only after this controlled test succeeds may project text say that the selected
provider/model was smoke-tested on the recorded date. It still must not claim
perfect accuracy, complete PII removal, autonomous decision-making, or general
production readiness.
