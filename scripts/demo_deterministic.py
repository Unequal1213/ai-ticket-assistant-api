"""Run a synthetic demo against a locally running deterministic API."""

import json
import os
import urllib.request

BASE_URL = os.getenv("DEMO_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

SYNTHETIC_TICKETS = (
    ("Delivery delay", "The synthetic parcel has not arrived on the expected day."),
    ("Return request", "I want to return an unused synthetic item."),
    ("Payment error", "Please help: the test payment failed with an error."),
    ("Technical problem", "The demo application crashes on the settings page."),
    ("Change order", "Please change order 12345 before it is processed."),
    ("General question", "Where can I read the support hours?"),
)


def request_json(method: str, path: str, payload: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return json.load(response)


def main() -> None:
    for title, description in SYNTHETIC_TICKETS:
        ticket = request_json(
            "POST",
            "/tickets",
            {"title": title, "description": description},
        )
        analyzed = request_json("POST", f"/tickets/{ticket['id']}/analyze")
        print(json.dumps(analyzed, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
