import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import provider_smoke

FULL_SHA = "a" * 40


def completed(
    arguments: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


def valid_inspection(identity: provider_smoke.ImageIdentity) -> dict:
    return {
        "RepoTags": [identity.tag],
        "Created": "2026-08-01T00:00:00Z",
        "Config": {
            "User": "appuser",
            "Labels": {
                "org.opencontainers.image.revision": identity.full_sha,
                "ai.ticket.smoke.commit": identity.full_sha,
                "ai.ticket.smoke.mode": "provider-validation",
            },
        },
    }


def live_args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "confirm_live_smoke": True,
        "expected_provider": "groq",
        "expected_model": "openai/gpt-oss-20b",
        "max_provider_requests": 1,
        "env_file": tmp_path / "provider.env",
        "expected_branch": provider_smoke.EXPECTED_BRANCH,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_image_tag_is_derived_from_full_sha() -> None:
    identity = provider_smoke.image_identity(FULL_SHA)

    assert identity.short_sha == "a" * 12
    assert identity.tag == f"ai-ticket-assistant-api:smoke-{'a' * 12}"
    assert "0acc472" not in identity.tag
    assert "80750e1" not in identity.tag


def test_dirty_tooling_parser_preserves_porcelain_status_columns() -> None:
    outputs = {
        ("git", "rev-parse", "--show-toplevel"): str(provider_smoke.REPOSITORY_ROOT),
        ("git", "branch", "--show-current"): provider_smoke.EXPECTED_BRANCH,
        ("git", "rev-parse", "HEAD"): FULL_SHA,
        ("git", "rev-parse", "--short=12", "HEAD"): FULL_SHA[:12],
        ("git", "status", "--porcelain"): (
            " M README.md\n?? scripts/provider_smoke.py\n"
        ),
    }

    def fake_command(
        arguments: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return completed(arguments, stdout=outputs[tuple(arguments)])

    state = provider_smoke.repository_state(
        require_clean=True,
        allow_dirty_tooling=True,
        command=fake_command,
    )

    assert state.dirty_files == ("README.md", "scripts/provider_smoke.py")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("revision", "b" * 40),
        ("smoke_commit", "b" * 40),
        ("mode", "other"),
        ("user", "root"),
    ],
)
def test_image_metadata_mismatch_blocks_runtime(field: str, value: str) -> None:
    identity = provider_smoke.image_identity(FULL_SHA)
    inspection = valid_inspection(identity)
    if field == "revision":
        inspection["Config"]["Labels"]["org.opencontainers.image.revision"] = value
    elif field == "smoke_commit":
        inspection["Config"]["Labels"]["ai.ticket.smoke.commit"] = value
    elif field == "mode":
        inspection["Config"]["Labels"]["ai.ticket.smoke.mode"] = value
    else:
        inspection["Config"]["User"] = value

    with pytest.raises(provider_smoke.SmokeError):
        provider_smoke.verify_image_metadata(inspection, identity)


def test_missing_image_after_build_is_an_error() -> None:
    identity = provider_smoke.image_identity(FULL_SHA)

    def fake_command(
        arguments: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if arguments[:3] == ["docker", "image", "inspect"]:
            raise provider_smoke.SmokeError("image missing")
        return completed(arguments)

    with pytest.raises(provider_smoke.SmokeError, match="image missing"):
        provider_smoke.build_and_verify_image(identity, command=fake_command)


def test_live_env_is_loaded_after_all_local_gates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    args = live_args(tmp_path)
    state = provider_smoke.RepositoryState(
        provider_smoke.EXPECTED_BRANCH,
        FULL_SHA,
        FULL_SHA[:12],
        (),
    )
    monkeypatch.setattr(
        provider_smoke,
        "repository_state",
        lambda **_: events.append("repository") or state,
    )
    monkeypatch.setattr(
        provider_smoke,
        "run_preflight",
        lambda: events.append("preflight"),
    )
    monkeypatch.setattr(
        provider_smoke,
        "build_and_verify_image",
        lambda identity: events.append("image") or {},
    )
    monkeypatch.setattr(
        provider_smoke,
        "run_runtime",
        lambda identity, **kwargs: events.append(kwargs["mode"]) or {},
    )
    monkeypatch.setattr(
        provider_smoke,
        "validate_live_env_metadata",
        lambda path: events.append("metadata"),
    )
    monkeypatch.setattr(
        provider_smoke,
        "load_live_environment",
        lambda path: events.append("read_env") or {"AI_API_KEY": "placeholder"},
    )
    monkeypatch.setattr(
        provider_smoke,
        "validate_live_environment",
        lambda values, **kwargs: events.append("validate_env"),
    )

    provider_smoke.run_live_mode(args)

    assert events == [
        "repository",
        "preflight",
        "image",
        "rehearsal",
        "metadata",
        "read_env",
        "validate_env",
        "live",
    ]


def test_incomplete_live_command_does_not_read_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_called = False

    def unexpected_read(path: Path) -> dict[str, str]:
        nonlocal read_called
        read_called = True
        return {}

    monkeypatch.setattr(provider_smoke, "load_live_environment", unexpected_read)

    with pytest.raises(provider_smoke.SmokeError):
        provider_smoke.run_live_mode(live_args(tmp_path, confirm_live_smoke=False))

    assert read_called is False


def test_live_env_permissions_must_not_be_wider_than_600(tmp_path: Path) -> None:
    path = tmp_path / "provider.env"
    path.write_text("AI_API_KEY=placeholder\n", encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(provider_smoke.SmokeError, match="permissions"):
        provider_smoke.validate_live_env_metadata(path)


def test_live_env_owner_execute_bit_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "provider.env"
    path.write_text("AI_API_KEY=placeholder\n", encoding="utf-8")
    path.chmod(0o700)

    with pytest.raises(provider_smoke.SmokeError, match="permissions"):
        provider_smoke.validate_live_env_metadata(path)


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("AI_FALLBACK_ENABLED", "true"),
        ("AI_MAX_RETRIES", "1"),
        ("AI_MAX_REPAIRS", "1"),
        ("AI_DAILY_REQUEST_LIMIT", "2"),
        ("AI_MAX_CONCURRENT_REQUESTS", "2"),
    ],
)
def test_live_env_rejects_unsafe_request_policy(
    field: str,
    unsafe_value: str,
) -> None:
    values = {
        "AI_PROVIDER": "llm",
        "AI_API_KEY": "synthetic-placeholder",
        "AI_BASE_URL": provider_smoke.GROQ_BASE_URL,
        "AI_MODEL": "openai/gpt-oss-20b",
        "AI_FALLBACK_ENABLED": "false",
        "AI_MAX_RETRIES": "0",
        "AI_MAX_REPAIRS": "0",
        "AI_DAILY_REQUEST_LIMIT": "1",
        "AI_MAX_CONCURRENT_REQUESTS": "1",
    }
    values[field] = unsafe_value

    with pytest.raises(provider_smoke.SmokeError, match="policy mismatch"):
        provider_smoke.validate_live_environment(
            values,
            expected_model="openai/gpt-oss-20b",
        )


