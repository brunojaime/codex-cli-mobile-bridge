"""Claude Code stream adapter using the local provider's queue and cancellation."""

from __future__ import annotations

import base64
import json
import mimetypes
import shlex
import subprocess
import threading
from pathlib import Path

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.claude_options import translate_options


def run_claude(
    provider,
    job_id,
    message,
    *,
    image_paths,
    cleanup_paths,
    provider_session_id,
    model,
    codex_options,
    workdir,
):
    process = None
    result = None
    errors = []
    reader_errors = []
    native_id = provider_session_id

    def update(**kwargs):
        provider._set_state(job_id, provider_session_id=native_id, **kwargs)

    try:
        option_args, option_context = translate_options(codex_options, workdir=workdir)
        command = shlex.split(provider._claude_command)
        if not command:
            raise ValueError("CLAUDE_COMMAND is empty.")
        command += [
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--input-format",
            "stream-json",
            "--model",
            model.removeprefix("claude:"),
            "--effort",
            provider._claude_effort,
        ]
        if "--permission-mode" not in option_args:
            command += ["--permission-mode", provider._claude_permission_mode]
        command += option_args
        if option_context:
            message = option_context + "\n\n" + message
        if native_id:
            command += ["--resume", native_id.removeprefix("claude:")]
        instructions = (
            "Follow the project's AGENTS.md instructions: read applicable AGENTS.md "
            "files in the workspace and its ancestors before working, and nested ones "
            "before editing their directories. Never print secrets.\n\n"
        )
        content = [{"type": "text", "text": instructions + message}]
        for path in image_paths or []:
            media_type = mimetypes.guess_type(path)[0]
            if media_type not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
                raise ValueError(f"Unsupported Claude image type: {media_type}")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(Path(path).read_bytes()).decode(
                            "ascii"
                        ),
                    },
                }
            )
        payload = (
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": content,
                    },
                }
            )
            + "\n"
        )
        update(
            status=JobStatus.RUNNING,
            phase="Starting Claude Code",
            latest_activity="Launching Claude in the current workspace.",
        )
        with provider._lock:
            if provider._is_cancelled(job_id):
                return
            process = subprocess.Popen(
                command,
                cwd=workdir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            provider._processes[job_id] = process

        def read_stdout():
            nonlocal result, native_id
            try:
                for line in process.stdout:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("session_id"):
                        native_id = "claude:" + event["session_id"]
                    kind = event.get("type")
                    if kind == "result":
                        result = event
                    elif kind == "assistant":
                        for block in event.get("message", {}).get("content", []):
                            if block.get("type") == "text":
                                update(
                                    status=JobStatus.RUNNING,
                                    phase="Claude responding",
                                    response=block.get("text", ""),
                                    latest_activity="Claude is responding.",
                                )
                            elif block.get("type") == "tool_use":
                                update(
                                    status=JobStatus.RUNNING,
                                    phase="Claude working",
                                    latest_activity=f"Claude: {block.get('name', 'tool')}",
                                )
                    elif kind == "system":
                        update(
                            status=JobStatus.RUNNING,
                            phase="Claude working",
                            latest_activity="Claude session connected.",
                        )
            except Exception as exc:
                reader_errors.append(str(exc))

        def read_stderr():
            for line in process.stderr:
                errors.append(line.rstrip())
                del errors[:-30]

        readers = [
            threading.Thread(target=read_stdout, daemon=True),
            threading.Thread(target=read_stderr, daemon=True),
        ]
        for reader in readers:
            reader.start()
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except OSError:
            pass  # Early startup/auth failures are reported through stdout/stderr.
        timeout = provider._timeout_seconds
        return_code = process.wait(timeout=timeout if timeout and timeout > 0 else None)
        for reader in readers:
            reader.join(timeout=2)
        if provider._is_cancelled(job_id):
            return
        if reader_errors:
            raise RuntimeError("Invalid Claude stream: " + reader_errors[0])
        if result is None:
            raise RuntimeError(
                "Claude did not return a final result. " + "\n".join(errors)
            )
        response = result.get("result") or ""
        if return_code or result.get("is_error"):
            raise RuntimeError(
                response
                or "; ".join(result.get("errors", []))
                or f"Claude exited with code {return_code}."
            )
        if result.get("permission_denials"):
            raise RuntimeError(
                "Claude requires tool permissions configured on the server. "
                "No permission was bypassed. " + response
            )
        update(
            status=JobStatus.COMPLETED,
            response=response or "Execution completed.",
            phase="Completed",
            latest_activity="Claude returned a final response.",
        )
    except FileNotFoundError:
        update(
            status=JobStatus.FAILED,
            phase="Failed",
            error="Claude Code is not installed. Install it and authenticate on the bridge server, or set CLAUDE_COMMAND.",
        )
    except subprocess.TimeoutExpired:
        provider._terminate_process_tree(process, kill=True)
        update(
            status=JobStatus.FAILED,
            phase="Timed out",
            error="Claude execution timed out.",
        )
    except Exception as exc:
        update(status=JobStatus.FAILED, phase="Failed", error=str(exc))
    finally:
        if process is not None:
            if process.poll() is None:
                provider._terminate_process_tree(process, kill=True)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        with provider._lock:
            provider._processes.pop(job_id, None)
        provider._cleanup_paths(cleanup_paths)
