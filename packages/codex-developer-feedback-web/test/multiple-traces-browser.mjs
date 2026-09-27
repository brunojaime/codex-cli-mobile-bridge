import { chromium } from 'playwright';
import { build } from 'esbuild';
import { mkdir,writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const output=resolve('../../reports/feedback-voice-queue-20260927');await mkdir(output,{recursive:true});
const bundle=(await build({stdin:{contents:"export { mountFeedback } from './src/index.js'; import { TRACE_LIMITS } from './src/trace.js'; window.testTraceLimits = TRACE_LIMITS; import { createQueueStore } from './src/queue-store.js'; window.createTestQueueStore = createQueueStore;",resolveDir:process.cwd()},bundle:true,format:'esm',write:false})).outputFiles[0].text;
const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
let posts=[];
const config={sourceApp:'proyecto-inmobiliaria',sourceDisplayName:'Chrem · Prueba local',environment:'dev',allowedOrigins:['https://flow.test'],bridgeUrl:'https://bridge.test'};
async function setup(viewport={width:390,height:844}, denied=false){
 const ctx=await browser.newContext({viewport,hasTouch:true});
 await ctx.addInitScript(denied?()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Denied','NotAllowedError');};}:()=>{const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);window.testStreams=[];navigator.mediaDevices.getUserMedia=async c=>{const s=await original(c);testStreams.push(s);return s;};});
 await ctx.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.hostname==='bridge.test'){
   if(url.pathname==='/feedback-workflow-presets')return route.fulfill({json:{default_preset_id:'generator_only',presets:[{id:'generator_only',name:'Generador'}]}});
   posts.push(route.request().postDataJSON());return route.fulfill({status:202,json:{job_id:'test-flow-job'}});
  }
  if(url.pathname==='/feedback.js')return route.fulfill({contentType:'text/javascript',body:bundle});
  return route.fulfill({contentType:'text/html',body:`<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font:16px system-ui;background:#f0f5fa;color:#163c61}header{background:white;border-bottom:1px solid #ccd8e4;padding:18px}main{padding:24px}button{font:inherit;padding:14px;border:0;border-radius:8px;background:#163c61;color:white}section{background:white;padding:24px;margin:20px 0;border-radius:8px}input{padding:14px}nav{position:fixed;bottom:0;width:100%;background:white;padding:18px}h1{font-size:28px}</style><header>RD / Chrem · Prueba de herramientas</header><main><h1 id="heading">Pantalla original</h1><p>La pantalla mantiene su tamaño al dibujar.</p><section><h2>Recorrido de prueba</h2><p>Datos sintéticos para validar navegación, capturas y voz.</p><button id="next" onclick="document.querySelector('#heading').textContent='Detalle de la propiedad';history.pushState({},'', '/detalle');">Abrir detalle</button></section><input type="password" value="test-secret"><div data-feedback-private>CONTENIDO PRIVADO DE PRUEBA</div><details><summary>Filtro cerrado</summary><div>OPCIONES OCULTAS</div></details></main><nav>Inicio　　Propiedades　　Consultas</nav><script type="module">import{mountFeedback}from'/feedback.js';window.disposeFeedback=mountFeedback(${JSON.stringify(config)});</script></html>`});
 });
 const page=await ctx.newPage();await page.goto('https://flow.test');return{ctx,page};
}
const readQueue = page => page.evaluate(() => new Promise((resolve,reject) => {
 const r=indexedDB.open('codex-developer-feedback',1);r.onerror=()=>reject(r.error);r.onsuccess=()=>{const db=r.result;const tx=db.transaction('queues');const get=tx.objectStore('queues').getAll();get.onsuccess=()=>resolve(get.result.flat());tx.oncomplete=()=>db.close();};
}));
try {
 const {ctx,page}=await setup();
 await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();
 await page.getByRole('button',{name:'Grabar recorrido con voz'}).click();
 await page.locator('#recording-frames').filter({hasText:'1 capturas'}).waitFor();
 assert.equal(await page.evaluate(()=>testTraceLimits.intervalMs),1000);
 await page.waitForTimeout(2200);assert.match(await page.locator('#recording-frames').innerText(),/^1 capturas/,'unchanged intervals are omitted');
 await page.evaluate(()=>document.querySelector('#heading').textContent='Cambio para capturar en un segundo');
 await page.locator('#recording-frames').filter({hasText:'2 capturas'}).waitFor({timeout:1800});
 await page.waitForTimeout(2100);assert.match(await page.locator('#recording-frames').innerText(),/^2 capturas/);
 for(let i=1;i<=10;i++){
  if(i>1){await page.getByRole('button',{name:'Nuevo recorrido',exact:true}).click();await page.locator('#recording-frames').filter({hasText:'1 capturas'}).waitFor();}
  await page.waitForTimeout(650);
  await page.getByRole('button',{name:'Detener recorrido',exact:true}).click();await page.locator('#trace-review').waitFor();
  await page.locator('#trace-comment').fill('Recorrido '+i);
  if(i===10){
   await page.evaluate(()=>{window.originalPut=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw new DOMException('Full','QuotaExceededError');};});
   await page.getByRole('button',{name:'Guardar recorrido',exact:true}).click();await page.locator('#trace-note').filter({hasText:'No queda espacio'}).waitFor();
   assert.equal((await readQueue(page)).length,9,'quota failure preserves previously committed queue');
   assert.equal(await page.locator('#trace-review').isVisible(),true,'unsaved recording retained');
   await page.evaluate(()=>IDBObjectStore.prototype.put=originalPut);
  }
  await page.getByRole('button',{name:'Guardar recorrido',exact:true}).click();await page.locator('#trace-review').waitFor({state:'hidden'});
  assert.equal((await readQueue(page)).length,i);
 }
 await page.screenshot({path:resolve(output,'ten-voice-traces.png'),fullPage:false});assert.equal(posts.length,0);
 await page.reload();await page.getByRole('button',{name:'Abrir feedback, 10 pendientes',exact:true}).click();await page.getByRole('button',{name:'Ver pendientes (10)',exact:true}).click();
 const saved=await readQueue(page);assert.equal(saved.length,10);assert.equal(new Set(saved.map(i=>i.id)).size,10);assert.ok(saved.every(i=>i.hasAudio&&i.audioBase64.length>0));
 await page.getByRole('button',{name:'Enviar a Codex',exact:true}).click();await page.locator('#status').filter({hasText:'Enviado a Codex'}).waitFor();assert.equal(posts.length,1);assert.equal(posts[0].items.filter(i=>i.hasAudio).length,10,'one audio per trace');assert.equal((await readQueue(page)).length,0);
 // Migration and queues larger than the old 4 MB limit; synthetic local data only.
 const migration=await page.evaluate(async()=>{
  const key='migration-test';const old=[{id:'legacy-image',screenshotPngBase64:'a'.repeat(2000000)}];localStorage.setItem(key,JSON.stringify(old));
  const store=createTestQueueStore(key);const migrated=await store.load();const sourceRemoved=localStorage.getItem(key)===null;
  const many=Array.from({length:12},(_,i)=>({id:'large-'+i,screenshotPngBase64:'b'.repeat(400000)}));await store.save(many);const loaded=await store.load();await store.close();return {migrated:migrated[0].id,sourceRemoved,count:loaded.length,chars:JSON.stringify(loaded).length};
 });assert.equal(migration.migrated,'legacy-image');assert.ok(migration.sourceRemoved);assert.equal(migration.count,12);assert.ok(migration.chars>4000000);
 await ctx.close();
 const result={realRecordedTraces:10,independentAudioTracks:10,savedWithoutSending:true,persistsAfterReload:true,noEightItemLimit:true,queueOverFourMillionChars:migration.chars,migrationPreservesLegacy:true,quotaFailurePreservesDraftAndQueue:true,intervalMs:1000,unchangedFramesOmitted:true,changedFrameCapturedWithin1800ms:true,simulatedBatchRequests:1,realSubmissions:0};
 await writeFile(resolve(output,'multiple-traces-tests.json'),JSON.stringify(result,null,2));console.log(result);
}finally{await browser.close();}
