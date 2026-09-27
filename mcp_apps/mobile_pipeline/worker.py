from pathlib import Path
import fcntl, hashlib, json, os, re, subprocess, sys
from .server import STATE, ENGINE, _node
job=sys.argv[1]
if not re.fullmatch(r'[a-f0-9-]{36}',job):raise ValueError('Invalid job')
path=STATE/job
request=json.loads((path/'request.json').read_text())
code=1; reason='operator-log'
try:
    lock=(STATE/(hashlib.sha256(request['project'].encode()).hexdigest()+'.lock')).open('w')
    fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    env=dict(os.environ)
    node=_node();env['PATH']=str(Path(node).parent)+os.pathsep+env.get('PATH','')
    for name,default in [('ANDROID_HOME',Path.home()/'.local/share/android-sdk'),('JAVA_HOME',Path.home()/'.local/share/java/jdk-17')]:
        if name not in env and default.exists():env[name]=str(default)
    code=subprocess.run([node,str(ENGINE),request['project'],request['operation'],request['approval']],env=env).returncode
except BlockingIOError:reason='project-already-running'
except Exception:reason='worker-failed'
finally:
    target=path/'result.json';tmp=path/'result.tmp'
    tmp.write_text(json.dumps({'jobId':job,'state':'succeeded' if code==0 else 'failed','exitCode':code,'operation':request['operation'],'reason':reason if code else None}))
    tmp.replace(target)
