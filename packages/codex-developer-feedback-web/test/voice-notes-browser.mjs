import { chromium } from 'playwright';
import { build } from 'esbuild';
import { mkdir,writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const output=resolve(process.env.FEEDBACK_REPORT_DIR || '../../reports/feedback-voice-comments-20260927');await mkdir(output,{recursive:true});
const bundle=(await build({stdin:{contents:"import { mountFeedback } from './src/index.js'; window.mountFeedback=mountFeedback;",resolveDir:process.cwd()},bundle:true,format:'iife',write:false})).outputFiles[0].text;
const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
let posts=[],fail=true;
async function setup(denied=false){
 const ctx=await browser.newContext({viewport:{width:390,height:844},hasTouch:true});
 await ctx.addInitScript(denied?()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Denied','NotAllowedError');};}:()=>{const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);window.streams=[];navigator.mediaDevices.getUserMedia=async c=>{const s=await original(c);streams.push(s);return s;};});
 await ctx.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.hostname==='bridge.test'){
   if(u.pathname==='/feedback-workflow-presets')return route.fulfill({json:{default_preset_id:'default',presets:[{id:'default',name:'Generador'}]}});
   posts.push(route.request().postDataJSON());return route.fulfill({status:fail?503:202,json:fail?{}:{job_id:'voice-test'}});
  }
  if(u.pathname==='/feedback.js')return route.fulfill({contentType:'text/javascript',body:bundle});
  return route.fulfill({contentType:'text/html',body:`<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:16px system-ui;background:#eef4f3;color:#19373d;padding:24px}section{background:white;border-radius:12px;padding:24px}</style><h1>Captura de prueba</h1><section>Comentá este cambio con varias notas de voz.</section><script src="/feedback.js"></script><script>window.dispose=mountFeedback({sourceApp:'fixture-app',sourceDisplayName:'Prueba de notas de voz',environment:'dev',allowedOrigins:['https://notes.test'],bridgeUrl:'https://bridge.test'});</script></html>`});
 });const page=await ctx.newPage();await page.goto('https://notes.test');return {ctx,page};
}
async function capture(page){await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await page.locator('#start-drawing').click();await page.locator('#continue').click();}
async function record(page,section='#capture-voice-notes'){const panel=page.locator(section);await panel.getByRole('button',{name:'Grabar nota de voz',exact:true}).click();await panel.locator('.voice-status').filter({hasText:'Grabando'}).waitFor();await page.waitForTimeout(450);await panel.getByRole('button',{name:'Terminar nota',exact:true}).click();await panel.locator('.voice-start').waitFor({state:'visible'});}
try{
 const {ctx,page}=await setup();await capture(page);const panel=page.locator('#capture-voice-notes');
 await record(page);await record(page);assert.equal(await panel.locator('audio').count(),2);
 await panel.locator('audio').first().evaluate(a=>a.play());await page.waitForTimeout(150);await panel.locator('audio').first().evaluate(a=>a.pause());
 await panel.getByRole('button',{name:'Eliminar nota 1',exact:true}).click();assert.equal(await panel.locator('audio').count(),1);
 // Advancing the UI clock beyond the guided trace's 2-minute cap must not stop a voice comment.
 await page.clock.install();await panel.locator('.voice-start').click();await panel.locator('.voice-status').filter({hasText:'Grabando'}).waitFor();await page.clock.runFor(185000);
 assert.equal(await panel.locator('.voice-stop').isVisible(),true);assert.match(await panel.locator('.voice-status').innerText(),/3:05/);
 await panel.locator('.voice-stop').click();await panel.locator('.voice-start').waitFor({state:'visible'});assert.equal(await panel.locator('audio').count(),2);
 assert.equal(await page.locator('#comment').inputValue(),'');await panel.scrollIntoViewIfNeeded();await page.screenshot({path:resolve(output,'multiple-voice-comments.png')});
 // A failed IndexedDB write keeps both notes and the original draft.
 await page.evaluate(()=>{window.put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw new DOMException('full','QuotaExceededError');};});
 await page.locator('#save').click();await page.locator('#status').filter({hasText:'No queda espacio'}).waitFor();assert.equal(await panel.locator('audio').count(),2);
 await page.evaluate(()=>IDBObjectStore.prototype.put=window.put);await page.locator('#save').click();await page.locator('#status').filter({hasText:'Guardado en este navegador'}).waitFor();assert.equal(posts.length,0);
 await page.reload();await page.getByRole('button',{name:'Abrir feedback, 1 pendientes',exact:true}).click();await page.locator('#pending').click();await page.getByRole('button',{name:'Escuchar notas',exact:true}).click();assert.equal(await page.locator('#queued-voice-notes audio').count(),2);await page.locator('#close-voice-review').click();
 await page.locator('#send').click();await page.locator('#status').filter({hasText:'no aceptó'}).waitFor();assert.equal(await page.locator('#queue .item').count(),1);
 const payload=posts[0];assert.equal(payload.message,undefined);assert.equal(payload.items.length,3);assert.equal(payload.items.filter(i=>i.audioBase64).length,2);assert.ok(payload.items[2].audioDurationMs>=185000);assert.ok(payload.items.every(i=>!i.voiceNotes));
 fail=false;await page.locator('#send').click();await page.locator('#status').filter({hasText:'Enviado a Codex'}).waitFor();assert.equal(await page.locator('#queue .item').count(),0);
 // Closing the comment finishes a note; reopening preserves it.
 await page.locator('#close').click();await capture(page);await panel.locator('.voice-start').click();await panel.locator('.voice-status').filter({hasText:'Grabando'}).waitFor();await page.waitForTimeout(400);await page.locator('#close').click();await page.waitForFunction(()=>streams.every(s=>s.getTracks().every(t=>t.readyState==='ended')));
 await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();await page.locator('#pending').click();assert.equal(await panel.locator('audio').count(),1);await page.locator('#discard').click();
 // Extra comments on a narrated trace are separate from its original voice track.
 await page.locator('#new-trace').click();await page.locator('#recording-frames').filter({hasText:'1 capturas'}).waitFor();await page.waitForTimeout(600);await page.locator('#stop-trace').click();await page.locator('#trace-review').waitFor();await record(page,'#trace-voice-notes');await record(page,'#trace-voice-notes');await page.locator('#save-trace').click();await page.locator('#trace-review').waitFor({state:'hidden'});await page.locator('#send').click();await page.locator('#status').filter({hasText:'Enviado a Codex'}).waitFor();assert.equal(posts.at(-1).items.filter(i=>i.audioBase64).length,3);
 // Cancel and unmount release the microphone and never append a discarded note.
 await page.locator('#close').click();await capture(page);await panel.locator('.voice-start').click();await panel.locator('.voice-status').filter({hasText:'Grabando'}).waitFor();await panel.locator('.voice-cancel').click();await panel.locator('.voice-start').waitFor({state:'visible'});assert.equal(await panel.locator('audio').count(),0);
 await panel.locator('.voice-start').click();await panel.locator('.voice-status').filter({hasText:'Grabando'}).waitFor();await page.evaluate(()=>dispose());assert.ok(await page.evaluate(()=>streams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))));await ctx.close();
 const denied=await setup(true);await capture(denied.page);await denied.page.locator('#capture-voice-notes .voice-start').click();await denied.page.locator('.voice-status').filter({hasText:'Permití el micrófono'}).waitFor();assert.equal(await denied.page.locator('#save').isDisabled(),false);await denied.ctx.close();
 const result={multipleNotes:true,textOptional:true,playback:true,deleteIndividual:true,noTwoMinuteCutoff:true,longNoteDurationMs:payload.items[2].audioDurationMs,reloadPreservesNotes:true,quotaFailureRetainsNotes:true,failedSendRetainsQueue:true,orderedAudioInBatch:true,defaultPromptRetainsTranscripts:true,traceCommentsKeepOriginalAudio:true,closeStopsAndKeeps:true,cancelAndUnmountStopMicrophone:true,deniedPermissionHandled:true,realSends:0};await writeFile(resolve(output,'voice-notes-tests.json'),JSON.stringify(result,null,2));console.log(result);
}finally{await browser.close();}
