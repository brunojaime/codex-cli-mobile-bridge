import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {resolve,relative,isAbsolute} from 'node:path';

const [configPath,action]=process.argv.slice(2);
assert(['inspect','validate','deploy'].includes(action),'Unknown operator action');
const read=async p=>JSON.parse(await fs.readFile(p));
const config=await read(configPath),root=await fs.realpath(config.root);
assert.equal(await fs.realpath(process.cwd()),root);
assert.equal(config.environment,'dev','This adapter publishes DEV only');
const hash=b=>createHash('sha256').update(b).digest('hex');
for(const [file,expected] of Object.entries(config.trustedFiles))assert.equal(hash(await fs.readFile(file)),expected,'Trusted release adapter changed: '+file);
assert.equal(hash(await fs.readFile(config.archive)),config.archiveSha256);
for(const file of execFileSync('tar',['-tzf',config.archive],{encoding:'utf8'}).trim().split('\n').filter(p=>!p.endsWith('/'))){
  assert(file.startsWith('package/')&&!file.includes('..'));
  assert.equal(hash(await fs.readFile('node_modules/@nienfos/release-core/'+file.slice(8))),hash(execFileSync('tar',['-xOf',config.archive,file])),'Official release engine differs');
}
const git=(...a)=>execFileSync('git',a,{encoding:'utf8'}).trim();
assert.equal(git('branch','--show-current'),config.branch,'Reserved queue branch changed');
assert.equal(git('status','--porcelain'),'','Queue candidate has uncommitted changes');
const revision=git('rev-parse','HEAD');
if(action==='inspect'){
  console.log(JSON.stringify({configured:true,environment:'dev',revision,publicationAttempted:false,backlogExecutionAttempted:false}));
}else{
  const state=await fs.realpath(config.state),plan=await read(resolve(state,'current.json'));
  assert.equal(plan.revision,revision,'Evidence belongs to another commit');
  for(const key of ['evidenceRoot','privateRoot']){
    const actual=await fs.realpath(plan[key]),rel=relative(state,actual);
    assert(rel&&!rel.startsWith('..')&&!isAbsolute(rel),'Private evidence escapes operator custody');
    assert(!actual.startsWith(root+'/'),'Private release custody belongs outside checkout');
  }
  const dir=resolve(plan.privateRoot,'dev');
  const candidate=await read(resolve(dir,'candidate.json'));
  assert.equal(candidate.revision,revision);assert.equal(candidate.environment,'dev');assert.equal(candidate.worker,'peluquerias-dev');
  assert(candidate.checks.some(c=>c.name==='independent-review'),'Independent Reviewer evidence required');
  const req=createRequire(resolve(root,'package.json'));
  const {digest}=await import(pathToFileURL(req.resolve('@nienfos/release-core')));
  const {assessWebMaintenance}=await import(pathToFileURL(req.resolve('@nienfos/release-core/web-maintenance')));
  const {assertRequiredEvidence}=await import(pathToFileURL(resolve(root,'scripts/release-environment-gates.mjs')));
  const authority={schema:'nienfos.web-maintenance-authority/v1',app:'peluquerias',environment:'dev',worker:'peluquerias-dev',requestRef:'Bridge backlog, user-enabled project DEV automation; preserve original task identity and project scope',expiresAt:new Date(Date.now()+2*3600000).toISOString(),candidateDigest:digest(candidate),requiredChecks:candidate.checks.map(c=>c.name),evidenceRoot:plan.evidenceRoot,scope:'DEV code delivery after independent review; no QA/prod, paid services or external messages'};
  assertRequiredEvidence(candidate,authority,plan.evidenceRoot);
  const decision=assessWebMaintenance({root,artifactRoot:resolve(dir,'artifact'),candidate,authority,currentDeployment:candidate.baselineDeployment});
  assert.equal(decision.ready,true,'Official release gate rejected candidate');
  await fs.writeFile(resolve(dir,'authority.json'),JSON.stringify(authority,null,2)+'\n',{mode:0o600});
  console.log(JSON.stringify({validated:true,revision,environment:'dev',checks:candidate.checks.length}));
}
