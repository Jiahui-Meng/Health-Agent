import subprocess
import sys
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.codex_cli import CodexCliError, CodexCliService


def _service() -> CodexCliService:
    root = Path(__file__).resolve().parents[2]
    backend_root = root / "backend"
    return CodexCliService(
        cli_bin="codex",
        python_bin=sys.executable,
        workspace_root=str(root),
        backend_root=str(backend_root),
        database_url="sqlite:///./test.db",
    )


def test_status_when_cli_missing(monkeypatch):
    monkeypatch.setattr("app.services.codex_cli.shutil.which", lambda _: None)
    service = _service()
    status = service.status()
    assert status.cli_available is False
    assert status.logged_in is False


def test_status_logged_in(monkeypatch):
    monkeypatch.setattr("app.services.codex_cli.shutil.which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Logged in as user@example.com", stderr=""),
    )
    service = _service()
    status = service.status()
    assert status.cli_available is True
    assert status.logged_in is True
    assert status.account_id == "user@example.com"


def test_exec_with_mcp_extracts_final_content(monkeypatch):
    monkeypatch.setattr("app.services.codex_cli.shutil.which", lambda _: "/usr/bin/codex")
    stdout = '\n'.join(
        [
            '{"type":"thread.started","thread_id":"t1"}',
            '{"type":"message","content":"{\\"summary\\": \\"ok\\", "}',
            '{"type":"message","delta":{"content":"\\"risk_level\\": \\"low\\", \\"next_steps\\": [\\"a\\", \\"b\\"], \\"disclaimer\\": \\"x\\", \\"stage\\": \\"conclusion\\"}"}}',
        ]
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=stdout, stderr=""),
    )
    service = _service()
    content = service.exec_with_mcp(prompt="hello")
    assert "risk_level" in content


def test_exec_with_mcp_extracts_agent_message_item(monkeypatch):
    monkeypatch.setattr("app.services.codex_cli.shutil.which", lambda _: "/usr/bin/codex")
    stdout = '\n'.join(
        [
            '{"type":"thread.started","thread_id":"t1"}',
            '{"type":"turn.started"}',
            '{"type":"item.completed","item":{"id":"item_4","type":"agent_message","text":"{\\"summary\\":\\"ok\\",\\"risk_level\\":\\"low\\",\\"next_steps\\":[],\\"emergency_guidance\\":null,\\"disclaimer\\":\\"x\\",\\"stage\\":\\"intake\\",\\"follow_up_questions\\":[\\"q1\\"]}"}}',
        ]
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=stdout, stderr=""),
    )
    service = _service()
    content = service.exec_with_mcp(prompt="hello")
    assert '"follow_up_questions"' in content


def test_exec_with_mcp_maps_unsupported_model_to_400(monkeypatch):
    monkeypatch.setattr("app.services.codex_cli.shutil.which", lambda _: "/usr/bin/codex")
    error_text = json.dumps(
        {"detail": "The 'gpt-4.1-mini' model is not supported when using Codex with a ChatGPT account."}
    )
    stdout = '\n'.join(
        [
            json.dumps({"type": "error", "message": error_text}),
            json.dumps({"type": "turn.failed", "error": {"message": error_text}}),
        ]
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=stdout, stderr=""),
    )
    service = _service()
    with pytest.raises(CodexCliError) as exc_info:
        service.exec_with_mcp(prompt="hello", model_name="gpt-4.1-mini")
    assert exc_info.value.status_code == 400
