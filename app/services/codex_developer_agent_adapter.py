"""Official Codex Python SDK adapter for local Developer Agent execution."""
from __future__ import annotations

import asyncio
import importlib.util
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class CodexExecutionResult:
    session_id: str
    status: str
    final_response: str | None
    events: tuple[dict[str, Any], ...]
    duration_ms: int | None
    error: str | None


class CodexDeveloperAgentAdapter:
    """Narrow provider boundary; production always uses the official SDK."""

    async def health(self, repository: Path) -> dict[str, Any]:
        cli = shutil.which("codex")
        if not cli:
            try:
                from codex_cli_bin import bundled_codex_path
                cli = str(bundled_codex_path())
            except (ImportError, FileNotFoundError):
                cli = None
        sdk = importlib.util.find_spec("openai_codex") is not None
        authentication = False
        auth_reason = "Codex CLI was not detected."
        if cli:
            status = await asyncio.to_thread(
                subprocess.run, [cli, "login", "status"],
                cwd=str(repository), capture_output=True, text=True,
                timeout=15, check=False,
            )
            authentication = status.returncode == 0
            auth_reason = (
                "Authenticated Codex session detected."
                if authentication else
                (status.stderr.strip() or status.stdout.strip() or "Authentication unavailable.")
            )
        app_server = False
        app_server_reason = (
            "Official Python SDK is not installed."
            if not sdk else
            "Codex CLI authentication is unavailable."
        )
        if sdk and authentication:
            try:
                from openai_codex import AsyncCodex, CodexConfig
                async with AsyncCodex(CodexConfig(cwd=str(repository))) as codex:
                    await codex.account()
                app_server = True
                app_server_reason = "Official SDK initialized its local app-server."
            except Exception as exc:  # pragma: no cover - provider/environment
                app_server_reason = f"Codex app-server initialization failed: {exc}"
        ready = bool(cli and sdk and authentication and app_server)
        return {
            "cliDetected": bool(cli),
            "sdkDetected": sdk,
            "authenticationAvailable": authentication,
            "appServerReachable": app_server,
            "reason": "Developer Agent is ready." if ready else app_server_reason or auth_reason,
        }

    async def execute(
        self, *, prompt: str, repository: Path,
        on_session: Callable[[str], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> CodexExecutionResult:
        from openai_codex import AsyncCodex, CodexConfig, Sandbox
        from openai_codex._run import _collect_async_turn_result

        async with AsyncCodex(CodexConfig(cwd=str(repository))) as codex:
            thread = await codex.thread_start(
                cwd=str(repository),
                sandbox=Sandbox.workspace_write,
            )
            if on_session:
                on_session(thread.id)
            turn = await thread.turn(prompt, sandbox=Sandbox.workspace_write)

            async def observed_stream():
                async for notification in turn.stream():
                    payload = notification.payload
                    item = getattr(payload, "item", None)
                    if item is not None and on_event:
                        if hasattr(item, "model_dump"):
                            on_event(item.model_dump(mode="json"))
                        else:
                            on_event({
                                "type": type(item).__name__,
                                "detail": str(item),
                            })
                    yield notification

            result = await _collect_async_turn_result(
                observed_stream(), turn_id=turn.id,
            )
            events: list[dict[str, Any]] = []
            for item in result.items:
                if hasattr(item, "model_dump"):
                    events.append(item.model_dump(mode="json"))
                else:
                    events.append({"type": type(item).__name__, "detail": str(item)})
            error = None
            if result.error is not None:
                error = str(result.error)
            return CodexExecutionResult(
                session_id=thread.id,
                status=str(result.status),
                final_response=result.final_response,
                events=tuple(events),
                duration_ms=result.duration_ms,
                error=error,
            )
