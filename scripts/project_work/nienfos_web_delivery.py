"""Operator-owned, DEV-only Nienfos web publisher; candidate supplies no commands."""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
import httpx

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 c=json.loads(Path(sys.argv[1]).read_text());action=sys.argv[2]
 assert action in ('inspect','validate','deploy')
 root=Path(c['root']).resolve();state=Path(c['state']);state.mkdir(parents=True,exist_ok=True,mode=0o700)
 assert Path.cwd().resolve()==root
 env={**os.environ,'PATH':str(Path(c['node']).parent)+':'+os.environ['PATH'],'WRANGLER_SEND_METRICS':'false','NODE_OPTIONS':'--dns-result-order=ipv4first --no-network-family-autoselection'}
 # Use the existing operator Cloudflare login; inherited app tokens lack Worker access.
 env.pop('CLOUDFLARE_API_TOKEN',None)
 def run(argv,label,timeout=600):
  r=subprocess.run(argv,cwd=root,env=env,capture_output=True,timeout=timeout)
  if r.returncode:
   p=state/(label+'-failed.log');p.write_bytes(r.stdout+b'\n'+r.stderr);p.chmod(0o600)
   raise RuntimeError(label+' failed; output retained privately')
  return r.stdout.decode().strip()
 git=lambda *a:run(['git',*a],'git')
 node=lambda *a:run([c['node'],*a],'validation')
 wr=lambda *a:run([c['node'],'node_modules/wrangler/bin/wrangler.js',*a],'cloudflare')
 for p,h in c['pinned'].items():assert sha((root/p).read_bytes())==h,'Destination/dependency change requires preparation'
 cfg=json.loads((root/'infra/wrangler.dev.jsonc').read_text())
 assert c['origin']=='https://dev.nienfos.com'
 assert cfg['name']==c['worker']=='nienfos-web-dev' and cfg['account_id']==c['account']
 assert cfg['vars']=={'APP_ENV':'dev','CONTACT_MODE':'disabled'}
 assert cfg['routes']==[{'pattern':'dev.nienfos.com','custom_domain':True}]
 assert cfg['assets']['directory']=='../dist-dev'
 assert not cfg.get('d1_databases') and not cfg.get('r2_buckets')
 assert git('branch','--show-current')==c['branch']
 assert not git('status','--porcelain'),'Candidate must be clean and committed'
 revision=git('rev-parse','HEAD');assert re.fullmatch('[a-f0-9]{40}',revision)
 def fetch(path):
  r=httpx.get(c['origin']+path,timeout=30,follow_redirects=False);assert r.status_code==200;return r
 health=fetch('/_health').json();assert health['environment']=='dev' and health['contact']=='disabled'
 if action=='inspect':
  assert c['account'] in wr('whoami');print(json.dumps({'isolated':True,'revision':revision}));return
 def manifest():return {str(p.relative_to(root/'dist-dev')):sha(p.read_bytes()) for p in sorted((root/'dist-dev').rglob('*')) if p.is_file()}
 validation=state/(revision+'-validated.json')
 if action=='validate':
  node('--test','scripts/dev-worker.test.mjs','scripts/contact-worker.test.mjs','scripts/chat-transport.test.mjs','scripts/assistant-proxy.test.mjs','scripts/chat-antibot.test.mjs')
  node('scripts/build-dev.mjs')
  assert 'noindex' in (root/'dist-dev/index.html').read_text()
  assert 'Disallow: /' in (root/'dist-dev/robots.txt').read_text()
  wr('deploy','--config','infra/wrangler.dev.jsonc','--dry-run','--var','SOURCE_COMMIT:'+revision)
  assert not git('status','--porcelain')
  validation.write_text(json.dumps({'revision':revision,'assets':manifest()}))
  print(json.dumps({'validated':True,'revision':revision}));return
 checked=json.loads(validation.read_text());assert checked['revision']==revision and checked['assets']==manifest(),'Validated assets changed'
 remote=git('ls-remote','origin','refs/heads/'+c['branch']).split();assert remote and remote[0]==revision,'Remote not confirmed'
 latest=state/'latest.json'
 if latest.exists():assert fetch('/api/bridge-version').json()=={'environment':'dev','commit':json.loads(latest.read_text())['commit']},'DEV changed outside queue'
 else:assert sha(fetch('/').content)==c['initial_page_sha256'],'DEV changed since preparation'
 attempt=state/(revision+'-attempt.json');assert not attempt.exists(),'Previous publication attempt requires inspection'
 attempt.write_text(json.dumps({'state':'publishing','revision':revision}))
 wr('deploy','--config','infra/wrangler.dev.jsonc','--var','SOURCE_COMMIT:'+revision)
 for i in range(12):
  try:
   assert fetch('/api/bridge-version').json()=={'environment':'dev','commit':revision};break
  except Exception:
   if i==11:raise
   time.sleep(2)
 page=fetch('/');assert sha(page.content)==checked['assets']['index.html']
 assert 'noindex' in page.headers['x-robots-tag']
 paths=re.findall(r'(?:src|href)="(/assets/[^"?]+)(?:\?[^" ]*)?"',page.text);assert paths
 for p in paths:assert sha(fetch(p).content)==checked['assets'][p.lstrip('/')]
 assert fetch('/_health').json()['contact']=='disabled'
 receipt={'environment':'dev','commit':revision,'remote_confirmed':True,'assets_verified':True,'contact_disabled':True,'noindex':True,'production_published':False,'url':c['origin']}
 latest.write_text(json.dumps(receipt,indent=2)+'\n');attempt.write_text(json.dumps({'state':'published_and_verified','revision':revision}))
 print(json.dumps(receipt))
if __name__=='__main__':main()
