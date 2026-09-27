import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {operate} from './release.mjs';
function fixture(){const root=mkdtempSync(join(tmpdir(),'nienfos-pipeline-test-'));mkdirSync(join(root,'infra/mobile'),{recursive:true});mkdirSync(join(root,'apps/mobile'),{recursive:true});const project={kind:'nienfos.mobile-project',version:1,sourceApp:'test-app',framework:'react-native-expo',sourceRoot:'apps/mobile',profiles:{preview:{apiBaseUrl:'https://qa.nienfos.com',androidApplicationId:'com.nienfos.test.preview'}}};const release={toolkitVersion:'0.1.0',repository:'owner/test-app',version:'0.1.0',androidBuild:1,profile:'preview'};writeFileSync(join(root,'infra/mobile/project.json'),JSON.stringify(project));writeFileSync(join(root,'infra/mobile/release.json'),JSON.stringify(release));spawnSync('git',['init','-q'],{cwd:root});return{root,project,release,close:()=>rmSync(root,{recursive:true,force:true})};}
test('status cannot claim a release without evidence',()=>{const f=fixture();try{const s=operate(f.root,'status');assert.equal(s.receiptExists,false);assert.equal(s.dirty,true);assert.equal(s.profile,'preview');}finally{f.close();}});
test('dirty source cannot build or publish',()=>{const f=fixture();try{assert.throws(()=>operate(f.root,'build'),/clean committed/);assert.throws(()=>operate(f.root,'publish',{approval:'chat:approved'}),/clean committed/);}finally{f.close();}});
test('incompatible toolkit and insecure API fail before execution',()=>{const f=fixture();try{f.release.toolkitVersion='2.0.0';writeFileSync(join(f.root,'infra/mobile/release.json'),JSON.stringify(f.release));assert.throws(()=>operate(f.root,'status'),/mismatch/);f.release.toolkitVersion='0.1.0';writeFileSync(join(f.root,'infra/mobile/release.json'),JSON.stringify(f.release));f.project.profiles.preview.apiBaseUrl='http://localhost:8000';writeFileSync(join(f.root,'infra/mobile/project.json'),JSON.stringify(f.project));assert.throws(()=>operate(f.root,'status'),/HTTPS/);}finally{f.close();}});
