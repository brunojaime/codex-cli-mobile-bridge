import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createFeedbackConfigHandler} from '../src/server.js';
test('consumer session and role are verified server-side, never enabled for other profiles',async()=>{
 const config={sourceApp:'fixture',sourceDisplayName:'Fixture',environment:'dev',allowedOrigins:['https://app.test'],roles:['owner'],bridgeUrl:'https://bridge.test'};
 const request=new Request('https://app.test/api/developer-feedback/config');
 assert.equal((await createFeedbackConfigHandler(config,async()=>({role:'member',user_id:'one'}))(request)).status,403);
 const result=await createFeedbackConfigHandler(config,async()=>({role:'owner',user_id:'one',token:'never exported'}))(request);
 assert.equal((await result.json()).queueScope,'one');assert.equal(result.headers.get('Cache-Control'),'no-store');
 for(const environment of ['qa','prod','production'])assert.equal((await createFeedbackConfigHandler({...config,environment},async()=>{throw Error('must not authenticate')})(request)).status,404);
});
