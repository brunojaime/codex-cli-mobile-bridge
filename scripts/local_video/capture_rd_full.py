"""Launch only an isolated local RD test server, capture synthetic walkthrough, stop it."""
from pathlib import Path
import argparse,json,os,signal,socket,subprocess,time,urllib.request
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--rd-project',type=Path,required=True);p.add_argument('--node',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=18919);a=p.parse_args()
a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
with socket.socket() as s:
 s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',a.port))
env={**os.environ,'PATH':str(Path(a.node).parent)+os.pathsep+os.environ['PATH'],'RD_E2E_PORT':str(a.port),'RD_E2E_ANTIVIRUS_MODE':'omitted'}
with (a.output/'local-server.log').open('w') as log:
 server=subprocess.Popen([a.node,'node_modules/tsx/dist/cli.mjs','scripts/e2e-server.ts'],cwd=a.rd_project,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  base=f'http://127.0.0.1:{a.port}'
  for _ in range(120):
   if server.poll() is not None:raise RuntimeError('Isolated RD failed to start')
   try:
    with urllib.request.urlopen(base+'/api/health',timeout=1) as r:assert json.load(r)['environment']=='local'
    break
   except OSError:time.sleep(.5)
  else:raise TimeoutError('Isolated RD not ready')
  doc=ROOT.parents[1]/'reports/rd-video-local-v2-20260929/chequeo-DEMO.pdf'
  subprocess.run([a.node,str(ROOT/'record_rd_full.mjs'),str(a.rd_project),str(a.output/'capture'),str(doc),base],check=True)
 finally:
  os.killpg(server.pid,signal.SIGTERM)
  try:server.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(server.pid,signal.SIGKILL);server.wait()
