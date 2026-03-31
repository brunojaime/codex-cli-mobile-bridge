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

This repository is not tied to `/home/brunojaime` or a specific `Projects` folder. The project picker is already driven by `.env`, specifically `PROJECTS_ROOT`.

The only machine-specific values you normally need to change are:

- `SERVER_NAME`
- `PROJECTS_ROOT`
- `CHAT_STORE_PATH` if you want the database somewhere else
- `TAILSCALE_SOCKET` only if you use a userspace Tailscale daemon
- `OPENAI_API_KEY` only if you choose OpenAI-based transcription

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
- `AUDIO_TRANSCRIPTION_MODEL=whisper-1` for OpenAI-only transcription
- `AUDIO_TRANSCRIPTION_LOCAL_MODEL=small`
- `OPENAI_API_KEY=...`

Two values matter most for a fresh machine:

- `PROJECTS_ROOT` must point to the parent folder that contains your repositories. The "Choose Project" sheet lists the direct child directories under that folder.
- `SERVER_NAME` is what the mobile app shows in the server picker.

Recommended defaults:

- `BACKEND_MODE=local`
- `CODEX_USE_EXEC=true`
- `CODEX_EXEC_ARGS=--skip-git-repo-check --color never --dangerously-bypass-approvals-and-sandbox`
- `CODEX_RESUME_ARGS=--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox`
- `EXECUTION_TIMEOUT_SECONDS=0`
- `CHAT_STORE_BACKEND=sqlite`

Example `.env` for another computer:

```env
BACKEND_MODE=local
SERVER_NAME=work-laptop
CODEX_COMMAND=codex
CODEX_USE_EXEC=true
CODEX_EXEC_ARGS=--skip-git-repo-check --color never --dangerously-bypass-approvals-and-sandbox
CODEX_RESUME_ARGS=--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox
CODEX_WORKDIR=.
PROJECTS_ROOT=/home/alice/Documents/Projects
CHAT_STORE_BACKEND=sqlite
CHAT_STORE_PATH=.data/chat_store.sqlite3
TAILSCALE_SOCKET=
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://localhost:8000
EXECUTION_TIMEOUT_SECONDS=0
AUDIO_TRANSCRIPTION_BACKEND=faster_whisper
AUDIO_TRANSCRIPTION_LOCAL_MODEL=small
AUDIO_TRANSCRIPTION_LOCAL_COMPUTE_TYPE=int8
AUDIO_TRANSCRIPTION_LOCAL_DEVICE=auto
OPENAI_API_KEY=
```

The backend uses `codex exec` for new messages and `codex exec resume` for follow-up messages inside the same chat session.

`EXECUTION_TIMEOUT_SECONDS=0` disables the backend execution timeout entirely.

Chat sessions, messages, and job history are stored in SQLite by default. Keep `CHAT_STORE_BACKEND=sqlite` and point `CHAT_STORE_PATH` at a persistent location if you deploy with containers or redeploy often.

Voice-note transcription options:

- `AUDIO_TRANSCRIPTION_BACKEND=faster_whisper` is the recommended local default for this repo. It keeps speech-to-text on your machine and avoids any OpenAI API usage.
- `AUDIO_TRANSCRIPTION_BACKEND=auto` prefers a configured command wrapper first, then OpenAI if `OPENAI_API_KEY` is present, and otherwise falls back to local `faster-whisper`.
- `AUDIO_TRANSCRIPTION_BACKEND=command` keeps execution local and lets you call a wrapper script around `whisper`, `faster-whisper`, or another speech-to-text tool. The command should print only the transcript to stdout.
- `AUDIO_TRANSCRIPTION_BACKEND=openai` sends the recorded audio file to OpenAI speech-to-text, then submits the returned transcript to the local Codex CLI.
- `AUDIO_TRANSCRIPTION_MODEL` only matters for `openai`. It does not affect local `faster-whisper`.
- `AUDIO_TRANSCRIPTION_BACKEND=faster_whisper` forces the local model path and avoids any external API call.
- `AUDIO_TRANSCRIPTION_BACKEND=disabled` turns the feature off explicitly.

