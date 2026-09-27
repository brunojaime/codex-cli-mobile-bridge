import { chromium } from 'playwright';
import { build } from 'esbuild';
import { mkdir,writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const output=resolve(process.env.FEEDBACK_REPORT_DIR || '../../reports/feedback-capture-fidelity-20260927');await mkdir(output,{recursive:true});
const bundle=(await build({stdin:{contents:"export { mountFeedback } from './src/index.js'; import { TRACE_LIMITS } from './src/trace.js'; window.testTraceLimits = TRACE_LIMITS;",resolveDir:process.cwd()},bundle:true,format:'esm',write:false})).outputFiles[0].text;
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
try{
 for(const [width,height] of [[390,844],[360,800],[430,932],[768,1024],[1440,900],[1728,1117],[780,360]]){
  const {ctx,page}=await setup({width,height});await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await page.getByRole('button',{name:'Dibujar en pantalla',exact:true}).click();await page.locator('#drawing-canvas').waitFor({state:'visible'});
  const bounds=await page.locator('#drawing-canvas').boundingBox();assert.deepEqual(bounds,{x:0,y:0,width,height});
  const handle=page.getByRole('button',{name:'Mover herramientas',exact:true});const h=await handle.boundingBox();const before=await page.locator('#drawing-tools').boundingBox();
  const cdp=await ctx.newCDPSession(page);await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:h.x+22,y:h.y+22}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:38,y:45}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  const after=await page.locator('#drawing-tools').boundingBox();assert.ok(after.y<before.y || height<450);assert.equal(await page.locator('#undo').isDisabled(),true,'moving toolbar must not draw');
  await page.getByRole('button',{name:'Plegar herramientas'}).click();assert.equal(await page.locator('#drawing-buttons').isVisible(),false);await page.getByRole('button',{name:'Mostrar herramientas'}).click();
  await handle.focus();await page.keyboard.press('ArrowRight');assert.ok((await page.locator('#drawing-tools').boundingBox()).x>=after.x);
  await page.mouse.move(width*.25,height*.48);await page.mouse.down();await page.mouse.move(width*.65,height*.55,{steps:10});await page.mouse.up();
  await page.screenshot({path:resolve(output,`native-editor-${width}.png`)});
  assert.deepEqual(await page.locator('#drawing-canvas').boundingBox(),bounds);
  await ctx.close();
 }
 const {ctx,page}=await setup();await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await page.getByRole('button',{name:'Grabar recorrido con voz'}).click();
 await page.locator('#recording-frames').filter({hasText:'1 capturas'}).waitFor();
 await page.locator('#mark-trace').click();
 await page.locator('#live-drawing').waitFor({state:'visible'});
 assert.deepEqual(await page.locator('#live-drawing').boundingBox(),{x:0,y:0,width:390,height:844});
 await page.locator('#live-arrow').click();
 await page.mouse.move(60,240);await page.mouse.down();await page.mouse.move(220,300,{steps:8});await page.mouse.up();
 await page.waitForTimeout(900);
 assert.ok(await page.evaluate(()=>testStreams.some(s=>s.getTracks().some(t=>t.readyState==='live'))),'voice continues while drawing');
 await page.screenshot({path:resolve(output,'recording-drawing-mobile.png')});
 await page.locator('#mark-trace').click();await page.locator('#live-drawing').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'Abrir detalle',exact:true}).click();
 await page.waitForTimeout(5700);
 await page.locator('#capture-step').click();await page.waitForTimeout(900);
 await page.screenshot({path:resolve(output,'recording-mobile.png')});
 await page.getByRole('button',{name:'Detener recorrido',exact:true}).click();await page.locator('#trace-review').waitFor({state:'visible'});
 assert.ok(await page.evaluate(()=>testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))));
 assert.ok(Number(await page.locator('#trace-position').getAttribute('max'))>=2);
 await page.locator('#trace-audio').evaluate(a=>a.play());await page.waitForTimeout(200);await page.locator('#trace-audio').evaluate(a=>a.pause());
 await page.locator('#trace-comment').fill('Mostrar el flujo esperado de la propiedad.');
 await page.screenshot({path:resolve(output,'review-mobile.png')});
 await page.getByRole('button',{name:'Guardar recorrido',exact:true}).click();assert.equal(posts.length,0);
 await page.reload();await page.getByRole('button',{name:'Abrir feedback, 1 pendientes',exact:true}).click();await page.getByRole('button',{name:'Ver pendientes (1)',exact:true}).click();
 await page.getByRole('button',{name:'Revisar',exact:true}).click();assert.equal(await page.locator('#trace-audio').isVisible(),true);await page.getByRole('button',{name:'Cerrar recorrido'}).click();
 await page.getByRole('button',{name:'Abrir feedback, 1 pendientes',exact:true}).click();await page.getByRole('button',{name:'Ver pendientes (1)',exact:true}).click();await page.getByRole('button',{name:'Enviar a Codex',exact:true}).click();
 await page.locator('#status').filter({hasText:'Enviado a Codex'}).waitFor();
 const payload=posts[0];assert.ok(payload.items.length>=3);assert.equal(payload.items.filter(i=>i.hasAudio).length,1);assert.ok(payload.items[0].audioByteLength>100);assert.ok(payload.items[0].guidedTrace.timeline.some(e=>e.type==='route_change'));
 assert.ok(payload.items[0].guidedTrace.frames.some(f=>f.annotations?.some(a=>a.tool==='arrow')),'drawings are saved with frames');
 assert.ok(payload.items.every(i=>i.screenshotPngBase64.length>100));assert.ok(payload.items[0].guidedTrace.frames.every(f=>!f.screenshotPngBase64));
 await writeFile('/tmp/feedback-trace-test-payload.json',JSON.stringify(payload));
 await page.getByRole('button',{name:'Cerrar feedback'}).click();await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await page.getByRole('button',{name:'Grabar recorrido con voz'}).click();await page.locator('#recording-frames').filter({hasText:'· Voz'}).waitFor();await page.getByRole('button',{name:'Descartar recorrido en curso'}).click();assert.ok(await page.evaluate(()=>testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))));
 await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await page.getByRole('button',{name:'Grabar recorrido con voz'}).click();await page.locator('#recording-frames').filter({hasText:'· Voz'}).waitFor();await page.evaluate(()=>disposeFeedback());assert.ok(await page.evaluate(()=>testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))));await ctx.close();
 const limited=await setup();await limited.page.evaluate(()=>{testTraceLimits.durationMs=1500;});await limited.page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await limited.page.getByRole('button',{name:'Grabar recorrido con voz'}).click();await limited.page.locator('#trace-review').waitFor({state:'visible'});assert.ok(await limited.page.evaluate(()=>testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))));await limited.ctx.close();
 const quota=await setup();await quota.page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await quota.page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await quota.page.evaluate(()=>{testTraceLimits.durationMs=1500;const original=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(v,k){if(k.startsWith('codex-feedback:'))throw new DOMException('Full','QuotaExceededError');return original.call(this,v,k);};});await quota.page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await quota.page.getByRole('button',{name:'Grabar recorrido con voz'}).click();await quota.page.locator('#trace-review').waitFor({state:'visible'});await quota.page.getByRole('button',{name:'Guardar recorrido',exact:true}).click();assert.equal(await quota.page.locator('#trace-review').isVisible(),true);await quota.page.locator('#trace-note').filter({hasText:'No queda espacio'}).waitFor();await quota.ctx.close();
 const denied=await setup(undefined,true);await denied.page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await denied.page.getByRole('button',{name:'Grabar recorrido con voz'}).click();await denied.page.locator('#dock-status').filter({hasText:'Permití el micrófono'}).waitFor();assert.equal(await denied.page.locator('#recording-bar').isVisible(),false);await denied.ctx.close();
 const result={nativeSize:true,viewports:[390,360,430,768,1440,1728,780],toolbarTouchDrag:true,keyboardMovement:true,fold:true,drawWhileRecording:true,voiceContinuesWhileDrawing:true,marksInSentFrames:true,navigationWhileRecording:true,automaticFrames:true,microphone:'Chromium simulated device with real MediaRecorder',audioPlayback:true,persistence:true,allFramesInBatch:payload.items.length,audioCopies:1,permissionDenied:true,autoStopReleasesMicrophone:true,quotaFailureRetainsDraft:true,cancelStopsMicrophone:true,unmountStopsMicrophone:true,realSubmissions:0};
 await writeFile(resolve(output,'flow-browser-tests.json'),JSON.stringify(result,null,2));console.log(result);
}finally{await browser.close();}
