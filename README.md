# Codex CLI Mobile Bridge

`Codex CLI Mobile Bridge` lets you control a local `codex` CLI from a mobile Flutter chat app. The app behaves like a Codex-style client, but execution stays on your own machine through the local CLI, not the OpenAI API.

## What It Does

- Runs Codex prompts on the machine where the backend is installed
- Returns async job results to a mobile chat UI
- Stores chat history persistently across backend restarts and redeploys
- Supports multiple workspaces and multiple backend servers
- Supports push-to-talk voice notes that transcribe into prompts before execution
- Supports remote access patterns such as USB, Tailscale, and other tunnels

## Stack

- Backend: FastAPI
- Frontend: Flutter
- Execution: local `codex` CLI via `codex exec` and `codex exec resume`
- Transport: REST polling, with optional WebSocket job updates

## Architecture

The backend follows a layered design:

- Transport layer: FastAPI routes and WebSocket endpoint
- Application layer: `MessageService` orchestration
- Domain layer: chat sessions, messages, jobs, repositories
- Infrastructure layer: execution providers, persistence, realtime streaming, network helpers

Execution is provider-driven:

- `LocalExecutionProvider` runs Codex locally through background subprocess jobs
- `LambdaExecutionProvider` is a prepared stub for future remote execution

## Repository Layout

```text
backend/
  app/
    api/
    application/
    domain/
    infrastructure/
frontend/mobile_app/
scripts/
tests/
docker-compose.yml
main.py
```

## Design Review

- Figma board: https://www.figma.com/design/qmN9KrBZgqhvwOjGKyMjPG?node-id=3-2
- HTML source for the imported board: `design/codex-mobile-ux-board.html`

## Requirements

- Python 3.12+
- Flutter SDK
- `uv`
- A working local `codex` CLI installation authenticated on the backend machine

Optional:

- Docker / Docker Compose
- Tailscale for private remote access
- `adb` for Android USB debugging

## Configuration

Copy the template first:

```bash
cp .env.example .env
```

Important variables:

- `BACKEND_MODE=local|lambda`
- `SERVER_NAME=my-machine`
- `CODEX_COMMAND=codex`
- `CODEX_USE_EXEC=true`
- `CODEX_EXEC_ARGS=--skip-git-repo-check --color never --dangerously-bypass-approvals-and-sandbox`
- `CODEX_RESUME_ARGS=--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox`
- `EXECUTION_TIMEOUT_SECONDS=0`
- `PROJECTS_ROOT=/absolute/path/to/your/projects`
- `CHAT_STORE_BACKEND=sqlite|memory`
- `CHAT_STORE_PATH=.data/chat_store.sqlite3`
- `API_HOST=0.0.0.0`
- `API_PORT=8000`
- `API_BASE_URL=http://localhost:8000`
- `TAILSCALE_SOCKET=/path/to/tailscaled.sock`
- `AUDIO_TRANSCRIPTION_BACKEND=auto|disabled|command|openai|faster_whisper`
- `AUDIO_TRANSCRIPTION_COMMAND=/absolute/path/to/your/transcriber-wrapper {file}`
- `AUDIO_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe`
- `AUDIO_TRANSCRIPTION_LOCAL_MODEL=small`
- `OPENAI_API_KEY=...`

Recommended defaults:

- `BACKEND_MODE=local`
- `CODEX_USE_EXEC=true`
- `CODEX_EXEC_ARGS=--skip-git-repo-check --color never --dangerously-bypass-approvals-and-sandbox`
- `CODEX_RESUME_ARGS=--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox`
- `EXECUTION_TIMEOUT_SECONDS=0`
- `CHAT_STORE_BACKEND=sqlite`

The backend uses `codex exec` for new messages and `codex exec resume` for follow-up messages inside the same chat session.

`EXECUTION_TIMEOUT_SECONDS=0` disables the backend execution timeout entirely.

Chat sessions, messages, and job history are stored in SQLite by default. Keep `CHAT_STORE_BACKEND=sqlite` and point `CHAT_STORE_PATH` at a persistent location if you deploy with containers or redeploy often.

Voice-note transcription options:

- `AUDIO_TRANSCRIPTION_BACKEND=auto` is now the default. It prefers a configured command wrapper first, then OpenAI if `OPENAI_API_KEY` is present, and otherwise falls back to local `faster-whisper`.
- `AUDIO_TRANSCRIPTION_BACKEND=command` keeps execution local and lets you call a wrapper script around `whisper`, `faster-whisper`, or another speech-to-text tool. The command should print only the transcript to stdout.
- `AUDIO_TRANSCRIPTION_BACKEND=openai` sends the recorded audio file to OpenAI speech-to-text, then submits the returned transcript to the local Codex CLI.
- `AUDIO_TRANSCRIPTION_BACKEND=faster_whisper` forces the local model path and avoids any external API call.
- `AUDIO_TRANSCRIPTION_BACKEND=disabled` turns the feature off explicitly.

