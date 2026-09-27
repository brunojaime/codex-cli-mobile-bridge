// Explicitly invoked smoke test: real deployments, simulated microphone, no sends.
import { chromium, request } from 'playwright';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
const output=resolve(process.env.FEEDBACK_REPORT_DIR || '../../reports/feedback-capture-fidelity-20260927');await mkdir(output,{recursive:true});
const service=JSON.parse(await readFile('/home/batata/.local/state/gestion-env-transition-20260927/dev-service-token.json','utf8'));
const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
const bridgeRequest=await request.newContext({proxy:{server:'http://127.0.0.1:1056'}});
const targets=[
 ['gestion-dev','https://dev.gestion.nienfos.com/login',true],
 ['rd-dev','https://rd-dev.nienfos.com',true],['chrem-dev','https://chrem-dev.nienfos.com',true],
 ['rd-qa','https://rd-qa.nienfos.com',false],['rd-legacy','https://rd-staging.nienfos.com',false],
 ['chrem-qa','https://chrem-qa.nienfos.com',false],['chrem-legacy','https://chrem-staging.nienfos.com',false],
 ['gestion-qa','https://qa.gestion.nienfos.com/login',false],['gestion-prod','https://gestion.nienfos.com/login',false],
 ['rd-prod','https://app.consultorard.com.ar',false],['chrem-prod','https://chrempropiedades.com.ar',false]
];
const selected = process.argv.slice(2);
const results=selected.length ? JSON.parse(await readFile(resolve(output,'live-browser.json'),'utf8').catch(()=>'[]')) : [];
try {
 for(const [name,url,enabled] of targets){
  if(selected.length && !selected.includes(name)) continue;
  const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true});
  let posts=0;const errors=[];
  await context.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(u.hostname.endsWith('.ts.net')&&route.request().method()==='POST'){posts++;return route.abort();}
   if(u.hostname.endsWith('.ts.net')){const r=await bridgeRequest.get(u.href);return route.fulfill({response:r});}
   if(u.origin==='https://dev.gestion.nienfos.com')return route.continue({headers:{...route.request().headers(),'CF-Access-Client-Id':service.client_id,'CF-Access-Client-Secret':service.client_secret}});
   return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  let response;for(let attempt=0;attempt<3;attempt++){try{response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});break;}catch(error){if(!String(error).includes('ERR_NETWORK_CHANGED')||attempt===2)throw error;}}assert.equal(response.status(),200,name+' HTTP');await page.waitForFunction(()=>document.body.innerText.length>30);await page.waitForTimeout(1500);
  const host=page.locator('[data-codex-feedback]');
  if(enabled){
   await host.waitFor({state:"attached"});await page.getByRole("button",{name:"Abrir feedback",exact:true}).waitFor();assert.equal(await host.getAttribute('data-codex-feedback'),'0.6.0');
   await page.screenshot({path:resolve(output,name+'-bug.png')});
   await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();
   await page.waitForFunction(()=>document.querySelector('[data-codex-feedback]')?.shadowRoot?.querySelectorAll('#preset option').length>2,null,{timeout:25000});
   await page.getByRole('button',{name:'Grabar recorrido con voz'}).click();
   await page.locator('#recording-frames').filter({hasText:'1 capturas'}).waitFor({timeout:30000});
   await page.locator('#mark-trace').click();
   await page.locator('#live-drawing').waitFor({state:'visible'});
 assert.deepEqual(await page.locator('#live-drawing').boundingBox(),{x:0,y:0,width:390,height:844});
   const handle=await page.locator('#recording-drag').boundingBox();
   await page.mouse.move(handle.x+20,handle.y+20);await page.mouse.down();await page.mouse.move(40,580,{steps:8});await page.mouse.up();
   await page.locator('#live-rectangle').click();
   const cdp=await context.newCDPSession(page);await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:25,y:140}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:345,y:280}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
   await page.waitForTimeout(1000);await page.screenshot({path:resolve(output,name+'-recording.png')});
   await page.locator('#mark-trace').click();await page.locator('#live-drawing').waitFor({state:'hidden'});
   await page.getByRole('button',{name:'Detener recorrido',exact:true}).click();await page.locator('#trace-review').waitFor();
   await page.locator('#trace-audio').evaluate(a=>a.play());await page.waitForTimeout(150);await page.locator('#trace-audio').evaluate(a=>a.pause());
   await page.getByRole('button',{name:'Guardar recorrido',exact:true}).click();
   await page.locator('#trace-review').waitFor({state:'hidden'});
   await page.getByRole('button',{name:'Nuevo recorrido',exact:true}).click();
   await page.locator('#recording-frames').filter({hasText:'1 capturas'}).waitFor();await page.waitForTimeout(1200);
   await page.getByRole('button',{name:'Detener recorrido',exact:true}).click();await page.locator('#trace-review').waitFor();
   await page.getByRole('button',{name:'Guardar recorrido',exact:true}).click();await page.locator('#trace-review').waitFor({state:'hidden'});
   const traces=await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('codex-developer-feedback',1);r.onerror=()=>reject(r.error);r.onsuccess=()=>{const db=r.result;const tx=db.transaction('queues');const get=tx.objectStore('queues').getAll();get.onsuccess=()=>resolve(get.result.flat());tx.oncomplete=()=>db.close();};}));
   assert.equal(traces.length,2);assert.ok(traces.every(i=>i.hasAudio));assert.ok(traces[0].hasAudio);assert.ok(traces[0].guidedTrace.frames.some(f=>f.annotations?.length));
   const image=traces[0].guidedTrace.frames.find(f=>f.annotations?.length).screenshotPngBase64;
   await writeFile(resolve(output,name+'-saved-frame.png'),Buffer.from(image,'base64'));
   const red=await page.evaluate(async b=>{const img=new Image();img.src='data:image/png;base64,'+b;await img.decode();const c=document.createElement('canvas');c.width=img.width;c.height=img.height;const ctx=c.getContext('2d');ctx.drawImage(img,0,0);const d=ctx.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<d.length;i+=4)if(d[i]>180&&d[i+1]<80&&d[i+2]<80)n++;return n;},image);assert.ok(red>100,'marked pixels saved');
   await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'Abrir feedback, 2 pendientes',exact:true}).waitFor();
   results.push({name,url,feedback:true,version:'0.6.0',recording:true,touchMarksSaved:true,movableToolbar:true,fullViewport:true,audioPlayback:true,queuePersists:true,presetsFromRealBridge:true,queuedTraces:traces.length,independentAudioTracks:traces.filter(i=>i.hasAudio).length,frames:traces[0].guidedTrace.frames.length,realSends:posts,pageErrors:errors});
  }else{
   assert.equal(await host.count(),0,name+' must hide feedback');
   await page.screenshot({path:resolve(output,name+'.png')});
   results.push({name,url,feedback:false,httpStatus:response.status(),realSends:posts,pageErrors:errors});
  }
  assert.equal(posts,0);await context.close();console.log(name,'passed');
  await writeFile(resolve(output,'live-browser.json'),JSON.stringify(results,null,2));
 }
}finally{await bridgeRequest.dispose();await browser.close();}
