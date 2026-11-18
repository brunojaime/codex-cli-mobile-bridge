// Trusted DEV-only Cloudflare app adapter; immutable evidence gates are release-core's.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,cp,stat,chmod,symlink} from 'node:fs/promises';
import {execFileSync,spawnSync,spawn} from 'node:child_process';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
process.on('uncaughtException',async error=>{try{if(error.privateLog)await writeFile(error.privateLog,error.output||error.message,{mode:0o600});}catch{}process.stderr.write('DEV operation blocked: '+(error.privateLog?'inspect private operator log':'validation or baseline guard rejected candidate')+'\n');process.exitCode=1;});
const [configPath,action]=process.argv.slice(2);assert(['inspect','preflight','validate','deploy'].includes(action));
const c=JSON.parse(await readFile(configPath)),root=c.root,state=c.state;
assert.equal(resolve(process.cwd()),root);assert.equal(c.product,'patsa');assert.equal(c.worker,'patsa-dev');assert.equal(c.origin,'https://patsa-dev.nienfos.workers.dev');
const sha=b=>createHash('sha256').update(b).digest('hex'),json=async p=>JSON.parse(await readFile(p));
await mkdir(state,{recursive:true,mode:0o700});
const save=async(p,v)=>{await mkdir(resolve(p,'..'),{recursive:true,mode:0o700});await writeFile(p,JSON.stringify(v,null,2)+'\n',{mode:0o600});};
for(const [p,h]of Object.entries(c.trustedFiles))assert.equal(sha(await readFile(p)),h,'Official gate changed');
for(const [p,h]of Object.entries(c.pinned))assert.equal(sha(await readFile(root+'/'+p)),h,'Destination/dependency/build config changed');
const env={...process.env,PATH:resolve(process.execPath,'..')+':'+process.env.PATH,CI:'true',WRANGLER_SEND_METRICS:'false',NODE_OPTIONS:'--dns-result-order=ipv4first --no-network-family-autoselection'};delete env.CLOUDFLARE_API_TOKEN;
let commandRoot=root;
function run(argv,label,extra={}){const r=spawnSync(argv[0],argv.slice(1),{cwd:commandRoot,env:{...env,...extra},encoding:'utf8',timeout:600000,maxBuffer:64000000});const log=state+'/'+label+'.log';if(r.status!==0){throw Object.assign(Error(label+' failed; inspect private logs'),{output:(r.stdout||'')+'\n'+(r.stderr||''),privateLog:log});}return r.stdout.trim();}
const git=(...a)=>execFileSync('git',a,{cwd:root,env,encoding:'utf8',maxBuffer:64000000}).trim(),node=(...a)=>run([process.execPath,...a],'validation'),wr=(...a)=>run([process.execPath,'node_modules/wrangler/bin/wrangler.js',...a],'cloudflare');
assert.equal(git('branch','--show-current'),c.branch);assert.equal(git('status','--porcelain'),'','Candidate must be clean');
const revision=git('rev-parse','HEAD');assert(/^[a-f0-9]{40}$/.test(revision));
const latestPath=state+'/latest.json';let prior;try{prior=await json(latestPath);}catch(e){if(e.code!=='ENOENT')throw e;}
const baseline=prior?.revision??c.baselineRevision,expected=prior?.version??c.baselineDeployment;
assert.equal(git('diff','--name-only',baseline,'--','wrangler.json','wrangler.qa.json','package.json','package-lock.json'),'','Schema/destination/dependency changes need preparation');
const token=JSON.parse(wr('auth','token','--json')).token;assert(token);
async function cf(field){const r=await fetch('https://api.cloudflare.com/client/v4/accounts/'+c.account+'/workers/scripts/'+c.worker+'/'+field,{headers:{Authorization:'Bearer '+token},redirect:'error',signal:AbortSignal.timeout(30000)});const j=await r.json();assert(r.ok&&j.success,'Cloudflare read failed');return j.result;}
const {digest}=await import(pathToFileURL(c.engine+'/index.mjs'));
const {scanSources}=await import(pathToFileURL(c.engine+'/inventory.mjs'));
const {artifactTree,webSourceDelta,assessWebMaintenance,dispatchWebMaintenance}=await import(pathToFileURL(c.engine+'/web-maintenance.mjs'));
const {baselineState,collectReleaseEvidence,assertBaseline}=await import(pathToFileURL(c.gates));
async function stable(){const d=(await cf('deployments')).deployments[0];assert.equal(d.versions.length,1);const [settings,schedules]=await Promise.all([cf('settings'),cf('schedules')]);assert.deepEqual((await cf('deployments')).deployments[0].versions,d.versions);return {version:d.versions[0].version_id,settings,schedules,state:baselineState(d.versions[0].version_id,settings,schedules)};}
async function fetchPublic(path){const r=await fetch(c.origin+path,{redirect:'error',signal:AbortSignal.timeout(30000)});assert.equal(r.status,200);return r;}
const before=await stable();assert.equal(before.version,expected,'DEV changed outside this queue; reconcile source first');
const runtimeEnv=before.settings.bindings.find(b=>b.name==='DEPLOYMENT_PROFILE')?.text;assert.equal(runtimeEnv,'development');
if(action==='inspect'){console.log(JSON.stringify({environment:'dev',revision,baselineRevision:baseline,version:before.version,bindings:before.settings.bindings.length,crons:before.schedules.schedules.map(s=>s.cron),publicationAttempted:false}));process.exit(0);}
const dir=state+'/'+revision+(action==='preflight'?'-preflight':''),evidence=dir+'/evidence',artifact=dir+'/artifact';await mkdir(evidence,{recursive:true,mode:0o700});
if(action==='validate'||action==='preflight'){
 // The independent Reviewer creates this record; the operator never fabricates one.
 if(action==='validate'){const review=await json(evidence+'/review.json');assert.equal(review.mode??'independent','independent');assert.equal(review.revision,revision);assert.equal(review.status,'PASS');}
 const delta=webSourceDelta(root,baseline,revision);const changedTests=delta.filter(p=>/\.test\.mjs$/.test(p));
 const buildSource=dir+'/build-source';await mkdir(buildSource,{recursive:true,mode:0o700});
 // Build/test frozen Git inputs outside the model checkout; generated assets and test reports cannot dirty reviewed source.
 await new Promise((ok,fail)=>{const ar=spawn('git',['archive','--format=tar',revision],{cwd:root,stdio:['ignore','pipe','ignore']});const tar=spawn('tar',['-x','-C',buildSource],{stdio:['pipe','ignore','ignore']});ar.stdout.pipe(tar.stdin);let finished=0,bad=false;for(const child of [ar,tar]){child.on('error',fail);child.on('close',code=>{bad ||= code!==0;if(++finished===2)bad?fail(Error('Frozen source staging failed')):ok();});}});
 try{await symlink(root+'/node_modules',buildSource+'/node_modules','dir');}catch(e){if(e.code!=='EEXIST')throw e;}
 await mkdir(buildSource+'/.platform-private',{recursive:true,mode:0o700});
 commandRoot=buildSource;
 const logs=[];
 const tests=run(['npm','test'],'tests');await writeFile(evidence+'/tests.log',tests,{mode:0o600});logs.push({name:'product-tests',passed:true,evidencePath:'tests.log'});
 const syntax=node('--check','worker.mjs');await writeFile(evidence+'/syntax.log',syntax,{mode:0o600});logs.push({name:'worker-syntax',passed:true,evidencePath:'syntax.log'});
 const build=run(['npm','run','build'],'build',{VITE_PATSA_ENVIRONMENT:'dev'});await writeFile(evidence+'/build.log',build,{mode:0o600});logs.push({name:'dev-build',passed:true,evidencePath:'build.log'});
 const migrationDelta=delta.filter(p=>p.startsWith('migrations/')&&p.endsWith('.sql'));
 assert.equal(git('diff','--no-renames','--diff-filter=MD','--name-only',baseline,'--','migrations'),'','Historical migrations are immutable');
 for(const p of migrationDelta){const sql=await readFile(root+'/'+p,'utf8');assert(!/\b(DROP|DELETE|TRUNCATE|REPLACE|UPDATE|INSERT|RENAME)\b/i.test(sql),'Non-additive migration requires specific preparation');}
 const cfg=await json(root+'/wrangler.json');assert.equal(cfg.name,c.worker);assert.equal(cfg.account_id,c.account);
 assert.equal(cfg.d1_databases.length,1);assert.equal(cfg.d1_databases[0].database_id,before.settings.bindings.find(b=>b.name==='DB').id);
 assert.equal(cfg.r2_buckets[0].bucket_name,before.settings.bindings.find(b=>b.name==='COMMERCIAL_ATTACHMENTS').bucket_name);
 const declared=new Set([cfg.assets.binding,...cfg.d1_databases.map(b=>b.binding),...cfg.r2_buckets.map(b=>b.binding),cfg.ai?.binding,...(cfg.durable_objects?.bindings??[]).map(b=>b.name),...(cfg.services??[]).map(b=>b.binding)]);
 for(const b of before.settings.bindings)if(!['plain_text','secret_text'].includes(b.type))assert(declared.has(b.name),'Missing live binding');
 cfg.vars=Object.fromEntries(before.settings.bindings.filter(b=>b.type==='plain_text').map(b=>[b.name,b.text]));cfg.compatibility_date=before.settings.compatibility_date;cfg.compatibility_flags=before.settings.compatibility_flags;cfg.triggers={crons:before.schedules.schedules.map(s=>s.cron)};
 cfg.main=resolve(buildSource,cfg.main);cfg.assets.directory=resolve(buildSource,cfg.assets.directory);cfg.vars.SOURCE_COMMIT=revision;delete cfg.$schema;
 await cp(root+'/migrations',artifact+'/migrations',{recursive:true});cfg.d1_databases.forEach(d=>d.migrations_dir=artifact+'/migrations');await save(dir+'/build-config.json',cfg);await save(dir+'/before.json',before);
 const applied=JSON.parse(wr('d1','execute','DB','--remote','--config',dir+'/build-config.json','--command','SELECT name FROM d1_migrations ORDER BY name','--json'))[0].results.map(r=>r.name);
 const migrations=(await (await import('node:fs/promises')).readdir(artifact+'/migrations')).filter(n=>n.endsWith('.sql')&&!applied.includes(n)).sort();
 for(const name of migrations)assert(migrationDelta.includes('migrations/'+name),'Pending migration outside reviewed delta');
 const dry=wr('deploy','--dry-run','--config',dir+'/build-config.json','--outdir',artifact+'/worker');await writeFile(evidence+'/dryrun.log',dry,{mode:0o600});logs.push({name:'dry-run',passed:true,evidencePath:'dryrun.log'});
 await cp(cfg.assets.directory,artifact+'/assets',{recursive:true});for(const name of ['_worker.js','index.js']){try{if((await stat(artifact+'/worker/'+name)).isFile()){cfg.main=artifact+'/worker/'+name;break;}}catch(e){if(e.code!=='ENOENT')throw e;}}assert(cfg.main.startsWith(artifact+'/worker/'),'Worker bundle not found');cfg.assets.directory=artifact+'/assets';cfg.no_bundle=true;await save(artifact+'/deploy.json',cfg);
 // Private real backup, restored to an isolated local SQLite database; no remote fixture writes.
 wr('d1','export','DB','--remote','--config',dir+'/build-config.json','--output',dir+'/before.sql');await chmod(dir+'/before.sql',0o600);
 run(['/home/batata/Projects/codex-cli-mobile-bridge/.venv/bin/python','-c',"import sqlite3,sys,pathlib;d=sqlite3.connect(':memory:');d.executescript(pathlib.Path(sys.argv[1]).read_text());assert d.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not d.execute('PRAGMA foreign_key_check').fetchall();d.close()",dir+'/before.sql'],'restore');
 for(const name of migrations){run(['/home/batata/Projects/codex-cli-mobile-bridge/.venv/bin/python','-c',"import sqlite3,sys,pathlib;d=sqlite3.connect(':memory:');d.executescript(pathlib.Path(sys.argv[1]).read_text());[d.executescript(pathlib.Path(p).read_text()) for p in sys.argv[2:]];assert d.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not d.execute('PRAGMA foreign_key_check').fetchall()",dir+'/before.sql',...migrations.map(n=>artifact+'/migrations/'+n)],'migration-restore');break;}
 await save(dir+'/migrations.json',migrations);
 await save(evidence+'/migration-drill.json',{status:'PASS',revision,backupRestorePassed:true,integrity:'ok',migrations:await Promise.all(migrations.map(async name=>({name,sha256:digest(await readFile(artifact+'/migrations/'+name))})))});await save(evidence+'/validation.json',{status:'PASS',revision,checks:logs});
 if(action==='preflight'){console.log(JSON.stringify({preflightPassed:true,revision,databaseRestoreVerified:true,publicationAttempted:false,independentReviewPending:true}));process.exit(0);}
 const {reviews,checks}=await collectReleaseEvidence({evidenceRoot:evidence,revision,baselineRevision:baseline,delta,artifactRoot:artifact,environment:'dev'});
 const sourceConfig={schema:'nienfos.source-config/v1',app:c.product,sources:[{id:'candidate',kind:'ref',ref:revision}],include:['src','server','domain','public','migrations','scripts','tests','specs','docs','vendor','AGENTS.md','package.json','package-lock.json','svelte.config.js','vite.config.js','worker.mjs','identity-runtime.mjs','identity.config.mjs','scheduled.mjs','notifications.mjs','tutorials.mjs','build-tutorials.mjs','build-nienfos-payments.mjs','compose-notifications.mjs','feedback-client.mjs','foundation.project.json','platform.project.json','wrangler.json'],exclude:[{path:'docs/reports',reason:'Evidence separate from source'}]};
 const candidate={schema:'nienfos.web-maintenance/v1',app:c.product,environment:'dev',worker:c.worker,revision,baselineRevision:baseline,baselineDeployment:before.version,baselineStateDigest:digest(before.state),sourceConfig,sourceDigest:digest(scanSources(sourceConfig,{candidate:root})),artifactDigest:artifactTree(artifact).digest,reviews,checks};
 const authority={schema:'nienfos.web-maintenance-authority/v1',app:c.product,environment:'dev',worker:c.worker,candidateDigest:digest(candidate),requestRef:'User b59e33ed625581a5eb4df57944d6e879facf2e7f3251b6460c9aeebb5813e08f comprehensive PATSA DEV improvements',expiresAt:new Date(Date.now()+2*3600000).toISOString(),evidenceRoot:evidence,requiredChecks:checks.map(c=>c.name)};
 assert.equal(assessWebMaintenance({root,artifactRoot:artifact,candidate,authority,currentDeployment:(await stable()).version}).ready,true);
 await save(dir+'/candidate.json',candidate);await save(dir+'/authority.json',authority);console.log(JSON.stringify({validated:true,revision,checks:checks.length}));
}else{
 const candidate=await json(dir+'/candidate.json'),authority=await json(dir+'/authority.json'),captured=await json(dir+'/before.json');assert.equal(candidate.revision,revision);assertBaseline(candidate,(await stable()).state);
 assert.equal(git('ls-remote','origin','refs/heads/'+c.branch).split(/\s/)[0],revision);
 const attempt=dir+'/attempt.json';try{await stat(attempt);throw Error('Previous publication attempt requires reconciliation');}catch(e){if(e.code!=='ENOENT')throw e;}
 await save(attempt,{state:'publishing',revision});
 await dispatchWebMaintenance({root,artifactRoot:artifact,candidate,authority,currentDeployment:captured.version},async()=>{const migrations=await json(dir+'/migrations.json');wr('d1','export','DB','--remote','--config',artifact+'/deploy.json','--output',dir+'/immediate-before.sql');await chmod(dir+'/immediate-before.sql',0o600);run(['/home/batata/Projects/codex-cli-mobile-bridge/.venv/bin/python','-c',"import sqlite3,sys,pathlib;d=sqlite3.connect(':memory:');d.executescript(pathlib.Path(sys.argv[1]).read_text());assert d.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not d.execute('PRAGMA foreign_key_check').fetchall();[d.executescript(pathlib.Path(p).read_text()) for p in sys.argv[2:]];assert d.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not d.execute('PRAGMA foreign_key_check').fetchall()",dir+'/immediate-before.sql',...migrations.map(n=>artifact+'/migrations/'+n)],'immediate-restore');assertBaseline(candidate,(await stable()).state);if(migrations.length)wr('d1','migrations','apply','DB','--remote','--config',artifact+'/deploy.json');return wr('deploy','--config',artifact+'/deploy.json','--message','Verified automatic DEV improvements '+revision);});
 const after=await stable();assert.notEqual(after.version,captured.version);assert.deepEqual(after.state.bindings.filter(b=>b.name!=='SOURCE_COMMIT'),captured.state.bindings.filter(b=>b.name!=='SOURCE_COMMIT'));assert.equal(after.settings.bindings.find(b=>b.name==='SOURCE_COMMIT')?.text,revision);assert.deepEqual(after.state.crons,captured.state.crons);assert.equal(after.state.compatibility_date,captured.state.compatibility_date);assert.deepEqual(after.state.compatibility_flags,captured.state.compatibility_flags);
 const version=JSON.parse(await (await fetchPublic('/_app/version.json')).text());assert.equal(version.version,JSON.parse(await readFile(artifact+'/assets/_app/version.json')).version);
 const health=await (await fetchPublic('/api/bridge-version')).json();assert.equal(health.environment,'dev');assert.equal(health.commit,revision);
 const protectedRoute=await fetch(c.origin+'/api/workspace/bootstrap',{redirect:'error'});assert.equal(protectedRoute.status,401);await fetchPublic('/ingresar');
 const receipt={status:'published_and_verified',environment:'dev',revision,version:after.version,baselineRevision:baseline,bindings:after.settings.bindings.length,crons:after.schedules.schedules.map(s=>s.cron),remoteConfirmed:true,publicVersionVerified:true,protectedDataStillPrivate:true,productionPublished:false};await save(latestPath,receipt);await save(attempt,receipt);console.log(JSON.stringify(receipt));
}
