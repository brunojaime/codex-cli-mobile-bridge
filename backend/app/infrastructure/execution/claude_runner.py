"""Claude Code stream adapter using the local provider's queue and cancellation."""

from __future__ import annotations

import base64
import json
import time
import mimetypes
import shlex
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.claude_options import translate_options
from backend.app.infrastructure.execution.activity import activity_item, entry
from backend.app.infrastructure.execution import claude_interactions
from backend.app.application.services import project_permissions


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
    results = []
    input_state = {"closing": False, "watchdog": None}
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
            "--include-partial-messages",
            # Echo every user message when Claude consumes it, so steering
            # instructions sent mid-turn can be tracked until answered.
            "--replay-user-messages",
            # Permission prompts, questions and plan approvals reach the
            # front through the stdio control protocol instead of being
            # silently denied.
            "--permission-prompt-tool",
            "stdio",
        ]
        if "--permission-mode" not in option_args:
            # The project's choice (saved from the front) wins over the server default.
            command += [
                "--permission-mode",
                project_permissions.effective_mode(workdir, provider._claude_permission_mode),
            ]
        if provider._claude_chrome:
            command.append("--chrome")
        command += option_args
        if option_context and not message.lstrip().startswith("/"):
            # Slash commands (/compact, /cost…) only run when they are the
            # very first thing in the message, so they never get a prefix.
            message = option_context + "\n\n" + message
        command += [
            "--append-system-prompt",
            "Follow the project's AGENTS.md instructions: read applicable AGENTS.md "
            "files in the workspace and its ancestors before working, and nested ones "
            "before editing their directories. Never print secrets.",
        ]
        if native_id:
            command += ["--resume", native_id.removeprefix("claude:")]
        # Instructions go to the system prompt so the user's message reaches
        # Claude untouched (slash commands such as /compact keep working).
        content = [{"type": "text", "text": message}]
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

        live = {"text": "", "prefix": "", "last_push": 0.0}
        compaction: dict = {}
        stdin_lock = threading.Lock()
        # uuid -> text of steering messages Claude has not consumed yet.
        pending_steers: dict[str, str] = {}

        def send(obj):
            with stdin_lock:
                if process.stdin is None or process.stdin.closed:
                    raise OSError("Claude input is closed.")
                process.stdin.write(json.dumps(obj) + "\n")
                process.stdin.flush()

        def close_stdin_locked():
            input_state["closing"] = True
            try:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
            except OSError:
                pass

        def close_stdin():
            with stdin_lock:
                close_stdin_locked()

        def steer(text):
            """Queue a user message on Claude's live input (real steering).

            Claude takes it at the next pause between tools; if the turn already
            ended it answers it as a continuation in this same process.
            """
            with stdin_lock:
                if (
                    input_state["closing"]
                    or process.stdin is None
                    or process.stdin.closed
                    or process.poll() is not None
                ):
                    return False
                steer_id = str(uuid4())
                process.stdin.write(
                    json.dumps(
                        {
                            "type": "user",
                            "uuid": steer_id,
                            "message": {
                                "role": "user",
                                "content": [{"type": "text", "text": text}],
                            },
                        }
                    )
                    + "\n"
                )
                process.stdin.flush()
                pending_steers[steer_id] = text
                return True

        def mark_consumed(event):
            blocks = (event.get("message") or {}).get("content")
            texts = [
                str(block.get("text", ""))
                for block in (blocks if isinstance(blocks, list) else [])
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            with stdin_lock:
                if event.get("uuid") in pending_steers:
                    pending_steers.pop(event["uuid"], None)
                    return
                for steer_id, text in list(pending_steers.items()):
                    if text in texts:
                        pending_steers.pop(steer_id, None)
                        return

        def finish_or_wait_for_steers(event):
            with stdin_lock:
                results.append(event)
                if not pending_steers:
                    # The turn is over and nothing is waiting: closing stdin
                    # lets Claude exit.
                    close_stdin_locked()
                    return
                if input_state["watchdog"] is None:
                    # Claude answers queued input right after a result; never
                    # leave the process waiting forever if it does not.
                    timer = threading.Timer(180, close_stdin)
                    timer.daemon = True
                    input_state["watchdog"] = timer
                    timer.start()

        def handle_control_request(event):
            request_id = str(event.get("request_id") or "")
            request = event.get("request") or {}
            if request.get("subtype") != "can_use_tool" or not request_id:
                send(
                    {
                        "type": "control_response",
                        "response": {
                            "subtype": "error",
                            "request_id": request_id,
                            "error": "Unsupported request from the bridge front.",
                        },
                    }
                )
                return
            activity = claude_interactions.interaction_activity(request_id, request)
            if parent := event.get("parent_tool_use_id") or request.get("parent_tool_use_id"):
                activity["parent_id"] = str(parent)

            def respond(decision):
                payload, label, status = claude_interactions.build_response(
                    request, decision
                )
                send(
                    {
                        "type": "control_response",
                        "response": {
                            "subtype": "success",
                            "request_id": request_id,
                            "response": payload,
                        },
                    }
                )
                provider._record_activity(
                    job_id, {**activity, "status": status, "resolution": label}
                )
                update(
                    status=JobStatus.RUNNING,
                    phase="Claude working",
                    latest_activity=label,
                )

            provider.register_interaction(job_id, request_id, respond)
            provider._record_activity(job_id, dict(activity))
            update(
                status=JobStatus.RUNNING,
                phase="Waiting for you",
                latest_activity=activity["title"],
            )

        def push_live(force=False):
            now = time.monotonic()
            if not force and now - live["last_push"] < 0.08:
                return
            live["last_push"] = now
            update(
                status=JobStatus.RUNNING,
                phase="Claude responding",
                response=live["prefix"] + live["text"],
                latest_activity="Claude is responding.",
            )

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
                    if kind == "control_request":
                        handle_control_request(event)
                        continue
                    if kind == "control_cancel_request":
                        request_id = str(event.get("request_id") or "")
                        if provider.drop_interaction(job_id, request_id):
                            snapshot = provider.get_snapshot(job_id)
                            previous = next(
                                (
                                    item
                                    for item in snapshot.activities
                                    if item["id"] == f"interaction-{request_id}"
                                ),
                                None,
                            )
                            if previous is not None:
                                provider._record_activity(
                                    job_id,
                                    {
                                        **previous,
                                        "status": "cancelled",
                                        "resolution": "Claude retiró el pedido",
                                    },
                                )
                        continue
                    if kind == "stream_event":
                        stream = event.get("event") or {}
                        stream_type = stream.get("type")
                        if event.get("parent_tool_use_id"):
                            continue
                        if stream_type == "message_start":
                            live["text"] = ""
                        elif stream_type == "content_block_delta":
                            delta = stream.get("delta") or {}
                            if delta.get("type") == "text_delta":
                                live["text"] += delta.get("text", "")
                                push_live()
                        elif stream_type in ("content_block_stop", "message_stop"):
                            if live["text"]:
                                push_live(force=True)
                        continue
                    if kind == "result":
                        result = event
                        if str(event.get("result") or "").strip():
                            live["prefix"] += str(event["result"]).strip() + "\n\n"
                        live["text"] = ""
                        finish_or_wait_for_steers(event)
                    elif kind == "assistant":
                        message_id = str(event.get("message", {}).get("id") or uuid4())
                        parent_id = event.get("parent_tool_use_id")
                        content = (event.get("message") or {}).get("content")
                        for block_index, block in enumerate(
                            content if isinstance(content, list) else []
                        ):
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") == "text":
                                provider._record_activity(
                                    job_id,
                                    entry(
                                        f"{message_id}-{block_index}",
                                        "commentary",
                                        block.get("text", ""),
                                        "",
                                        "completed",
                                        parent_id=parent_id,
                                    ),
                                )
                                if parent_id:
                                    # Subagent text belongs to its own node, never
                                    # to the main response shown in the chat.
                                    continue
                                update(
                                    status=JobStatus.RUNNING,
                                    phase="Claude responding",
                                    response=live["prefix"] + block.get("text", ""),
                                    latest_activity="Claude is responding.",
                                )
                            elif block.get("type") == "tool_use":
                                activity = activity_item(block, completed=False)
                                if activity is not None and parent_id:
                                    activity["parent_id"] = str(parent_id)
                                provider._record_activity(job_id, activity)
                                is_subagent = block.get("name") in {"Task", "Agent"}
                                update(
                                    status=JobStatus.RUNNING,
                                    phase="Claude working",
                                    latest_activity=(
                                        "Subagente: "
                                        + str(
                                            (block.get("input") or {}).get("description")
                                            or "en curso"
                                        )
                                        if is_subagent
                                        else f"Claude: {block.get('name', 'tool')}"
                                    ),
                                )
                    elif kind == "user":
                        if pending_steers:
                            mark_consumed(event)
                        blocks = (event.get("message") or {}).get("content")
                        # After /compact Claude replays the summary as a plain
                        # string; only tool results (lists of blocks) matter.
                        if not isinstance(blocks, list):
                            continue
                        for block in blocks:
                            if not isinstance(block, dict) or block.get("type") != "tool_result":
                                continue
                            tool_id = block.get("tool_use_id")
                            snapshot = provider.get_snapshot(job_id)
                            previous = next(
                                (
                                    item
                                    for item in snapshot.activities
                                    if item["id"] == tool_id
                                ),
                                None,
                            )
                            if previous is not None:
                                content = block.get("content", "")
                                if isinstance(content, list):
                                    content = "\n".join(
                                        str(part.get("text", ""))
                                        for part in content
                                        if isinstance(part, dict)
                                        and part.get("type") == "text"
                                    )
                                provider._record_activity(
                                    job_id,
                                    {
                                        **previous,
                                        "status": "failed"
                                        if block.get("is_error")
                                        else "completed",
                                        "detail": (
                                            previous["detail"] + "\n\n" + str(content)
                                        )[:16000],
                                    },
                                )
                    elif kind == "system" and event.get("subtype") == "compact_boundary":
                        compaction.update(event.get("compact_metadata") or {})
                    elif kind == "system" and event.get("status") == "compacting":
                        update(
                            status=JobStatus.RUNNING,
                            phase="Compacting",
                            latest_activity="Compactando la conversación.",
                        )
                    elif kind == "system":
                        update(
                            status=JobStatus.RUNNING,
                            phase="Claude working",
                            latest_activity="Claude session connected.",
                        )
            except Exception as exc:
                reader_errors.append(str(exc))
                # Never leave Claude waiting on an open stdin nobody reads.
                close_stdin()
                provider._terminate_process_tree(process, kill=True)

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
            with stdin_lock:
                process.stdin.write(payload)
                process.stdin.flush()
        except OSError:
            pass  # Early startup/auth failures are reported through stdout/stderr.
        # Steering opens only after the request itself is on Claude's input.
        with provider._lock:
            provider._claude_steerers[job_id] = steer
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
        # A late instruction is answered as a continuation: keep every answer.
        response = "\n\n".join(
            str(item.get("result") or "").strip()
            for item in results
            if str(item.get("result") or "").strip()
        ) or (result.get("result") or "")
        if len(results) > 1:
            result = _merge_results(results)
        if return_code or result.get("is_error"):
            raise RuntimeError(
                response
                or "; ".join(result.get("errors", []))
                or f"Claude exited with code {return_code}."
            )
        denials = result.get("permission_denials") or []
        if denials and not response.strip():
            raise RuntimeError(
                "Claude requires tool permissions configured on the server. "
                "No permission was bypassed."
            )
        if denials:
            # Claude answered anyway: keep the answer and surface the blocked
            # tools as a warning step instead of failing the whole turn.
            names = sorted(
                {
                    str(item.get("tool_name") or "herramienta")
                    for item in denials
                    if isinstance(item, dict)
                }
            ) or ["herramienta"]
            provider._record_activity(
                job_id,
                entry(
                    "permission-denials",
                    "status",
                    f"{len(denials)} uso(s) de herramienta bloqueado(s) por permisos: "
                    + ", ".join(names),
                    "No se saltó ningún permiso. Configurá los permisos de Claude en "
                    "el servidor si estas herramientas son necesarias.",
                    "warning",
                ),
            )
        if not response.strip() and compaction:
            before = compaction.get("pre_tokens")
            after = compaction.get("post_tokens")
            response = "Conversación compactada" + (
                f": {_compact_number(int(before))} → {_compact_number(int(after))} tokens de contexto."
                if isinstance(before, (int, float)) and isinstance(after, (int, float))
                else "."
            )
        usage_entry = _usage_activity(result)
        if usage_entry is not None:
            provider._record_activity(job_id, usage_entry)
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
        with provider._lock:
            provider._claude_steerers.pop(job_id, None)
        if input_state["watchdog"] is not None:
            input_state["watchdog"].cancel()
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
        provider.clear_interactions(job_id)
        provider._cleanup_paths(cleanup_paths)


def _merge_results(results: list[dict]) -> dict:
    """Fold the results of one process (original turn plus continuations)."""
    merged = dict(results[-1])
    merged["permission_denials"] = [
        denial for item in results for denial in (item.get("permission_denials") or [])
    ]
    usage: dict[str, int] = {}
    for item in results:
        for key, value in (item.get("usage") or {}).items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + int(value)
    merged["usage"] = usage
    for key in ("total_cost_usd", "num_turns", "duration_ms"):
        values = [item.get(key) for item in results if isinstance(item.get(key), (int, float))]
        if values:
            merged[key] = sum(values)
    return merged


def _compact_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def _usage_activity(result: dict) -> dict[str, str] | None:
    """Summarize tokens and cost of a Claude turn as a public activity."""
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    def as_int(key: str) -> int:
        value = usage.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    input_tokens = (
        as_int("input_tokens")
        + as_int("cache_read_input_tokens")
        + as_int("cache_creation_input_tokens")
    )
    output_tokens = as_int("output_tokens")
    cost = result.get("total_cost_usd")
    if not input_tokens and not output_tokens and not isinstance(cost, (int, float)):
        return None
    parts = [
        f"{_compact_number(input_tokens)} entrada",
        f"{_compact_number(output_tokens)} salida",
    ]
    if isinstance(cost, (int, float)):
        parts.append(f"US${cost:.3f}")
    turns = result.get("num_turns")
    detail = json.dumps(
        {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": as_int("cache_read_input_tokens"),
            "total_cost_usd": cost,
            "num_turns": turns,
            "duration_ms": result.get("duration_ms"),
        }
    )
    return entry("usage", "usage", " · ".join(parts), detail, "completed")
