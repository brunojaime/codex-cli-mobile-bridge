// Trusted DEV-only consumer adapter; immutable evidence gates are release-core's.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,cp,stat,chmod} from 'node:fs/promises';
import {execFileSync,spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
process.on('uncaughtException',async error=>{try{if(error.privateLog)await writeFile(error.privateLog,error.output||error.message,{mode:0o600});}catch{}process.stderr.write('DEV operation blocked: '+(error.privateLog?'inspect private operator log':'validation or baseline guard rejected candidate')+'\n');process.exitCode=1;});
const [configPath,action]=process.argv.slice(2);assert(['inspect','preflight','validate','deploy'].includes(action));
const c=JSON.parse(await readFile(configPath)),root=c.root,state=c.state;
assert.equal(resolve(process.cwd()),root);assert.equal(c.worker,'nienfos-gestion-dev');assert.equal(c.origin,'https://dev.gestion.nienfos.com');
const sha=b=>createHash('sha256').update(b).digest('hex'),json=async p=>JSON.parse(await readFile(p));
await mkdir(state,{recursive:true,mode:0o700});
const save=async(p,v)=>{await mkdir(resolve(p,'..'),{recursive:true,mode:0o700});await writeFile(p,JSON.stringify(v,null,2)+'\n',{mode:0o600});};
for(const [p,h]of Object.entries(c.trustedFiles))assert.equal(sha(await readFile(p)),h,'Official gate changed');
for(const [p,h]of Object.entries(c.pinned))assert.equal(sha(await readFile(root+'/'+p)),h,'Destination/dependency/build config changed');
const env={...process.env,PATH:resolve(process.execPath,'..')+':'+process.env.PATH,CI:'true',WRANGLER_SEND_METRICS:'false',NODE_OPTIONS:'--dns-result-order=ipv4first --no-network-family-autoselection'};delete env.CLOUDFLARE_API_TOKEN;
function run(argv,label,extra={}){const r=spawnSync(argv[0],argv.slice(1),{cwd:root,env:{...env,...extra},encoding:'utf8',timeout:600000,maxBuffer:64000000});const log=state+'/'+label+'.log';if(r.status!==0){throw Object.assign(Error(label+' failed; inspect private logs'),{output:(r.stdout||'')+'\n'+(r.stderr||''),privateLog:log});}return r.stdout.trim();}
const git=(...a)=>run(['git',...a],'git'),node=(...a)=>run([process.execPath,...a],'validation'),wr=(...a)=>run([process.execPath,'node_modules/wrangler/bin/wrangler.js',...a],'cloudflare');
assert.equal(git('branch','--show-current'),c.branch);assert.equal(git('status','--porcelain'),'','Candidate must be clean');
const revision=git('rev-parse','HEAD');assert(/^[a-f0-9]{40}$/.test(revision));
const latestPath=state+'/latest.json';let prior;try{prior=await json(latestPath);}catch(e){if(e.code!=='ENOENT')throw e;}
const baseline=prior?.revision??c.baselineRevision,expected=prior?.version??c.baselineDeployment;
assert.equal(git('diff','--name-only',baseline,'--','infra','package.json','package-lock.json','apps/web/package.json'),'','Schema/destination/dependency changes need preparation');
const token=JSON.parse(wr('auth','token','--json')).token;assert(token);
async function cf(field){const r=await fetch('https://api.cloudflare.com/client/v4/accounts/'+c.account+'/workers/scripts/'+c.worker+'/'+field,{headers:{Authorization:'Bearer '+token},redirect:'error',signal:AbortSignal.timeout(30000)});const j=await r.json();assert(r.ok&&j.success,'Cloudflare read failed');return j.result;}
const {digest}=await import(pathToFileURL(c.engine+'/index.mjs'));
const {scanSources}=await import(pathToFileURL(c.engine+'/inventory.mjs'));
const {artifactTree,webSourceDelta,assessWebMaintenance,dispatchWebMaintenance}=await import(pathToFileURL(c.engine+'/web-maintenance.mjs'));
const {baselineState,collectReleaseEvidence,assertBaseline}=await import(pathToFileURL(c.gates));
async function stable(){const d=(await cf('deployments')).deployments[0];assert.equal(d.versions.length,1);const [settings,schedules]=await Promise.all([cf('settings'),cf('schedules')]);assert.deepEqual((await cf('deployments')).deployments[0].versions,d.versions);return {version:d.versions[0].version_id,settings,schedules,state:baselineState(d.versions[0].version_id,settings,schedules)};}
async function fetchPublic(path){const r=await fetch(c.origin+path,{redirect:'error',signal:AbortSignal.timeout(30000)});assert.equal(r.status,200);return r;}
const before=await stable();assert.equal(before.version,expected,'DEV changed outside this queue; reconcile source first');
const runtimeEnv=before.settings.bindings.find(b=>b.name==='APP_ENV')?.text;assert.equal(runtimeEnv,'development');
if(action==='inspect'){console.log(JSON.stringify({environment:'dev',revision,baselineRevision:baseline,version:before.version,bindings:before.settings.bindings.length,crons:before.schedules.schedules.map(s=>s.cron),publicationAttempted:false}));process.exit(0);}
const dir=state+'/'+revision+(action==='preflight'?'-preflight':''),evidence=dir+'/evidence',artifact=dir+'/artifact';await mkdir(evidence,{recursive:true,mode:0o700});
if(action==='validate'||action==='preflight'){
 // The independent Reviewer creates this record; the operator never fabricates one.
 if(action==='validate'){const review=await json(evidence+'/review.json');assert.equal(review.mode??'independent','independent');assert.equal(review.revision,revision);assert.equal(review.status,'PASS');}
 const delta=webSourceDelta(root,baseline,revision);const changedTests=delta.filter(p=>/\.test\.ts$/.test(p));
 const testFiles=[...new Set(['apps/web/test/release-health.test.ts','apps/web/test/hooks-security.test.ts','apps/web/test/environment-config.test.ts',...changedTests])];
 const logs=[];
 run(['npm','exec','--workspace','@nienfos/web','--','svelte-kit','sync'],'sync');
 run(['npm','run','build','-w','@nienfos/tutorials'],'tutorials');
 const tests=node('node_modules/vitest/vitest.mjs','run',...testFiles);await writeFile(evidence+'/tests.log',tests,{mode:0o600});logs.push({name:'directed-tests',passed:true,evidencePath:'tests.log'});
 const types=run(['npm','run','check','-w','@nienfos/web'],'types');await writeFile(evidence+'/types.log',types,{mode:0o600});logs.push({name:'types',passed:true,evidencePath:'types.log'});
 run(['npm','run','build','-w','@nienfos/tutorials'],'tutorials');
 const build=run(['npm','run','build','-w','@nienfos/web'],'build',{GESTION_SOURCE_COMMIT:revision});await writeFile(evidence+'/build.log',build,{mode:0o600});logs.push({name:'build',passed:true,evidencePath:'build.log'});
 const cfg=await json(root+'/infra/wrangler.dev.jsonc');assert.equal(cfg.name,c.worker);assert.equal(cfg.account_id,c.account);
 assert.equal(cfg.d1_databases.length,1);assert.equal(cfg.d1_databases[0].database_id,before.settings.bindings.find(b=>b.name==='DB').id);
 assert.equal(cfg.r2_buckets[0].bucket_name,before.settings.bindings.find(b=>b.name==='PRIVATE_FILES').bucket_name);
 const declared=new Set([cfg.assets.binding,...cfg.d1_databases.map(b=>b.binding),...cfg.r2_buckets.map(b=>b.binding),cfg.ai?.binding,...(cfg.durable_objects?.bindings??[]).map(b=>b.name),...(cfg.services??[]).map(b=>b.binding)]);
 for(const b of before.settings.bindings)if(!['plain_text','secret_text'].includes(b.type))assert(declared.has(b.name),'Missing live binding');
 cfg.vars=Object.fromEntries(before.settings.bindings.filter(b=>b.type==='plain_text').map(b=>[b.name,b.text]));cfg.compatibility_date=before.settings.compatibility_date;cfg.compatibility_flags=before.settings.compatibility_flags;cfg.triggers={crons:before.schedules.schedules.map(s=>s.cron)};
 cfg.main=resolve(root,'infra',cfg.main);cfg.assets.directory=resolve(root,'infra',cfg.assets.directory);delete cfg.$schema;
 await mkdir(artifact+'/migrations',{recursive:true,mode:0o700});cfg.d1_databases.forEach(d=>d.migrations_dir=artifact+'/migrations');await save(dir+'/build-config.json',cfg);await save(dir+'/before.json',before);
 const dry=wr('deploy','--dry-run','--config',dir+'/build-config.json','--outdir',artifact+'/worker');await writeFile(evidence+'/dryrun.log',dry,{mode:0o600});logs.push({name:'dry-run',passed:true,evidencePath:'dryrun.log'});
 await cp(cfg.assets.directory,artifact+'/assets',{recursive:true});cfg.main=artifact+'/worker/index.js';await stat(cfg.main);cfg.assets.directory=artifact+'/assets';cfg.no_bundle=true;await save(artifact+'/deploy.json',cfg);
 // Private real backup, restored to an isolated local SQLite database; no remote fixture writes.
 wr('d1','export','DB','--remote','--config',dir+'/build-config.json','--output',dir+'/before.sql');await chmod(dir+'/before.sql',0o600);
 run(['/home/batata/Projects/codex-cli-mobile-bridge/.venv/bin/python','-c',"import sqlite3,sys,pathlib;d=sqlite3.connect(':memory:');d.executescript(pathlib.Path(sys.argv[1]).read_text());assert d.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not d.execute('PRAGMA foreign_key_check').fetchall();d.close()",dir+'/before.sql'],'restore');
 await save(evidence+'/migration-drill.json',{status:'PASS',revision,backupRestorePassed:true,integrity:'ok',migrations:[]});await save(evidence+'/validation.json',{status:'PASS',revision,checks:logs});
 if(action==='preflight'){console.log(JSON.stringify({preflightPassed:true,revision,databaseRestoreVerified:true,publicationAttempted:false,independentReviewPending:true}));process.exit(0);}
 const {reviews,checks}=await collectReleaseEvidence({evidenceRoot:evidence,revision,baselineRevision:baseline,delta,artifactRoot:artifact,environment:'dev'});
 const sourceConfig={schema:'nienfos.source-config/v1',app:'nienfos-gestion',sources:[{id:'candidate',kind:'ref',ref:revision}],include:['apps','packages','infra','scripts','specs','docs','architecture','data','domain','contracts','AGENTS.md','package.json','package-lock.json'],exclude:[{path:'docs/reports',reason:'Evidence separate from source'}]};
 const candidate={schema:'nienfos.web-maintenance/v1',app:'nienfos-gestion',environment:'dev',worker:c.worker,revision,baselineRevision:baseline,baselineDeployment:before.version,baselineStateDigest:digest(before.state),sourceConfig,sourceDigest:digest(scanSources(sourceConfig,{candidate:root})),artifactDigest:artifactTree(artifact).digest,reviews,checks};
 const authority={schema:'nienfos.web-maintenance-authority/v1',app:'nienfos-gestion',environment:'dev',worker:c.worker,candidateDigest:digest(candidate),requestRef:'User db2629437fbe14a873efc30fb8d4509f02193d453dcedf50077bdceb27f2e33b DEV bugfix automation',expiresAt:new Date(Date.now()+2*3600000).toISOString(),evidenceRoot:evidence,requiredChecks:checks.map(c=>c.name)};
 assert.equal(assessWebMaintenance({root,artifactRoot:artifact,candidate,authority,currentDeployment:(await stable()).version}).ready,true);
 await save(dir+'/candidate.json',candidate);await save(dir+'/authority.json',authority);console.log(JSON.stringify({validated:true,revision,checks:checks.length}));
}else{
 const candidate=await json(dir+'/candidate.json'),authority=await json(dir+'/authority.json'),captured=await json(dir+'/before.json');assert.equal(candidate.revision,revision);assertBaseline(candidate,(await stable()).state);
 assert.equal(git('ls-remote','origin','refs/heads/'+c.branch).split(/\s/)[0],revision);
 const attempt=dir+'/attempt.json';try{await stat(attempt);throw Error('Previous publication attempt requires reconciliation');}catch(e){if(e.code!=='ENOENT')throw e;}
 await save(attempt,{state:'publishing',revision});
 await dispatchWebMaintenance({root,artifactRoot:artifact,candidate,authority,currentDeployment:captured.version},async()=>wr('deploy','--config',artifact+'/deploy.json','--message','Verified automatic DEV bugfix '+revision));
 const after=await stable();assert.notEqual(after.version,captured.version);assert.deepEqual(after.state.bindings,captured.state.bindings);assert.deepEqual(after.state.crons,captured.state.crons);assert.equal(after.state.compatibility_date,captured.state.compatibility_date);assert.deepEqual(after.state.compatibility_flags,captured.state.compatibility_flags);
 const version=JSON.parse(await (await fetchPublic('/_app/version.json')).text());assert.equal(version.version,revision);
 const health=await (await fetchPublic('/healthz')).json();assert.equal(health.environment,'dev');assert.equal(health.commit,revision);
 const protectedRoute=await fetch(c.origin+'/api/health',{redirect:'error'});assert.equal(protectedRoute.status,401);await fetchPublic('/login');
 const receipt={status:'published_and_verified',environment:'dev',revision,version:after.version,baselineRevision:baseline,bindings:after.settings.bindings.length,crons:after.schedules.schedules.map(s=>s.cron),remoteConfirmed:true,publicVersionVerified:true,protectedDataStillPrivate:true,productionPublished:false};await save(latestPath,receipt);await save(attempt,receipt);console.log(JSON.stringify(receipt));
}
