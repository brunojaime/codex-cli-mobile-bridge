// Explicit deployment smoke: real apps, simulated microphone, no submissions.
import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const output=resolve(process.env.FEEDBACK_REPORT_DIR || '../../reports/feedback-voice-comments-20260927');await mkdir(output,{recursive:true});
const service=JSON.parse(await readFile('/home/batata/.local/state/gestion-env-transition-20260927/dev-service-token.json','utf8'));
const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
const targets=[['gestion','https://dev.gestion.nienfos.com/login'],['rd','https://rd-dev.nienfos.com'],['chrem','https://chrem-dev.nienfos.com']];
const results=[];
try{
 for(const[name,url] of targets){
  if(process.argv.length>2&&!process.argv.slice(2).includes(name))continue;
  const ctx=await browser.newContext({viewport:{width:390,height:844},hasTouch:true});let sends=0;const errors=[];
  await ctx.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname.endsWith('.ts.net')&&route.request().method()==='POST'){sends++;return route.abort();}if(u.origin==='https://dev.gestion.nienfos.com')return route.continue({headers:{...route.request().headers(),'CF-Access-Client-Id':service.client_id,'CF-Access-Client-Secret':service.client_secret}});return route.continue();});
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});assert.equal(response.status(),200);
  await page.getByRole('button',{name:'Abrir feedback',exact:true}).waitFor();assert.equal(await page.locator('[data-codex-feedback]').getAttribute('data-codex-feedback'),'0.7.0');
  await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await page.locator('#start-drawing').click();await page.locator('#continue').click();const panel=page.locator('#capture-voice-notes');
  for(let i=0;i<2;i++){await panel.locator('.voice-start').click();await panel.locator('.voice-status').filter({hasText:'Grabando'}).waitFor();await page.waitForTimeout(1300);await panel.locator('.voice-stop').click();await panel.locator('.voice-start').waitFor({state:'visible'});}
  assert.equal(await panel.locator('audio').count(),2);await panel.locator('audio').first().evaluate(a=>a.play());await page.waitForTimeout(150);await panel.locator('audio').first().evaluate(a=>a.pause());assert.equal(await page.locator('#comment').inputValue(),'');
  await panel.scrollIntoViewIfNeeded();await page.screenshot({path:resolve(output,name+'-voice-comments.png')});await page.locator('#save').click();await page.locator('#status').filter({hasText:'Guardado en este navegador'}).waitFor();
  await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'Abrir feedback, 1 pendientes',exact:true}).click();await page.locator('#pending').click();await page.getByRole('button',{name:'Escuchar notas',exact:true}).click();assert.equal(await page.locator('#queued-voice-notes audio').count(),2);
  const items=await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('codex-developer-feedback',1);r.onerror=()=>reject(r.error);r.onsuccess=()=>{const db=r.result;const tx=db.transaction('queues');const q=tx.objectStore('queues').getAll();q.onsuccess=()=>resolve(q.result.flat());tx.oncomplete=()=>db.close();};}));
  assert.equal(items.length,1);assert.equal(items[0].voiceNotes.length,2);assert.equal(new Set(items[0].voiceNotes.map(n=>n.id)).size,2);assert.ok(items[0].voiceNotes.every(n=>n.audioBase64.length>100&&n.audioDurationMs>=1000));assert.equal(sends,0);assert.deepEqual(errors,[]);
  results.push({name,url,version:'0.7.0',notes:2,textOptional:true,audioPlayback:true,independentNotes:true,persistsAfterReload:true,realSubmissions:sends,pageErrors:errors});await writeFile(resolve(output,'live-voice-'+name+'.json'),JSON.stringify(results.at(-1),null,2));console.log(name,'passed');await ctx.close();
 }
}finally{await browser.close();}
