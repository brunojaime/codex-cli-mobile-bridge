import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createNativeFeedback} from '../src/native.js';
const config={sourceApp:'native-fixture',sourceDisplayName:'Fixture',environment:'dev',queueScope:'user-a',bridgeUrl:'https://bridge.test'};
const memory=()=>{const data=new Map();return {getItem:async k=>data.get(k)||null,setItem:async(k,v)=>data.set(k,v)}};
test('native queue survives client recreation and isolates subject without erasing originals',async()=>{
 const storage=memory(),a=createNativeFeedback(config,storage);
 await a.capture({screenshot:'cG5n',comment:'test',width:100,height:200,audio:{base64:'dm9pY2U=',mimeType:'audio/webm',durationMs:20,byteLength:5}});
 assert.equal((await createNativeFeedback(config,storage).pending())[0].audioBase64,'dm9pY2U=');
 assert.equal((await createNativeFeedback({...config,queueScope:'user-b'},storage).pending()).length,0);
 await assert.rejects(a.capture({screenshot:'file:///private/capture.png',width:1,height:1}));
});
test('native uncertain response retains queue and retries identical content identity',async()=>{
 const storage=memory();const sent=[];let fail=true;
 const client=createNativeFeedback(config,storage,async(url,request)=>{
  if(url.endsWith('/feedback-contract'))return new Response(JSON.stringify({kind:'codex.feedbackContract',supportedBatchVersions:[1,3],idempotentSubmissions:true,submissionPath:'/feedback-batches/start-session'}));
  assert.equal(url,'https://bridge.test/feedback-batches/start-session');sent.push(JSON.parse(request.body));
  return new Response(JSON.stringify(fail?{}:{job_id:'same-job'}),{status:fail?503:202});
 });
 await client.capture({screenshot:'cG5n',width:1,height:1});
 await assert.rejects(client.send('default'));assert.equal((await client.pending()).length,1);
 fail=false;await client.send('default');assert.equal(sent[0].batchId,sent[1].batchId);assert.equal(sent[0].releaseWhenComplete,false);
 assert.equal((await client.pending()).length,0);
});

test('legacy migration keeps originals and never resends an uncertain legacy batch',async()=>{
 const storage=memory();await storage.setItem('legacy',JSON.stringify([{id:'old',sourceApp:'native-fixture',screenshotPngBase64:'cG5n',comment:'old'}]));await storage.setItem('old-pending','true');
 let posts=0;
 const client=createNativeFeedback({...config,legacyQueueKeys:['legacy'],legacyUncertainKeys:['old-pending']},storage,async()=>{posts++;return new Response('{}')});
 assert.equal((await client.pending()).length,1);
 await client.capture({screenshot:'cG5n',comment:'new',width:1,height:1});
 await assert.rejects(client.send('default'));assert.equal(posts,0);
 await client.reconcileLegacy('received');
 assert.equal((await client.pending()).length,1);assert.equal((await client.pending())[0].comment,'new');
 assert.equal(JSON.parse(await storage.getItem('legacy'))[0].id,'old');
});