def test_request_limit_greater_than_one_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(provider_smoke.SmokeError, match="requests 1"):
        provider_smoke.validate_live_request_arguments(
            live_args(tmp_path, max_provider_requests=2)
        )


def test_key_value_is_not_printed(capsys: pytest.CaptureFixture[str]) -> None:
    secret_sentinel = "SYNTHETIC_SECRET_MUST_NOT_PRINT"
    values = {
        "AI_PROVIDER": "llm",
        "AI_API_KEY": secret_sentinel,
        "AI_BASE_URL": provider_smoke.GROQ_BASE_URL,
        "AI_MODEL": "openai/gpt-oss-20b",
        "AI_FALLBACK_ENABLED": "false",
        "AI_MAX_RETRIES": "0",
        "AI_MAX_REPAIRS": "0",
        "AI_DAILY_REQUEST_LIMIT": "1",
        "AI_MAX_CONCURRENT_REQUESTS": "1",
    }

    provider_smoke.validate_live_environment(
        values,
        expected_model="openai/gpt-oss-20b",
    )

    assert secret_sentinel not in capsys.readouterr().out


def test_client_has_no_application_imports_or_stale_tags() -> None:
    paths = (
        provider_smoke.CLIENT_PATH,
        Path(provider_smoke.__file__),
        provider_smoke.INSTRUMENT_PATH,
    )
    client_tree = ast.parse(provider_smoke.CLIENT_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(client_tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert "app" not in imported_roots
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "offline-preflight-fix-" not in source
        assert "precommit-runtime-" not in source


def test_client_starts_without_pythonpath_from_arbitrary_cwd(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed_process = subprocess.run(
        [sys.executable, str(provider_smoke.CLIENT_PATH), "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed_process.returncode == 0
    assert "--base-url" in completed_process.stdout


def test_cleanup_runs_when_runtime_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_called = False
    identity = provider_smoke.image_identity(FULL_SHA)

    def fake_cleanup(self: provider_smoke.SmokeResources) -> None:
        nonlocal cleanup_called
        cleanup_called = True

    def failing_command(
        arguments: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        raise provider_smoke.SmokeError("synthetic stop condition")

    monkeypatch.setattr(provider_smoke.SmokeResources, "cleanup", fake_cleanup)

    with pytest.raises(provider_smoke.SmokeError, match="synthetic stop"):
        provider_smoke.run_runtime(
            identity,
            mode="rehearsal",
            command=failing_command,
        )

    assert cleanup_called is True


def test_cleanup_verifies_run_id_labels() -> None:
    calls: list[list[str]] = []

    def fake_command(
        arguments: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        returncode = 1 if "inspect" in arguments else 0
        return completed(arguments, returncode=returncode)

    resources = provider_smoke.SmokeResources(
        provider_smoke.image_identity(FULL_SHA),
        "run123",
        fake_command,
        app_container="app",
        postgres_container="postgres",
        network="network",
        volume="volume",
    )

    resources.cleanup()

    assert any("label=ai.ticket.smoke.run=run123" in arguments for arguments in calls)


def test_preflight_has_exact_named_invariants() -> None:
    assert len(provider_smoke.PREFLIGHT_INVARIANT_NAMES) == len(
        set(provider_smoke.PREFLIGHT_INVARIANT_NAMES)
    )
    assert "PII_EMAIL_BEFORE_PUNCTUATION" in provider_smoke.PREFLIGHT_INVARIANT_NAMES
    assert "PROMPT_STORE_FALSE" in provider_smoke.PREFLIGHT_INVARIANT_NAMES
    assert "PROMPT_STRICT_STRUCTURED_OUTPUT" in (
        provider_smoke.PREFLIGHT_INVARIANT_NAMES
    )


def test_preflight_uses_mock_transport_and_no_external_network(
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider_smoke.run_preflight()

    output = capsys.readouterr().out
    assert "external_provider_requests=0" in output
    assert "PREFLIGHT_MOCK_REQUEST_COUNT_ONE=PASS" in output
