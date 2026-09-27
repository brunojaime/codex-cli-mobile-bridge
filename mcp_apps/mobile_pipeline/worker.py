from pathlib import Path
import json, os, re, subprocess, sys
from .server import STATE, ENGINE, _node
import fcntl, hashlib
job=sys.argv[1]
if not re.fullmatch(r'[a-f0-9-]{36}',job):raise ValueError('Invalid job')
path=STATE/job
request=json.loads((path/'request.json').read_text())
lock=(STATE/(hashlib.sha256(request['project'].encode()).hexdigest()+'.lock')).open('w')
fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
env=dict(os.environ)
node=_node();env['PATH']=str(Path(node).parent)+os.pathsep+env.get('PATH','')
for name,default in [('ANDROID_HOME',Path.home()/'.local/share/android-sdk'),('JAVA_HOME',Path.home()/'.local/share/java/jdk-17')]:
    if name not in env and default.exists():env[name]=str(default)
result=subprocess.run([node,str(ENGINE),request['project'],request['operation'],request['approval']],env=env)
target=path/'result.json';tmp=path/'result.tmp'
tmp.write_text(json.dumps({'jobId':job,'state':'succeeded' if result.returncode==0 else 'failed','exitCode':result.returncode,'operation':request['operation'],'detail':'See private operator log for failures; no automatic retry or republish.'}))
tmp.replace(target)