## Git HTTPS Snap Fix

If this environment is using the Codex snap-packaged `git`, HTTPS remotes can fail because `git` does not find its remote helpers at the right exec path. This repo includes:

- `scripts/setup_git_https_snap.sh`
- `scripts/rollback_git_https_snap.sh`
- `scripts/test_git_https_snap_setup.sh`

Use the setup script first in preview mode:

```bash
scripts/setup_git_https_snap.sh --dry-run
```

Audit the current environment without changing anything:

```bash
scripts/setup_git_https_snap.sh --check
```

Machine-readable audit output:

```bash
scripts/setup_git_https_snap.sh --check --json
```

The JSON includes:

- `status`
- ordered `checks`
- per-check `result`
- per-check `message`

Formal schema:

- `docs/setup_git_https_snap_check.schema.json`

Apply it for real:

```bash
scripts/setup_git_https_snap.sh
```

Machine-readable setup output:

```bash
scripts/setup_git_https_snap.sh --json
scripts/setup_git_https_snap.sh --dry-run --json
```

Rollback:

```bash
scripts/rollback_git_https_snap.sh
```

Machine-readable rollback output:

```bash
scripts/rollback_git_https_snap.sh --json
scripts/rollback_git_https_snap.sh --dry-run --json
```

For isolated testing without touching your real config, override:

- `BASHRC=/tmp/some-bashrc`
- `GIT_CONFIG_GLOBAL=/tmp/some-gitconfig`

There is also a repeatable non-destructive harness:

```bash
scripts/test_git_https_snap_setup.sh
```

Shell validation for these scripts:

```bash
scripts/lint_git_https_snap_shell.sh
```

That lint step validates shell syntax for the repo-level wrapper plus the script suite, and it also enforces the executable bit on the main command entrypoints:

- `./check_git_https_snap.sh`
- `scripts/setup_git_https_snap.sh`
- `scripts/rollback_git_https_snap.sh`
- `scripts/check_git_https_snap.sh`
- `scripts/validate_check_git_https_snap_json.sh`

Simplest repo-level command for validating everything in order:

```bash
./check_git_https_snap.sh
```

Less noisy success output for humans:

```bash
./check_git_https_snap.sh --quiet
```

Equivalent script path if you want the underlying entrypoint directly:

```bash
scripts/check_git_https_snap.sh
```

That entrypoint runs:

- shell lint/syntax checks for `check_git_https_snap_lib.sh`, `check_git_https_snap.sh`, `setup_git_https_snap.sh`, `rollback_git_https_snap.sh`, `test_git_https_snap_setup.sh`, and `validate_check_git_https_snap_json.sh`
- the non-destructive setup/rollback harness

Machine-readable summary of that entrypoint:

```bash
scripts/check_git_https_snap.sh --json
./check_git_https_snap.sh --json
```

`--quiet` only affects the human-readable mode. It keeps the final success line and any failure output, but suppresses the detailed harness logs when everything passes.
On failure, it keeps a short stage-specific error message instead of dumping the full harness output.

The JSON payload includes:

- `schema_version`
- `status`
- ordered `stages`
- per-stage `result`
- per-stage `message`

The repo-level wrapper `./check_git_https_snap.sh` and all main scripts also support `-h` / `--help` for flags, purpose, and relevant environment variables where applicable.

Exit code semantics:

- `scripts/setup_git_https_snap.sh`
  - exit `0`: setup completed, or `--check` confirmed the environment is fully configured
  - exit non-`0`: preflight failed, setup could not complete, or `--check` found a missing/broken requirement
- `scripts/rollback_git_https_snap.sh`
  - exit `0`: rollback completed, or there was nothing left to remove
  - exit non-`0`: invalid usage or an unexpected rollback failure
