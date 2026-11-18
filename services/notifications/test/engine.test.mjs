import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {generateKeyPairSync} from 'node:crypto';
import {openDatabase} from '../src/sqlite.mjs';
import {createEngine,hash} from '../src/engine.mjs';
const privateKey=generateKeyPairSync('rsa',{modulusLength:2048,privateKeyEncoding:{type:'pkcs8',format:'pem'},publicKeyEncoding:{type:'spki',format:'pem'}}).privateKey;
function fixture(t){
 const dir=mkdtempSync(join(tmpdir(),'bridge-push-')),path=join(dir,'chat.sqlite');
 const seed=new DatabaseSync(path);
 seed.exec(`CREATE TABLE sessions(id TEXT PRIMARY KEY,title TEXT,workspace_path TEXT,workspace_name TEXT,active_agent_run_id TEXT,archived_at TEXT);
 CREATE TABLE messages(id TEXT PRIMARY KEY,session_id TEXT,role TEXT,status TEXT,run_id TEXT,job_id TEXT,created_at TEXT,updated_at TEXT,content TEXT);
 CREATE TABLE jobs(id TEXT PRIMARY KEY,session_id TEXT,status TEXT,auto_chain_processed INTEGER,run_id TEXT);
 INSERT INTO sessions VALUES('chat','Chat','/project','Project','run',NULL);`);seed.close();
 const db=openDatabase(path),sent=[];
 const time=Date.now();
 const engine=createEngine({db,environment:'prod',projectId:'bridge-test-prod',origin:'https://bridge.example.com',bridgeId:'bridge-id',now:()=>time,
  credential:{project_id:'bridge-test-prod',client_email:'sender@bridge-test-prod.iam.gserviceaccount.com',private_key:privateKey},
  fetcher:async(url,options)=>{
   if(url.includes('oauth2'))return Response.json({access_token:'unit-test-token',token_type:'Bearer',expires_in:3600});
   sent.push(JSON.parse(options.body));return Response.json({name:'projects/test/messages/accepted'});
  }});
 t.after(()=>{db.connection.close();rmSync(dir,{recursive:true,force:true});});
 return {db:db.connection,engine,sent,time};
}
async function register(f,verified=true){
 const id='12345678-1234-4234-8234-123456789abc';
 f.db.prepare('INSERT INTO bridge_push_installations VALUES(?,?,1,?,?,?)').run(id,hash('a'.repeat(43)),verified?f.time:null,f.time,f.time);
 await f.engine.store.register({appId:'codex-mobile',environment:'prod'},{userId:'bridge-owner',tenantId:'bridge',sessionId:id},{installationId:id,platform:'android',fid:'x'.repeat(64)},f.time);
 return id;
}
function finish(f,id='generator'){
 f.db.prepare("INSERT INTO messages VALUES(?,'chat','assistant','completed','run',?, ?,?,'Private reply')").run(id,id,new Date(f.time).toISOString(),new Date(f.time).toISOString());
 f.db.prepare("INSERT INTO jobs VALUES(?,'chat','completed',1,'run')").run(id);
}
test('transaction rollback leaves no completion intent',t=>{
 const f=fixture(t);f.db.exec('BEGIN');finish(f);f.db.exec('ROLLBACK');
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM bridge_push_events').get().n,0);
});
test('Generator/Reviewer sends once after whole project is idle, with opaque data',async t=>{
 const f=fixture(t);await register(f);finish(f);
 await f.engine.tick();assert.equal(f.sent.length,0);
 finish(f,'reviewer');f.db.exec("UPDATE sessions SET active_agent_run_id=NULL");
 await f.engine.tick();await f.engine.tick();assert.equal(f.sent.length,1);
 const payload=f.sent[0].message;
 assert.equal(payload.notification,undefined);assert.equal(payload.android.priority,'HIGH');
 assert.equal(JSON.stringify(payload).includes('Private reply'),false);
 assert.equal(payload.data.bridgeId,'bridge-id');
 assert.equal(f.db.prepare('SELECT message_id FROM bridge_push_events').get().message_id,'reviewer');
});
test('reading the project before dispatch cancels the pending push',async t=>{
 const f=fixture(t),id=await register(f);finish(f);f.db.exec('UPDATE sessions SET active_agent_run_id=NULL');
 f.db.prepare('INSERT INTO bridge_push_reads VALUES(?,?,?)').run(id,'project:/project',f.time+1);
 await f.engine.tick();assert.equal(f.sent.length,0);
 assert.equal(f.db.prepare('SELECT state FROM nienfos_push_outbox').get().state,'cancelled');
});
test('unverified or revoked installations never receive project completions',async t=>{
 const f=fixture(t);await register(f,false);finish(f);f.db.exec('UPDATE sessions SET active_agent_run_id=NULL');
 await f.engine.tick();assert.equal(f.sent.length,0);
});
test('other active chats in a project hold dispatch',async t=>{
 const f=fixture(t);await register(f);finish(f);
 f.db.exec("UPDATE sessions SET active_agent_run_id=NULL;INSERT INTO sessions VALUES('other','Other','/project','Project','other-run',NULL)");
 await f.engine.tick();assert.equal(f.sent.length,0);
 f.db.exec("UPDATE sessions SET active_agent_run_id=NULL");await f.engine.tick();assert.equal(f.sent.length,1);
});
