# Sebastian Secondary Codex Bridge Setup

This machine is prepared to run a second Codex Mobile Bridge instance for
Sebastian without sharing Bruno's Codex home, projects, chat database, or
Tailscale identity.

## What Bruno Runs On This Computer

From the current repo:

```bash
cd /home/batata/Projects/codex-cli-mobile-bridge
sudo ./scripts/setup_secondary_linux_user.sh
```

The script creates:

- Linux user: `sebastian-buenafont`
- Backend repo: `/home/sebastian-buenafont/codex-cli-mobile-bridge`
- Projects root: `/home/sebastian-buenafont/Projects`
- Backend port: `8001`
- Tailscale socket: `/home/sebastian-buenafont/.local/share/tailscale-userspace/tailscaled.sock`

It also copies this working tree into Sebastian's home, creates a Python venv,
installs the backend, enables lingering, and starts the backend plus userspace
Tailscale services when the user systemd manager is reachable.

## What Sebastian Authenticates

After the script finishes:

```bash
sudo -iu sebastian-buenafont codex login
```

Then authenticate Tailscale with Sebastian's Tailscale account:

```bash
sudo -iu sebastian-buenafont
tailscale --socket=/home/sebastian-buenafont/.local/share/tailscale-userspace/tailscaled.sock up --hostname=codex-sebastian-buenafont
systemctl --user enable --now codex-mobile-bridge-tailscale-serve.service
tailscale --socket=/home/sebastian-buenafont/.local/share/tailscale-userspace/tailscaled.sock serve status
```

## Local Verification

```bash
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:8001/workspaces
```

If `/workspaces` is empty, add project folders directly under:

```bash
/home/sebastian-buenafont/Projects
```

## Apps Sebastian Should Install

- Tailscale on the phone, logged into Sebastian's Tailscale account.
- The Codex Mobile Bridge mobile app APK, the same app Bruno uses.
- GitHub mobile or browser access only if he needs to approve GitHub auth,
  inspect repos, or manage PRs from the phone.
- A password manager or authenticator app if his Codex/OpenAI, GitHub, or
  Tailscale login requires MFA.

## App Server Profile

In the mobile app, add a new server profile using Sebastian's Tailscale Serve
URL or Tailscale IP after authentication. Keep Bruno's profile separate from
Sebastian's profile.

Expected local backend URL on this computer:

```text
http://127.0.0.1:8001
```

