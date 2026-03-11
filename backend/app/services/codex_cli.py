from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ..schemas import ChatAnswer

MCP_SERVER_NAME = "health_agent"


@dataclass
class CodexCliStatus:
    cli_available: bool
    logged_in: bool
    message: str
    account_id: str | None = None


@dataclass
class CodexCliActionResult:
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""


class CodexCliError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class CodexCliService:
    def __init__(
        self,
        cli_bin: str = "codex",
        *,
        python_bin: str,
        workspace_root: str,
        backend_root: str,
        database_url: str,
    ):
        self.cli_bin = cli_bin
        self.python_bin = python_bin
        self.workspace_root = workspace_root
        self.backend_root = backend_root
        self.database_url = database_url
        self.last_mcp_error = ""

    def status(self, timeout_seconds: int = 20) -> CodexCliStatus:
        if not shutil.which(self.cli_bin):
            return CodexCliStatus(
                cli_available=False,
                logged_in=False,
                message=f"CLI '{self.cli_bin}' is not installed or not in PATH.",
            )
        result = self._run([self.cli_bin, "login", "status"], timeout_seconds=timeout_seconds)
        text = result.message
        if result.ok:
            return CodexCliStatus(
                cli_available=True,
                logged_in=True,
                message=text or "Codex CLI is logged in.",
                account_id=_extract_account_id(text),
            )
        lower = text.lower()
        if "not logged in" in lower or "login required" in lower or "unauthorized" in lower:
            return CodexCliStatus(
                cli_available=True,
                logged_in=False,
                message=text or "Codex CLI is not logged in.",
            )
        return CodexCliStatus(
            cli_available=True,
            logged_in=False,
            message=text or "Unable to determine Codex login status.",
        )

    def mcp_status(self) -> tuple[bool, str]:
        if not Path(self.python_bin).exists():
            return False, f"Python executable not found: {self.python_bin}"
        server_entry = Path(self.backend_root) / "app" / "services" / "health_mcp_server.py"
        if not server_entry.exists():
            return False, f"MCP server entrypoint not found: {server_entry}"
        if self.last_mcp_error:
            return True, self.last_mcp_error
        return True, "MCP server is ready."

    def login(self, timeout_seconds: int = 180) -> CodexCliActionResult:
        if not shutil.which(self.cli_bin):
            return CodexCliActionResult(False, f"CLI '{self.cli_bin}' is not installed.")
        return self._run([self.cli_bin, "login"], timeout_seconds=timeout_seconds)

    def logout(self, timeout_seconds: int = 45) -> CodexCliActionResult:
        if not shutil.which(self.cli_bin):
            return CodexCliActionResult(False, f"CLI '{self.cli_bin}' is not installed.")
        return self._run([self.cli_bin, "logout"], timeout_seconds=timeout_seconds)

    def exec_with_mcp(self, prompt: str, model_name: str | None = None, timeout_seconds: int = 90) -> str:
        if not shutil.which(self.cli_bin):
            raise CodexCliError(f"Codex CLI '{self.cli_bin}' is not installed.", status_code=400)

        mcp_available, mcp_message = self.mcp_status()
        if not mcp_available:
            raise CodexCliError(f"MCP server is not available. {mcp_message}", status_code=500)

        with tempfile.TemporaryDirectory(prefix="health-agent-codex-") as tmp_dir:
            schema_path = Path(tmp_dir) / "chat_answer.schema.json"
            output_path = Path(tmp_dir) / "last_message.txt"
            schema = _make_schema_strict(ChatAnswer.model_json_schema())
            schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")

            command = [
                self.cli_bin,
                "exec",
                "--json",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-C",
                self.workspace_root,
                "-c",
                f'mcp_servers.{MCP_SERVER_NAME}.command={json.dumps(self.python_bin)}',
                "-c",
                f'mcp_servers.{MCP_SERVER_NAME}.args={json.dumps(["-m", "app.services.health_mcp_server"])}',
                "-c",
                f"mcp_servers.{MCP_SERVER_NAME}.env={_to_toml_inline_table(self._mcp_env())}",
                "-",
            ]
            if model_name and model_name.strip():
                command[2:2] = ["--model", model_name.strip()]

            result = self._run(command, timeout_seconds=timeout_seconds, input_text=prompt)
            if not result.ok:
                detail = _extract_codex_error(result.stdout or result.message, result.stderr)
                lower = detail.lower()
                self.last_mcp_error = detail
                if "not logged in" in lower or "login required" in lower or "unauthorized" in lower:
                    raise CodexCliError("Codex CLI is not logged in. Please run login first.", status_code=401)
                if "not supported when using codex" in lower or "model is not supported" in lower:
                    raise CodexCliError(detail, status_code=400)
                if "mcp" in lower:
                    raise CodexCliError(f"MCP server/tool error: {detail}", status_code=502)
                raise CodexCliError(f"Codex CLI execution failed: {detail}", status_code=502)

            content = _extract_assistant_content_from_jsonl(result.stdout)
            if not content and output_path.exists():
                content = output_path.read_text(encoding="utf-8").strip()
            if not content:
                self.last_mcp_error = "Codex CLI returned empty assistant output."
                raise CodexCliError("Codex CLI returned empty assistant output.", status_code=502)

            self.last_mcp_error = ""
            return content

    def _mcp_env(self) -> dict[str, str]:
        python_path_parts = [self.backend_root]
        if os.environ.get("PYTHONPATH"):
            python_path_parts.append(os.environ["PYTHONPATH"])
        return {
            "PYTHONPATH": os.pathsep.join(python_path_parts),
            "HEALTH_AGENT_DATABASE_URL": self.database_url,
        }

    def _run(
        self,
        command: list[str],
        timeout_seconds: int,
        input_text: str | None = None,
    ) -> CodexCliActionResult:
        try:
            completed = subprocess.run(
                command,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except FileNotFoundError:
            return CodexCliActionResult(False, f"CLI '{self.cli_bin}' is not installed.")
        except subprocess.TimeoutExpired:
            return CodexCliActionResult(False, "Codex CLI command timed out.")

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        message = stdout or stderr or "No CLI output."
        if completed.returncode != 0:
            return CodexCliActionResult(False, message, stdout=stdout, stderr=stderr)
        return CodexCliActionResult(True, message, stdout=stdout, stderr=stderr)


def _extract_assistant_content_from_jsonl(raw: str) -> str:
    text_chunks: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")
        if event_type == "exec.completed":
            last_message = event.get("last_message")
            if isinstance(last_message, str) and last_message.strip():
                text_chunks.append(last_message)
                continue
        if event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                item_text = item.get("text")
                if isinstance(item_text, str) and item_text.strip():
                    text_chunks.append(item_text)
                    continue

        candidate = event.get("content")
        if isinstance(candidate, str) and candidate.strip():
            text_chunks.append(candidate)
            continue

        delta = event.get("delta")
        if isinstance(delta, dict):
            delta_content = delta.get("content")
            if isinstance(delta_content, str) and delta_content:
                text_chunks.append(delta_content)
                continue

        message = event.get("message")
        if isinstance(message, dict):
            msg_content = message.get("content")
            if isinstance(msg_content, str) and msg_content.strip():
                text_chunks.append(msg_content)
                continue
            if isinstance(msg_content, list):
                for part in msg_content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        text_chunks.append(part["text"])

    merged = "".join(text_chunks).strip()
    if merged:
        return merged
    return raw.strip()


def _extract_codex_error(stdout: str, stderr: str) -> str:
    messages: list[str] = []
    if stderr.strip():
        messages.append(stderr.strip())
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if isinstance(event.get("message"), str):
            messages.append(event["message"])
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "error" and isinstance(item.get("message"), str):
            messages.append(item["message"])
        error = event.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            messages.append(error["message"])
    return "\n".join(dict.fromkeys(msg for msg in messages if msg)).strip() or stdout.strip() or "Unknown Codex CLI error."


def _extract_account_id(text: str) -> str | None:
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
    if email_match:
        return email_match.group(0)
    return None


def _to_toml_inline_table(payload: dict[str, str]) -> str:
    parts = [f"{key} = {json.dumps(value)}" for key, value in payload.items()]
    return "{ " + ", ".join(parts) + " }"


def _make_schema_strict(node):
    if isinstance(node, dict):
        next_node = {key: _make_schema_strict(value) for key, value in node.items()}
        if next_node.get("type") == "object":
            if "additionalProperties" not in next_node:
                next_node["additionalProperties"] = False
            properties = next_node.get("properties")
            if isinstance(properties, dict):
                next_node["required"] = list(properties.keys())
        return next_node
    if isinstance(node, list):
        return [_make_schema_strict(item) for item in node]
    return node
