---
name: codex-mobile-bridge-ubuntu-setup
description: Install, validate, run, and expose the codex-cli-mobile-bridge repository on a fresh Ubuntu/Linux machine. Use when Codex needs to prepare another computer for this repo, document or execute backend startup, configure .env, verify dependencies, run the FastAPI backend, set up standard or userspace Tailscale, install systemd services, or troubleshoot mobile app connectivity to the backend.
---

# Codex Mobile Bridge Ubuntu Setup

## Core Rule

Treat this repo as a host-executed bridge. The backend runs `codex` on the same Linux machine that hosts the FastAPI service, so a successful setup requires a local authenticated Codex CLI installation on that machine. Do not present Docker as the default path unless the user explicitly wants containers; Docker needs extra mounts for Codex credentials and binary access.

## Fresh Ubuntu Setup

From a clean Ubuntu machine, install prerequisites first:

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg curl git
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install Flutter using the user's preferred method and make sure `flutter` is in `PATH`. Install and authenticate the Codex CLI before trying real message execution:

```bash
codex --version
```

Clone and configure the repo:

```bash
git clone <repo-url>
cd codex-cli-mobile-bridge
cp .env.example .env
```

Edit `.env` and set at least:

- `SERVER_NAME`: a human-readable name for this computer, such as `ubuntu-desktop`.
- `PROJECTS_ROOT`: the parent directory whose direct child folders should appear in the mobile project picker.
- `TAILSCALE_SOCKET`: leave empty for normal system Tailscale; set only for userspace Tailscale.
- `API_PORT`: usually `8000`.

Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
uv pip install -e '.[dev]'
```

Run the repo doctor before starting services:

```bash
codex-skills/codex-mobile-bridge-ubuntu-setup/scripts/doctor.sh
```

## Backend Startup

For a foreground development run:

```bash
source .venv/bin/activate
python main.py
```

For the normal detached repo launcher:

```bash
./scripts/run_backend_detached.sh
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/workspaces
```

If the health check fails after the detached launcher claims success, inspect:

```bash
tail -80 .run/backend.log
cat .run/backend.pid
```

The `/health` response should show the configured `server_name` and `projects_root`. The `/workspaces` response should list direct child folders under `PROJECTS_ROOT`; it does not scan recursively.

## Tailscale On Ubuntu

Prefer standard system Tailscale for a normal Ubuntu desktop or server:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled
sudo tailscale up
tailscale status
tailscale ip -4
```

Use the direct backend URL from another Tailnet device:

```text
http://<tailscale-ip>:8000
```

Use userspace Tailscale only when the user cannot or does not want to run the system daemon. In that mode, set `TAILSCALE_SOCKET` in `.env`, then run:

```bash
./scripts/run_tailscaled_userspace.sh
tailscale --socket="$TAILSCALE_SOCKET" up
tailscale --socket="$TAILSCALE_SOCKET" serve --http=80 http://127.0.0.1:8000
tailscale --socket="$TAILSCALE_SOCKET" serve status
```

If `tailscale up` prints an auth URL, give that URL to the user and stop until authentication is completed.

## Systemd Services

Use user services when the backend should survive terminal closure after login:

```bash
./scripts/install_user_services.sh --enable-now
systemctl --user status codex-mobile-bridge-backend.service
```

Run this once if services must keep running after reboot before a graphical login:

```bash
loginctl enable-linger "$USER"
```

Use boot services only when the machine must start the backend at boot without a user session:

```bash
sudo ./scripts/install_boot_services.sh --enable-now
systemctl status codex-mobile-bridge-backend.service
```

If `.env` leaves `TAILSCALE_SOCKET=` empty, the service installers intentionally skip userspace Tailscale services. In that case manage standard Tailscale with `sudo systemctl enable --now tailscaled`.

## Mobile App Validation

Run Flutter checks from the app folder:

```bash
cd frontend/mobile_app
flutter pub get
flutter test
flutter analyze
```

Run the app against the backend URL that matches the test environment:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Use `10.0.2.2` for Android emulator to host backend, `127.0.0.1` for iOS simulator, and `http://<tailscale-ip>:8000` or the configured Tailscale Serve URL for a physical phone over Tailnet.

## Acceptance Checklist

Before telling the user another computer is ready, verify:

- `doctor.sh` reports no failed required checks.
- `pytest` passes from the repo root.
- `flutter test` and `flutter analyze` pass from `frontend/mobile_app`.
- `curl /health` returns the expected `server_name`, `projects_root`, and port.
- `curl /workspaces` returns folders from `PROJECTS_ROOT`.
- The mobile app can connect to the selected backend URL.
- A real chat can start inside a project and produce a Codex response.
- Restarting the backend preserves history when `CHAT_STORE_BACKEND=sqlite`.

## Common Failure Modes

- `codex` not found or not authenticated: install/login Codex on the backend machine.
- Empty project picker: fix `PROJECTS_ROOT`; only direct child folders are listed.
- Backend works locally but phone cannot connect: check firewall, LAN routing, Tailscale status, and whether the phone is using the right `API_BASE_URL`.
- Tailscale Serve missing: run `tailscale serve status` and configure Serve to `http://127.0.0.1:8000`.
- Service starts but backend fails: inspect `.run/backend.log` for launcher runs, or `journalctl --user -u codex-mobile-bridge-backend.service` for user services.
