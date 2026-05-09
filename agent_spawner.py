"""Codex CLI process spawning and NDJSON event streaming."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterator, TextIO


CODEX_BIN = "codex"


class CodexSpawnError(RuntimeError):
    """Raised when the Codex CLI process cannot be started."""


@dataclass(frozen=True)
class StreamEvent:
    """Represents one parsed event or transport-level relay error."""

    kind: str
    payload: dict
    raw_line: str | None = None


PopenFactory = Callable[..., subprocess.Popen]


def build_codex_command(prompt: str, workdir: str, codex_thread_id: str | None = None) -> list[str]:
    """Build the Codex CLI argv for a fresh or resumed session."""
    if codex_thread_id:
        return [CODEX_BIN, "-a", "never", "exec", "resume", codex_thread_id, "--json", prompt]
    return [CODEX_BIN, "-a", "never", "exec", "--json", "-C", workdir, prompt]


def start_codex_process(
    prompt: str,
    workdir: str,
    codex_thread_id: str | None = None,
    popen_factory: PopenFactory = subprocess.Popen,
) -> "CodexProcess":
    """Start Codex and return a wrapper that streams NDJSON events."""
    command = build_codex_command(prompt=prompt, workdir=workdir, codex_thread_id=codex_thread_id)
    try:
        process = popen_factory(
            command,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise CodexSpawnError(f"failed to start Codex CLI: {exc}") from exc

    return CodexProcess(process=process, command=command)


@dataclass
class CodexProcess:
    """Thin wrapper around a running Codex subprocess."""

    process: subprocess.Popen
    command: list[str]
    codex_thread_id: str | None = None

    def iter_events(self) -> Iterator[StreamEvent]:
        """Yield parsed NDJSON events and transport-level errors."""
        stdout = self.process.stdout
        if stdout is None:
            yield StreamEvent(
                kind="relay_error",
                payload={"reason": "missing_stdout", "message": "Codex process stdout pipe is unavailable."},
            )
            return

        yield from self._iter_stdout_events(stdout)
        exit_code = self.process.wait()
        if exit_code != 0:
            yield StreamEvent(
                kind="relay_error",
                payload={
                    "reason": "process_exit",
                    "message": f"Codex exited with status {exit_code}.",
                    "exit_code": exit_code,
                    "stderr": self._read_stderr(),
                },
            )

    def _iter_stdout_events(self, stdout: TextIO) -> Iterator[StreamEvent]:
        for line in stdout:
            raw_line = line.rstrip("\n")
            if not raw_line.strip():
                continue

            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                yield StreamEvent(
                    kind="relay_error",
                    payload={
                        "reason": "invalid_json_line",
                        "message": f"Failed to decode Codex JSON line: {exc.msg}.",
                    },
                    raw_line=raw_line,
                )
                continue

            self._remember_thread_id(event)
            yield StreamEvent(kind="raw_event", payload=event, raw_line=raw_line)

    def _remember_thread_id(self, event: dict) -> None:
        if event.get("type") != "thread.started":
            return
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            self.codex_thread_id = thread_id

    def _read_stderr(self) -> str:
        stderr = self.process.stderr
        if stderr is None:
            return ""
        return stderr.read().strip()
