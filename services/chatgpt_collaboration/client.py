"""Register a sent ChatGPT request and release the current Codex execution."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def environment_defaults(choice, cwd=None, environ=None):
    environ = os.environ if environ is None else environ
    if choice == 'auto':
        inherited = environ.get('CODEX_CHATGPT_ENVIRONMENT') or environ.get('BRIDGE_ENVIRONMENT')
        if inherited in {'dev', 'prod'}:
            choice = inherited
        else:
            # The DEV launcher sets BRIDGE_ENVIRONMENT. For manually launched stage
            # sessions, use the authoritative stage path instead of a folder-name guess.
            choice = 'prod'
            folder = Path(cwd or Path.cwd()).resolve()
            try:
                cached = json.loads((Path.home()/'.local/share/chatgpt-collaboration/dev-routing.json').read_text())
                if any(folder.is_relative_to(Path(path).resolve()) for path in cached.get('workspace_paths', [])):
                    choice = 'dev'
            except (OSError, ValueError, TypeError):
                pass
            try:
                with urlopen('http://127.0.0.1:8118/health', timeout=3) as response:
                    identity = json.load(response).get('environment_identity') or {}
                stage = identity.get('worktree_path')
                folder = Path(cwd or Path.cwd()).resolve()
                if identity.get('environment') == 'dev' and stage and folder.is_relative_to(Path(stage).resolve()):
                    choice = 'dev'
            except (OSError, ValueError):
                pass
    suffix = 'backend-dev' if choice == 'dev' else 'backend'
    port = 8167 if choice == 'dev' else 8166
    return choice, 'http://127.0.0.1:' + str(port), Path.home()/'.local/share/chatgpt-collaboration'/suffix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=['auto', 'prod', 'dev'], default='auto')
    parser.add_argument('--url')
    parser.add_argument('--state', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    register = commands.add_parser('register')
    register.add_argument('--run-folder', required=True)
    register.add_argument('--session-id')
    register.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    register.add_argument('--chatgpt-url', required=True)
    register.add_argument('--continue-with', required=True)
    register.add_argument('--timeout', type=int, default=1800)
    register.add_argument('--delivery-mode', choices=['supervised', 'github'], default='supervised')
    register.add_argument('--write-probe-run-id')
    register.add_argument('--recovery-after', type=int, default=300)
    commands.add_parser('list')
    commands.add_parser('health')
    defer = commands.add_parser('defer', help='Report observed ongoing generation from the active recovery')
    defer.add_argument('run_id')
    defer.add_argument('--job-id', required=True)
    reconcile = commands.add_parser('reconcile', help='Acknowledge inspected completed work; verifies result, never resumes')
    reconcile.add_argument('run_id')
    reconcile.add_argument('--job-id', required=True)
    for name in ('status', 'retry', 'cancel', 'recover'):
        commands.add_parser(name).add_argument('run_id')
    args = parser.parse_args()
    environment, default_url, default_state = environment_defaults(args.environment)
    args.url = args.url or default_url
    args.state = args.state or default_state
    if environment == 'dev' and args.url.rstrip('/') != 'http://127.0.0.1:8167':
        parser.error('DEV must use its dedicated collaboration endpoint on port 8167')
    parsed = urlparse(args.url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        parser.error('API URL must use loopback HTTP')
    payload = None
    path = '/tasks'
    method = 'GET'
    if args.command == 'register':
        method = 'POST'
        payload = dict(run_folder=args.run_folder, session_id=args.session_id, thread_id=args.thread_id,
                       conversation_url=args.chatgpt_url, continuation=args.continue_with, timeout_seconds=args.timeout,
                       delivery_mode=args.delivery_mode, write_probe_run_id=args.write_probe_run_id,
                       recovery_after_seconds=args.recovery_after)
    elif args.command == 'health':
        path = '/health'
    elif args.command != 'list':
        if not args.run_id.replace('-', '').replace('_', '').isalnum():
            parser.error('Invalid run ID')
        path += '/' + args.run_id
        if args.command != 'status':
            method = 'POST'
            path += '/' + args.command
            if args.command in {'defer', 'reconcile'}:
                payload = {'job_id': args.job_id}
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(args.url.rstrip('/')+path, data=data, method=method)
    if path != '/health':
        token = (args.state/'api.token').read_text().strip()
        req.add_header('Authorization', 'Bearer '+token)
    req.add_header('Content-Type', 'application/json')
    try:
        with urlopen(req, timeout=120) as response:
            print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
    except HTTPError as exc:
        print(exc.read().decode())
        raise SystemExit(2)


if __name__ == '__main__':
    main()
