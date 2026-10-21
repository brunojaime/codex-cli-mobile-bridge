"""Repeat the local RD tutorial without invoking Codex or a model API."""
from pathlib import Path
import argparse, json, os, shutil, subprocess, sys, time, urllib.request, socket, signal
ROOT=Path(__file__).resolve().parent
LAB=Path.home()/'.local/share/rd-video-lab'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rd-project',type=Path)
    p.add_argument('--node',default=shutil.which('node'))
    p.add_argument('--port',type=int,default=18879)
    p.add_argument('--v2',action='store_true',help='Smoother capture with local speech/action timing')
    p.add_argument('--fast',action='store_true',help='Explicit speed request: Peter instead of voz 1')
    p.add_argument('--reuse-capture',action='store_true',help='Reuse existing recorded UI')
    a=p.parse_args()
    if a.v2 and a.fast: p.error('V2 uses reviewed voz-1 timing; use --fast without --v2 for Peter')
    started=time.perf_counter(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    python=LAB/('pocket-env' if a.fast else 'venv')/'bin/python'
    subprocess.run([str(python),str(ROOT/'voice.py'),str(ROOT/'rd-documents.json'),'--output',str(out/'audio'),*(['--fast'] if a.fast else [])],check=True)
    if a.v2:
        subprocess.run([str(LAB/'venv/bin/python'),str(ROOT/'align.py'),'--output',str(out)],check=True)
    if not a.reuse_capture:
        if not a.rd_project or not a.node: p.error('--rd-project and Node 22+ are required to record')
        from PIL import Image, ImageDraw
        im=Image.new('RGB',(800,1000),'white'); d=ImageDraw.Draw(im)
        d.text((50,80),'RD DEMO - Chequeo de extintores\nEmpresa DEMO\nDocumento ficticio para tutorial',fill='black')
        document=out/'chequeo-DEMO.pdf'; im.save(document,'PDF')
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            probe.bind(('127.0.0.1',a.port))
        base=f'http://127.0.0.1:{a.port}'
        env={**os.environ,'PATH':str(Path(a.node).parent)+os.pathsep+os.environ['PATH'],
             'RD_E2E_PORT':str(a.port),'RD_E2E_ANTIVIRUS_MODE':'omitted'}
        with (out/'local-server.log').open('w') as log:
            server=subprocess.Popen([a.node,'node_modules/tsx/dist/cli.mjs','scripts/e2e-server.ts'],cwd=a.rd_project,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                for _ in range(120):
                    if server.poll() is not None: raise RuntimeError('Local demo server failed; inspect local-server.log')
                    try:
                        with urllib.request.urlopen(base+'/api/health',timeout=1) as response:
                            assert json.load(response)['environment']=='local'
                        break
                    except OSError: time.sleep(.5)
                else: raise TimeoutError('Local demo server did not start')
                subprocess.run([a.node,str(ROOT/('record_rd_v2.mjs' if a.v2 else 'record_rd.mjs')),str(a.rd_project.resolve()),str(out/'capture'),str(document),base],check=True)
            finally:
                os.killpg(server.pid,signal.SIGTERM)
                try: server.wait(timeout=15)
                except subprocess.TimeoutExpired: os.killpg(server.pid,signal.SIGKILL); server.wait()
    subprocess.run([str(LAB/'venv/bin/python'),str(ROOT/('render_v2.py' if a.v2 else 'render.py')),'--output',str(out)],check=True)
    (out/'run.json').write_text(json.dumps({'edition':2 if a.v2 else 1,'completed':True,'seconds':time.perf_counter()-started,'reuse_capture':a.reuse_capture,'explicit_fast':a.fast,'voice':'peter-fast' if a.fast else 'voz-1','model_api_integration':'none'},indent=2)+'\n')
if __name__=='__main__': main()
