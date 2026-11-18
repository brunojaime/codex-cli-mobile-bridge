"""Isolated RD login tutorial harness; synthetic credentials and captured mail only."""
import argparse
import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--rd-project',type=Path,default=Path('/home/batata/Projects/rd-gestion-hse/tmp/document-renewal-dev'))
p.add_argument('--node',default='/home/batata/.npm/_npx/5705de4b80ce9477/node_modules/node/bin/node')
p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=18923)
p.add_argument('--offline-provider',type=Path,help='Reuse prior public-provider captures during regression tests')
a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
with socket.socket() as s:
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',a.port))
project=a.rd_project.resolve()
# Adapt only the existing isolated test launcher, never product source or live settings.
source=(project/'scripts/e2e-server.ts').read_text()
source=source.replace("const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');",'const root = '+json.dumps(str(project))+';')
source=source.replace("value: 'local-e2e-session-secret'","value: 'local-e2e-session-secret-at-least-32-characters'")
source=source.replace("value: `http://127.0.0.1:${testPort}`","value: 'https://rd-login-demo.invalid'")
source=source.replace("DEMO_ACCESS_CODE: {", "ZOHO_LOGIN_ENABLED: { type: 'text', value: 'true' },\nZOHO_REGION: { type: 'text', value: 'us' },\nZOHO_LOGIN_DOMAIN: { type: 'text', value: 'example.invalid' },\nZOHO_CLIENT_ID: { type: 'text', value: 'synthetic-video-client' },\nZOHO_CLIENT_SECRET: { type: 'text', value: 'synthetic-video-secret' },\nDEMO_ACCESS_CODE: {")
auth=(project/'apps/api-cloudflare/src/auth-email.ts').read_text()
helpers=auth[auth.index('function escapeHtml'):auth.index('async function sendEmail')]
source="import { createHmac } from 'node:crypto';\nlet demoDatabase: any;\n"+helpers+'\n'+source
source=source.replace("const database = await activeServer.getD1Database('DB', 'rd-gestion-hse-local');", "const database = await activeServer.getD1Database('DB', 'rd-gestion-hse-local'); demoDatabase = database;")
source=source.replace("const pathname = decodeURIComponent(new URL(request.url).pathname);",'''const pathname = decodeURIComponent(new URL(request.url).pathname);
  if (pathname === '/__demo/mail' || pathname === '/__demo/evidence') {
    const row = await demoDatabase.prepare(`SELECT o.*, c.consumed_at, c.invalidated_at, c.expires_at FROM auth_email_outbox o JOIN auth_email_challenges c ON c.id=o.challenge_id WHERE o.template='password_recovery' ORDER BY o.created_at DESC LIMIT 1`).first();
    if (!row) return new Response('No captured recovery message', {status:404});
    const token=createHmac('sha256','local-e2e-auth-challenge-key-with-32-characters').update('rd-gestion-hse-auth-email-v1'+String.fromCharCode(0)+row.challenge_id).digest('base64url');
    const link=`http://127.0.0.1:${testPort}/restablecer?token=${token}`;
    if (pathname === '/__demo/evidence') return Response.json({recipient:row.recipient_email,template:row.template,consumed:!!row.consumed_at,expires_at:row.expires_at,sent_real_mail:false});
    const content=emailContent(row,link);
    return new Response(content.html.replace('<body ', '<body data-demo="true" ').replace('<table role="presentation"', '<p style="text-align:center;font:12px Arial;color:#527084">DEMO · Vista del mensaje de recuperación</p><table role="presentation"'),{headers:{'content-type':'text/html; charset=utf-8'}});
  }''')
source=source.replace('await activeServer.setOptions(optionsForPort(testPort));', "await activeServer.setOptions(optionsForPort(testPort)); demoDatabase = await activeServer.getD1Database('DB', 'rd-gestion-hse-local');")
launcher=project/f'.wrangler/video-login-{a.port}.ts';launcher.parent.mkdir(exist_ok=True);launcher.write_text(source)
env={**os.environ,'PATH':str(Path(a.node).parent)+os.pathsep+os.environ['PATH'],'RD_E2E_PORT':str(a.port),'RD_E2E_ANTIVIRUS_MODE':'omitted'}
try:
    with (a.output/'local-server.log').open('w') as log:
        server=subprocess.Popen([a.node,'node_modules/tsx/dist/cli.mjs',str(launcher)],cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            base=f'http://127.0.0.1:{a.port}'
            for _ in range(180):
                if server.poll() is not None:raise RuntimeError('Local RD failed to start; inspect local-server.log')
                try:
                    with urllib.request.urlopen(base+'/api/health',timeout=1) as r:assert json.load(r)['environment']=='local'
                    break
                except OSError:time.sleep(.5)
            else:raise TimeoutError('Local RD not ready')
            cmd=[a.node,str(HERE/'record_rd_login.mjs'),str(project),str(a.output/'capture'),base]
            if a.offline_provider:cmd.append(str(a.offline_provider.resolve()))
            subprocess.run(cmd,check=True)
        finally:
            if server.poll() is None:
                os.killpg(server.pid,signal.SIGTERM)
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(server.pid,signal.SIGKILL);server.wait()
finally:
    launcher.unlink(missing_ok=True)
