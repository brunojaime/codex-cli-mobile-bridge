// Operator-owned DEV-only delivery adapter. Never receives commands from a task.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,chmod,stat} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {resolve} from 'node:path';

const [configuration,action]=process.argv.slice(2);
assert(['inspect','validate','deploy'].includes(action));
const cfg=JSON.parse(await readFile(configuration)),root=await (await import('node:fs/promises')).realpath(cfg.root);
assert.equal(await (await import('node:fs/promises')).realpath(process.cwd()),root);
const hash=b=>createHash('sha256').update(typeof b==='string'||Buffer.isBuffer(b)?b:JSON.stringify(b)).digest('hex');
const env={...process.env,PATH:resolve(process.execPath,'..')+':'+process.env.PATH,CI:'true',WRANGLER_SEND_METRICS:'false',NODE_OPTIONS:'--dns-result-order=ipv4first --no-network-family-autoselection'};
delete env.CLOUDFLARE_API_TOKEN;
await mkdir(cfg.state,{recursive:true,mode:0o700});
let sequence=0;
async function run(argv,label,timeout=180000){
 const r=spawnSync(argv[0],argv.slice(1),{cwd:root,env,encoding:'utf8',timeout,maxBuffer:64*1024*1024});
 if(r.status!==0){await writeFile(resolve(cfg.state,`failure-${Date.now()}-${sequence++}.log`),(r.stdout||'')+'\n'+(r.stderr||''),{mode:0o600});throw Error(label+' failed; output retained privately');}
 return r.stdout.trim();
}
const git=(...args)=>run(['git',...args],'Git');
const wr=(...args)=>run([process.execPath,'node_modules/wrangler/bin/wrangler.js',...args],'Cloudflare');
const config=JSON.parse(await readFile('wrangler.json'));
assert.equal(hash(await readFile('wrangler.json')),cfg.wranglerSha256,'DEV configuration changed');
assert.equal(config.name,'comandas-web-dev');
assert.equal(config.account_id,'c339fa224b83bcca6be83a051720fe70');
assert.equal(config.d1_databases.length,1);
assert.equal(config.d1_databases[0].database_id,'6926873c-0204-4a32-b747-b2ee93fea4e2');
assert.equal(config.vars.APP_ORIGIN,'https://comandas-web-dev.nienfos.workers.dev');
assert.equal(config.vars.DEPLOYMENT_PROFILE,'development');
assert.equal(config.vars.CODEX_FEEDBACK_ENABLED,'true');
assert.equal(config.assets.directory,'.build/dev/public');
assert.equal(await git('branch','--show-current'),cfg.branch);
assert.equal(await git('status','--porcelain'),'','Uncommitted candidate');
assert.equal((await git('diff','--name-only',cfg.baseCommit,'--','migrations','wrangler.json','wrangler.qa.json','wrangler.production.json','package.json','package-lock.json')),'','Database/destination/dependency changes require separate preparation');
const revision=await git('rev-parse','HEAD');
async function health(origin=cfg.origin){const r=await fetch(origin+'/api/health',{signal:AbortSignal.timeout(30000),redirect:'error'});assert.equal(r.status,200);return r.json();}
const live=await health();assert.equal(live.environment,'dev');assert.equal(live.feedback,true);
if(action==='inspect'){
 assert.equal(live.source_commit,cfg.baselineSource,'DEV changed during preparation');
 assert((await wr('whoami')).includes(config.account_id));
 assert.equal(JSON.parse(await wr('d1','info',config.name,'--config','wrangler.json','--json')).uuid,config.d1_databases[0].database_id);
 assert((await wr('d1','migrations','list','DB','--config','wrangler.json','--remote')).includes('No migrations to apply'),'Pending migrations require preparation');
 console.log(JSON.stringify({configured:true,environment:'dev',revision,liveCommit:live.source_commit,publicationAttempted:false}));
}else{
 const checked=resolve(cfg.state,revision+'-validated.json');
 if(action==='validate'){
  await run([process.execPath,'scripts/build-environment.mjs','dev'],'DEV build');
  // Local QA compilation is required by the existing environment-isolation test;
  // it does not contact or publish to QA.
  await run([process.execPath,'scripts/build-environment.mjs','qa'],'Local QA distribution check');
  await run([process.execPath,'--test','scripts/scheduled-orders.test.mjs','scripts/business-days.test.mjs','scripts/order-readiness.test.mjs','scripts/feedback-environments.test.mjs'],'Directed tests',180000);
  await wr('deploy','--config','wrangler.json','--dry-run','--var','SOURCE_COMMIT:'+revision);
  assert.equal(await git('status','--porcelain'),'','Validation changed tracked candidate');
  await writeFile(checked,JSON.stringify({revision,manifest:hash(await readFile('.build/dev/public/asset-manifest.json')),at:new Date().toISOString()}),{mode:0o600});
  console.log(JSON.stringify({validated:true,environment:'dev',revision}));
 }else{
  const validation=JSON.parse(await readFile(checked));assert.equal(validation.revision,revision);
  assert.equal(hash(await readFile('.build/dev/public/asset-manifest.json')),validation.manifest,'Validated assets changed');
  const priorReceipt=resolve(cfg.state,'latest.json');
  let previous=cfg.baselineSource;try{previous=JSON.parse(await readFile(priorReceipt)).commit;}catch(e){if(e.code!=='ENOENT')throw e;}
  assert.equal(live.source_commit,previous,'DEV changed outside this queue; reconcile before publishing');
  const attempt=resolve(cfg.state,revision+'-attempt.json');
  try{await stat(attempt);throw Error('Previous publication attempt exists; reconcile before retry');}catch(e){if(e.code!=='ENOENT')throw e;}
  assert((await wr('whoami')).includes(config.account_id));
  assert.equal(JSON.parse(await wr('d1','info',config.name,'--config','wrangler.json','--json')).uuid,config.d1_databases[0].database_id);
  assert((await wr('d1','migrations','list','DB','--config','wrangler.json','--remote')).includes('No migrations to apply'),'Pending migrations require explicit preparation');
  const query=async sql=>JSON.parse(await wr('d1','execute','DB','--config','wrangler.json','--remote','--command',sql,'--json'));
  const tables=(await query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' ORDER BY name"))[0].results.map(r=>r.name);
  for(const name of tables)assert(/^[A-Za-z0-9_]+$/.test(name));
  const definitions=await query(tables.map(t=>'PRAGMA table_info("'+t+'")').join(';'));
  const selections=tables.map((table,i)=>{
   const primary=definitions[i].results.filter(f=>f.pk).sort((a,b)=>a.pk-b.pk).map(f=>'"'+f.name.replaceAll('"','""')+'"');
   return 'SELECT * FROM "'+table+'" ORDER BY '+(primary.join(',')||'rowid');
  });
  async function fingerprints(){
   const rows=await query(selections.join(';'));
   return Object.fromEntries(tables.map((table,i)=>[table,{count:rows[i].results.length,sha256:hash(rows[i].results)}]));
  }
  const before=await fingerprints(),qaBefore=await health('https://comandas-web-qa.nienfos.workers.dev'),prodBefore=await health('https://app.alasbrasaspm.com.ar');
  const backup=resolve(cfg.state,revision+'-before.sql');
  await wr('d1','export','DB','--config','wrangler.json','--remote','--output',backup);await chmod(backup,0o600);
  const db=new DatabaseSync(':memory:');try{
   db.exec(await readFile(backup,'utf8'));assert.equal(db.prepare('PRAGMA integrity_check').get().integrity_check,'ok');assert.equal(db.prepare('PRAGMA foreign_key_check').all().length,0);
   for(const t of tables)assert.equal(db.prepare('SELECT count(*) n FROM "'+t+'"').get().n,before[t].count,'Backup snapshot changed; repeat preparation');
  }finally{db.close();}
  assert.deepEqual(await fingerprints(),before,'DEV data changed during preflight');
  assert.equal((await health()).source_commit,previous,'DEV changed during preflight');
  await writeFile(attempt,JSON.stringify({status:'publishing',revision}),{mode:0o600});
  const output=await wr('deploy','--config','wrangler.json','--var','SOURCE_COMMIT:'+revision);
  await writeFile(resolve(cfg.state,revision+'-deploy.log'),output,{mode:0o600});
  const observed=await health();assert.equal(observed.source_commit,revision);assert.equal(observed.environment,'dev');
  const r=await fetch(cfg.origin+'/api/bridge-version',{redirect:'error'});assert.equal(r.status,200);assert.deepEqual(await r.json(),{environment:'dev',commit:revision});
  const assets=JSON.parse(await readFile('.build/dev/public/asset-manifest.json'));
  for(const path of Object.values(assets)){const response=await fetch(cfg.origin+path,{redirect:'error'});assert.equal(response.status,200);assert.equal(hash(Buffer.from(await response.arrayBuffer())),hash(await readFile('.build/dev/public'+path)));}
  assert.equal((await fetch(cfg.origin+'/api/orders')).status,401);
  assert.deepEqual(await fingerprints(),before,'DEV data changed; reconcile publication');
  assert.deepEqual(await health('https://comandas-web-qa.nienfos.workers.dev'),qaBefore);assert.deepEqual(await health('https://app.alasbrasaspm.com.ar'),prodBefore);
  const receipt={environment:'dev',commit:revision,version:output.match(/Current Version ID:\s*([\w-]+)/)?.[1],backupRestored:true,dataPreserved:true,assetsVerified:true,qaUnchanged:true,prodUnchanged:true,at:new Date().toISOString()};assert(receipt.version);
  await writeFile(priorReceipt,JSON.stringify(receipt),{mode:0o600});await writeFile(attempt,JSON.stringify({status:'verified',revision}),{mode:0o600});
  console.log(JSON.stringify(receipt));
 }
}
