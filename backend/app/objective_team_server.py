"""Independent read-only monitor: release UI without interrupting active agents.

Only loopback binding is supported. The existing private Tailscale origin
routes /objective-team here; job creation and coordination stay in Bridge.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.request import build_opener, ProxyHandler
from threading import Lock
from time import monotonic

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.app.api.objective_team_routes import router, get_view, get_container
from backend.app.application.services.objective_team_view import ObjectiveTeamView


def create_monitor(root, backend_port, environment):
    app = FastAPI(title="Bridge objective team monitor")
    app.include_router(router)
    app.include_router(router, prefix="/api/v1")
    app.add_middleware(CORSMiddleware, allow_origins=[
        'https://batata-default-string.tail0302c4.ts.net',
        'http://batata-default-string.tail0302c4.ts.net',
        'http://batata-default-string.tail0302c4.ts.net:8118',
        'https://batata-default-string.tail0302c4.ts.net:8443',
    ], allow_methods=['GET'], allow_headers=['Content-Type'])

    registry = {'expires': 0, 'workspaces': []}
    registry_lock = Lock()

    def view():
        try:
            # Cache only the discovery registry, not execution state. Gallery
            # requests must not rescan every Git workspace for each thumbnail.
            with registry_lock:
                if monotonic() >= registry['expires']:
                    opener = build_opener(ProxyHandler({}))
                    with opener.open(f'http://127.0.0.1:{backend_port}/workspaces', timeout=10) as response:
                        items = json.load(response)
                    registry['workspaces'] = [SimpleNamespace(path=w['path'], name=w['name']) for w in items]
                    registry['expires'] = monotonic() + 30
                workspaces = registry['workspaces']
        except Exception:
            raise HTTPException(503, 'No se pudo consultar el registro de proyectos del Bridge') from None
        return ObjectiveTeamView(root, workspaces)

    app.dependency_overrides[get_view] = view
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(
        settings=SimpleNamespace(bridge_environment=environment))
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--backend-port', type=int, required=True)
    parser.add_argument('--environment', choices=['prod', 'dev'], required=True)
    parser.add_argument('--web-root', type=Path)
    parser.add_argument('--dev-web-root', type=Path)
    parser.add_argument('--state-root', default=str(Path.home() / '.local/state/nienfos-objective-team'))
    args = parser.parse_args()
    app = create_monitor(args.state_root, args.backend_port, args.environment)
    if args.web_root:
        from fastapi.staticfiles import StaticFiles
        dev = create_monitor(args.state_root, 8118, 'dev')
        if args.dev_web_root:
            dev.mount('/', StaticFiles(directory=args.dev_web_root, html=True))
        app.mount('/dev', dev)
        app.mount('/', StaticFiles(directory=args.web_root, html=True))
    uvicorn.run(app, host='127.0.0.1', port=args.port)