## Run Locally

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
uv pip install -e '.[dev]'
```

Start the backend:

```bash
python main.py
```

This creates the chat database automatically at `.data/chat_store.sqlite3` unless you override `CHAT_STORE_PATH`.

If you want it to keep running after closing the terminal:

```bash
chmod +x scripts/run_backend_detached.sh scripts/stop_backend.sh
./scripts/run_backend_detached.sh
```

That keeps the backend alive after the shell window closes. Logs go to `.run/backend.log`.
Stop it with:

```bash
./scripts/stop_backend.sh
```

Important: this only solves closing the terminal. If the computer sleeps, reboots, or shuts down, the backend stops. For true always-on access, run it on a machine that stays on, or install it as a system service.

The backend exposes:

- `GET /health`
- `GET /workspaces`
- `GET /sessions`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /message`
- `POST /message/audio`
- `POST /sessions/{session_id}/messages`
- `GET /response/{job_id}`
- `GET /ws/jobs/{job_id}`

## Backend Flow

1. Create a chat with `POST /sessions`, or let the first message create one.
2. Send a message.
3. Receive a `job_id` immediately.
4. Poll `GET /response/{job_id}` until it is `completed` or `failed`.
5. Load the full conversation with `GET /sessions/{session_id}`.
6. Send follow-up turns to `POST /sessions/{session_id}/messages`.

Quick test:

```bash
python scripts/test_message_flow.py "Summarize this repository"
```

## Run the Flutter App

Install dependencies:

```bash
cd frontend/mobile_app
flutter pub get
```

Run the app:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Notes:

- Android emulator typically uses `10.0.2.2` for host access. Replace it with your actual server URL when needed.
- iOS simulator can typically use `http://localhost:8000`
- Real devices should use a reachable backend URL, such as a LAN IP, Tailscale URL, or tunnel URL
- Android and iOS will request microphone permission the first time you record a voice note

## Multi-Server Support

The mobile app can store multiple backend servers and switch between them.

Typical setup:

- One backend per computer
- Each backend gets its own `SERVER_NAME`
- Each backend can point at a different `PROJECTS_ROOT`

Examples:

- `SERVER_NAME=personal`
- `SERVER_NAME=workstation`

Add each backend URL in the app from the server picker.

## Workspace-Aware Chats

Each chat session is tied to a workspace directory. When creating a new chat, the app can fetch available projects from `PROJECTS_ROOT` and start the Codex session inside the selected project.

This allows separate chats such as:

- one chat for `project-a`
- one chat for `project-b`
- one chat for `mobile-app`

The mobile UI groups chats by project for easier navigation.

## Remote Access Options

### USB Debugging

Useful for local mobile development:

```bash
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

### Tailscale

Recommended when only your own devices should access the backend over the internet.

High-level flow:

1. Install Tailscale on the backend machine and phone.
2. Sign both devices into the same tailnet.
3. Start the backend locally.
4. Expose the backend through Tailscale Serve if you are using userspace Tailscale.
5. Add the resulting Tailscale URL in the app.

Example:

```bash
tailscale serve --http=80 --bg http://127.0.0.1:8000
```

Then use:

```text
http://your-machine.your-tailnet.ts.net
```

### Other Tunnels

The app can also connect to:

- LAN URLs such as `http://192.168.1.10:8000`
- ngrok URLs
- Cloudflare Tunnel URLs

## Docker

Run the backend with Docker:

```bash
docker compose up --build
```

Host execution is still the preferred setup when the backend needs direct access to the same `codex` CLI installation and credentials as your terminal session.

## Switch to Lambda Later

Set:

```env
BACKEND_MODE=lambda
USE_LAMBDA=true
LAMBDA_ENDPOINT=https://your-lambda-adapter.example.com
```

The repository already includes a replaceable execution provider abstraction so the backend can move from local CLI execution to a remote worker without changing the app or API contracts.

## Testing

Backend tests:

```bash
pytest
```

Flutter checks:

```bash
cd frontend/mobile_app
flutter test
flutter analyze
```

## Development Notes

- The repository is designed for replaceable execution providers
- Job state is currently stored in memory
- Tailscale helpers are included, but network setup still depends on your machine configuration
- Public deployment should add authentication before exposing the backend to the internet

## Security

- This project does not use the OpenAI API for execution
- Audio transcription can optionally use the OpenAI API if you enable `AUDIO_TRANSCRIPTION_BACKEND=openai`
- The backend executes commands on the host machine through the local `codex` CLI
- Do not expose the backend publicly without adding authentication
- Do not commit your `.env` file or any Codex credentials

## License

MIT