- `scripts/check_git_https_snap.sh`
  - exit `0`: lint plus harness passed
  - exit non-`0`: either lint or harness failed; `--json` still reports the failing stage
- `scripts/validate_check_git_https_snap_json.sh`
  - exit `0`: both the success payload and the controlled failure payload validated against the JSON contract
  - exit non-`0`: JSON parse/schema/semantic validation failed in either scenario

Formal schema:

- `docs/check_git_https_snap.schema.json`

The repo-level wrapper keeps the exact same JSON contract and schema as `scripts/check_git_https_snap.sh --json`.

Non-destructive contract validation:

```bash
scripts/validate_check_git_https_snap_json.sh
```

Controlled failure check for the quiet human mode:

```bash
scripts/validate_check_git_https_snap_quiet.sh
```

Schemas:

- audit JSON: `docs/setup_git_https_snap_check.schema.json`
- setup/rollback JSON: `docs/git_https_snap_operation.schema.json`

The setup/rollback JSON includes:

- `status`
- `operation`
- `dry_run`
- `targets`
- `changes`

Each change reports whether it was only detected/planned or actually applied via the `applied` flag.

## Android APK Releases On GitHub

This repository can publish the Android APK to GitHub Releases so you can install updates from your phone without a USB cable.

What is included:

- A GitHub Actions workflow at `.github/workflows/android-release.yml`
- A local helper command at `scripts/publish_android_release.sh`
- A stable release asset name: `codex-mobile.apk`

Recommended flow:

1. Update `frontend/mobile_app/pubspec.yaml` and bump the Flutter version.
2. Commit and push your code changes.
3. Run `./scripts/publish_android_release.sh --push`.
4. GitHub Actions builds the APK and publishes a release for that tag.
5. Download it from:
   `https://github.com/<owner>/<repo>/releases/latest/download/codex-mobile.apk`

Important details:

- If `frontend/mobile_app/android/key.properties` is present, the Android release build uses that keystore.
- If no release keystore is configured, the build falls back to the debug key so the workflow still works for internal testing.
- For stable over-the-air updates, keep the same release keystore forever and always increase the app version in `frontend/mobile_app/pubspec.yaml`.

Optional GitHub repository secrets for proper release signing:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`
- `ANDROID_STORE_PASSWORD`

The workflow decodes the keystore into `frontend/mobile_app/android/upload-keystore.jks` during the build and writes `frontend/mobile_app/android/key.properties` on the runner.

### Local Voice Transcription Setup

This repository already installs `faster-whisper` as part of the Python dependencies. For most local setups, that is the transcription engine you want.

Recommended `.env` values:

```env
AUDIO_TRANSCRIPTION_BACKEND=faster_whisper
AUDIO_TRANSCRIPTION_LOCAL_MODEL=small
AUDIO_TRANSCRIPTION_LOCAL_COMPUTE_TYPE=int8
AUDIO_TRANSCRIPTION_LOCAL_DEVICE=auto
OPENAI_API_KEY=
```

Install system dependencies:

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

macOS with Homebrew:

```bash
brew install ffmpeg
```

Then install the project dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
uv pip install -e '.[dev]'
```

Notes:

- `faster-whisper` is a local Whisper-compatible implementation. It does not use the OpenAI API.
- `AUDIO_TRANSCRIPTION_LOCAL_MODEL=small` is a reasonable CPU default.
- `AUDIO_TRANSCRIPTION_LOCAL_COMPUTE_TYPE=int8` is a good CPU-friendly setting.
- If you have a compatible GPU, you can later tune `AUDIO_TRANSCRIPTION_LOCAL_DEVICE` and compute type for faster inference.
- If you want to use the original OpenAI-hosted Whisper API instead, set `AUDIO_TRANSCRIPTION_BACKEND=openai`, configure `OPENAI_API_KEY`, and choose an OpenAI model such as `whisper-1`.

## Install On Another Computer

Use this flow when you want the same behavior on a second machine.

