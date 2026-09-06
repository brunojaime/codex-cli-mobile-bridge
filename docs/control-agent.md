# Codex Mobile Control Agent

The Control Agent is a small FastAPI process that stays independent from the
Codex Bridge backends. It never invokes an LLM to inspect or restart a service.

## Local layout

| Environment | systemd user unit | Port | Data |
| --- | --- | --- | --- |
| Production | `codex-mobile-bridge-backend.service` | 8000 | Existing `.env` paths |
| Development | `codex-mobile-bridge-dev.service` | 8001 | `.data/dev/` |
| Control | `codex-mobile-control.service` | 8010 | In-memory action state |

Production keeps its existing unit name so installing the controller does not
interrupt the currently running backend.

## Install

Install the unit files without starting anything:

```bash
scripts/install_control_services.sh
```

Install and start Control plus Development:

```bash
scripts/install_control_services.sh --enable-now
```

The installer creates `.control.env` with a random bearer token and `.env.dev`
with isolated development ports and storage. Both files are gitignored.

Production is not restarted by this installer. Existing Codex runs continue.

## Mobile connection

1. Open **Operations** from the app bar.
2. Use `https://<tailscale-dns-name>/ops` as the Control URL. When the selected
   Bridge URL already uses Tailscale Serve, the app derives this automatically.
3. Read the token locally with `scripts/show_control_token.sh` and paste it once.

The app stores the URL and token inside its private application preferences.
Tailscale remains the network access boundary; the bearer token adds a second
authentication layer.

## Deterministic restart behavior

A safe restart performs these fixed operations:

1. `POST /maintenance/drain` on the selected backend.
2. Poll until `ready_to_restart=true`.
3. Run `systemctl --user restart` for the environment's preconfigured unit.
4. Poll `/health` until the backend recovers.

If the backend is already unreachable, safe restart treats it as recovery and
goes directly to the allowlisted `systemctl` operation. Force restart skips
drain explicitly and requires confirmation in the mobile app.

The API never accepts a shell command or arbitrary unit name. The only targets
are those loaded at Control Agent startup.

## Checks

```bash
systemctl --user status codex-mobile-control.service
systemctl --user status codex-mobile-bridge-dev.service
curl -H "Authorization: Bearer $(scripts/show_control_token.sh)" \
  http://127.0.0.1:8010/environments
```

Do not add a mobile action that restarts `tailscaled`; Tailscale is the recovery
channel used to reach the machine.
