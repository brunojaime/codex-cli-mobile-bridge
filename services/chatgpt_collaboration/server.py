"""Loopback-only collaboration backend; polling never keeps a Codex process alive."""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import threading
from urllib.parse import urlparse

from .core import Bridge, Conflict, GithubResult, Monitor, Store


def public(row):
    return {k: v for k, v in row.items() if k not in {'continuation', 'resume_payload', 'private_folder', 'recovery_payload', 'attention_payload'}}


def build_server(monitor, token, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log request bodies, bearer tokens or conversation URLs.

        def reply(self, status, data):
            content = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)

        def handle_request(self):
            path = urlparse(self.path).path
            if self.command == 'GET' and path == '/health':
                return self.reply(200, {'status': 'ok', 'service': 'chatgpt-collaboration',
                                        'bridge_environment': monitor.bridge_environment,
                                        'bridge_url': getattr(monitor.bridge, 'url', None),
                                        'required_project': monitor.required_project,
                                        'required_repository': monitor.required_repository,
                                        'recovery_protocol': 2,
                                        'generation_wait_supported': True,
                                        'attention_required': [r['id'] for r in monitor.store.list() if r['state'] in {'needs_attention', 'timed_out'}],
                                        'states': dict(Counter(r['state'] for r in monitor.store.list()))})
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                return self.reply(401, {'error': 'unauthorized'})
            try:
                if self.command == 'GET' and path == '/tasks':
                    return self.reply(200, [public(row) for row in monitor.store.list()])
                parts = path.strip('/').split('/')
                if self.command == 'GET' and len(parts) == 2 and parts[0] == 'tasks':
                    return self.reply(200, public(monitor.store.get(parts[1])))
                if self.command == 'POST' and path == '/tasks':
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 64000:
                        return self.reply(413, {'error': 'body_size'})
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError('Expected an object')
                    return self.reply(202, public(monitor.register(payload)))
                if self.command == 'POST' and len(parts) == 3 and parts[0] == 'tasks' and parts[2] in {'defer', 'reconcile'}:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 1000:
                        return self.reply(413, {'error': 'body_size'})
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError('Expected an object')
                    return self.reply(200, public(getattr(monitor, parts[2])(parts[1], payload['job_id'])))
                if self.command == 'POST' and len(parts) == 3 and parts[0] == 'tasks' and parts[2] in {'retry', 'cancel', 'recover'}:
                    return self.reply(200, public(getattr(monitor, parts[2])(parts[1])))
                return self.reply(404, {'error': 'not_found'})
            except Conflict as exc:
                return self.reply(409, {'error': str(exc)})
            except KeyError:
                return self.reply(404, {'error': 'task_or_required_field_not_found'})
            except (ValueError, OSError) as exc:
                return self.reply(422, {'error': str(exc)})
            except Exception:
                return self.reply(503, {'error': 'dependency_unavailable'})

        do_GET = handle_request
        do_POST = handle_request

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, default=Path.home()/'.local/share/chatgpt-collaboration/backend')
    p.add_argument('--skill-script', type=Path, default=Path.home()/'.codex/skills/chatgpt-project-collaboration/scripts/exchange.py')
    p.add_argument('--bridge-url', default='http://127.0.0.1:8000')
    p.add_argument('--port', type=int, default=8166)
    p.add_argument('--required-project')
    p.add_argument('--required-repository')
    p.add_argument('--bridge-environment', choices=['prod', 'dev'])
    p.add_argument('--interval', type=int, default=30)
    args = p.parse_args()
    os.umask(0o077)
    store = Store(args.state)
    with (store.root/'monitor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        token_file = store.root/'api.token'
        if not token_file.exists():
            token_file.write_text(secrets.token_urlsafe(48))
        os.chmod(token_file, 0o600)
        if not args.skill_script.is_file():
            raise SystemExit('Install the collaboration skill first')
        monitor = Monitor(store, Bridge(args.bridge_url), GithubResult(args.skill_script), args.interval,
                          required_project=args.required_project, required_repository=args.required_repository,
                          bridge_environment=args.bridge_environment)
        server = build_server(monitor, token_file.read_text().strip(), args.port)
        server.daemon_threads = True
        stop = threading.Event()

        def tick():
            while not stop.is_set():
                try:
                    monitor.tick()
                except Exception as exc:
                    print(json.dumps({'event': 'monitor_error', 'type': type(exc).__name__}), flush=True)
                stop.wait(2)

        worker = threading.Thread(target=tick, daemon=True, name='chatgpt-result-monitor')
        worker.start()

        def shutdown(*_):
            stop.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        print(json.dumps({'event': 'started', 'port': args.port, 'interval': args.interval}), flush=True)
        try:
            server.serve_forever(poll_interval=.5)
        finally:
            stop.set()
            server.server_close()
            worker.join(timeout=105)


if __name__ == '__main__':
    main()