### 1. Install Prerequisites On The Backend Machine

- Python 3.12+
- `uv`
- `ffmpeg`
- a working `codex` CLI installation authenticated on that machine
- Tailscale if you want remote access from your phone outside USB or LAN

Ubuntu / Debian example:

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg curl
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone The Repo And Configure `.env`

```bash
git clone <your-repo-url>
cd cli-codex-project
cp .env.example .env
```

Then edit `.env` and set at least:

- `SERVER_NAME` to something meaningful such as `home-desktop` or `work-laptop`
- `PROJECTS_ROOT` to the parent folder that contains the repos you want in the project picker
- `TAILSCALE_SOCKET` only if you run userspace Tailscale

Important:

- Do not copy `/home/brunojaime/Documents/Projects` to another machine unless that path is actually correct there.
- The app does not scan recursively. It only lists direct child folders inside `PROJECTS_ROOT`.
- If you want `project-a` and `project-b` to appear in "Choose Project", they must exist as sibling directories under the configured `PROJECTS_ROOT`.

### 3. Install Python Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
uv pip install -e '.[dev]'
```

If `.venv` already exists, do not recreate it unless you want a fresh environment. Just run:

```bash
source .venv/bin/activate
uv pip install -e '.[dev]'
```

### 4. Start The Backend

```bash
source .venv/bin/activate
python main.py
```

At this point the backend should be serving on:

```text
http://localhost:8000
```

Quick checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/workspaces
```

`/health` should show the configured `server_name` and `projects_root`. `/workspaces` should return the folders under `PROJECTS_ROOT`.

If you want the backend to survive closing that shell:

```bash
chmod +x scripts/run_backend_detached.sh scripts/stop_backend.sh
./scripts/run_backend_detached.sh
```

Stop it with:

```bash
./scripts/stop_backend.sh
```

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

You have two valid Tailscale setups in this repo: normal system Tailscale and userspace Tailscale.

#### Standard Tailscale Service

This is the simplest option on a normal Linux laptop or desktop.

1. Install Tailscale on the backend machine.
2. Install Tailscale on the phone or tablet.
3. Log both devices into the same tailnet.
4. Start the backend with `python main.py`.
5. Use the machine's Tailscale IP or MagicDNS name in the mobile app.

Typical Linux flow:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled
sudo tailscale up
tailscale ip -4
```

With the normal system daemon:

- leave `TAILSCALE_SOCKET=` empty in `.env`
- the backend healthcheck can still detect Tailscale through the default CLI
- the mobile app can connect to `http://<tailscale-ip>:8000` or `http://<magic-dns-name>:8000`

Example:

```text
http://home-desktop.tailnet-name.ts.net:8000
```

#### Userspace Tailscale

Use this only if you intentionally run `tailscaled` in userspace mode.

Start the daemon:

```bash
./scripts/run_tailscaled_userspace.sh
```

Then authenticate or reconnect using the userspace socket:

```bash
tailscale --socket="$HOME/.local/share/tailscale-userspace/tailscaled.sock" up
```

In `.env`, set:

```env
TAILSCALE_SOCKET=/home/your-user/.local/share/tailscale-userspace/tailscaled.sock
```

If you use userspace Tailscale, expose the backend through Tailscale Serve:

```bash
tailscale --socket="$HOME/.local/share/tailscale-userspace/tailscaled.sock" serve --http=80 http://127.0.0.1:8000
```

Then use the served MagicDNS URL in the app.

#### What To Install On The Phone

- install the Tailscale mobile app
- sign into the same tailnet
- confirm the backend machine appears as online
- use the backend machine's Tailscale URL in the app server picker

#### What Must Match This Current Setup

For another machine to behave like this one, the backend machine must have:

- a working local `codex` CLI session
- a valid `.env`
- `PROJECTS_ROOT` pointing at the real parent folder for that machine's repos
- the backend running on port `8000`
- Tailscale connected if you want remote access over the tailnet

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
