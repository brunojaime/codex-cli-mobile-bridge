import { chromium } from 'playwright';
import { build } from 'esbuild';
import { mkdir,writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const output=resolve(process.env.FEEDBACK_REPORT_DIR || '../../reports/feedback-capture-fidelity-20260927');await mkdir(output,{recursive:true});
const bundle=(await build({stdin:{contents:"import { captureViewport } from './src/capture.js'; import { createLiveDrawing } from './src/live-drawing.js'; window.captureViewport=captureViewport; window.createLiveDrawing=createLiveDrawing;",resolveDir:process.cwd()},bundle:true,format:'iife',write:false})).outputFiles[0].text;
const browser=await chromium.launch({headless:true});const broken=!!process.env.EXPECT_BROKEN;
const results=[];
async function setup({blockCloneCss=false,width=390}={}){
 const ctx=await browser.newContext({viewport:{width,height:844},hasTouch:true});let cssRequests=0;
 await ctx.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/feedback.js')return route.fulfill({contentType:'text/javascript',body:bundle});
  if(url.pathname==='/assets/style.css'){
   cssRequests++;if(blockCloneCss&&cssRequests>1)return route.fulfill({status:503,body:'unavailable'});
   return route.fulfill({contentType:'text/css',headers:{'cache-control':'no-store'},body:'body{margin:0;background:rgb(20,90,160);font:16px Arial;color:white;height:2200px}#target{position:absolute;left:80px;top:250px;width:180px;height:100px;background:rgb(20,180,90)}#fixed{position:fixed;bottom:0;left:0;width:100%;height:40px;background:rgb(240,180,30)}#inner{position:absolute;top:1050px;height:180px;overflow:auto;width:300px;background:white}#inner div{height:450px}#inner i{display:block;height:40px;background:rgb(160,40,160)}'});
  }
  return route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/assets/style.css"></head><body><h1>Captura de prueba</h1><div id="target"></div><div id="inner"><div></div><i></i></div><div id="fixed"></div><div data-codex-feedback><canvas id="ink" hidden style="position:fixed;inset:0;touch-action:none;z-index:99"></canvas></div><script src="/feedback.js"></script></body></html>'});
 });
 const page=await ctx.newPage();await page.goto('https://capture.test');return {ctx,page,cssRequests:()=>cssRequests};
}
const save=async(page,name)=>{const data=await page.evaluate(()=>window.shot.canvas.toDataURL().split(',')[1]);await writeFile(resolve(output,name+'.png'),Buffer.from(data,'base64'));};
const sample=(page,x,y)=>page.evaluate(([x,y])=>[...shot.canvas.getContext('2d').getImageData(x,y,1,1).data].slice(0,3),[x,y]);
try{
 const css=await setup({blockCloneCss:true});await css.page.screenshot({path:resolve(output,'css-original.png')});
 await css.page.evaluate(async()=>window.shot=await captureViewport());await save(css.page,broken?'css-before':'css-after');
 const color=await sample(css.page,15,160);results.push({test:'loaded CSS preserved when clone cannot reload it',color,cssRequests:css.cssRequests()});
 if(broken)assert.notDeepEqual(color,[20,90,160]);else assert.deepEqual(color,[20,90,160]);await css.ctx.close();
 for(const width of [390,1440]){
  const c=await setup({width});await c.page.evaluate(async()=>{window.drawing=createLiveDrawing(document.querySelector('#ink'),()=>{});await drawing.show();drawing.tool='arrow';});
  await c.page.mouse.move(35,200);await c.page.mouse.down();await c.page.mouse.move(120,275,{steps:8});await c.page.mouse.up();
  await c.page.evaluate(()=>document.querySelector('#target').style.top='500px');
  await c.page.evaluate(async()=>window.shot=await drawing.capture());await save(c.page,`marks-${broken?'before':'after'}-${width}`);
  const target=await sample(c.page,150,300);results.push({test:'mark stays with its original frame after layout changes',width,target});
  if(broken)assert.notDeepEqual(target,[20,180,90]);else assert.deepEqual(target,[20,180,90]);
  if (!broken) {
    await c.page.evaluate(()=>{history.pushState({},'', '/changed');window.scrollTo(0,400);});
    await c.page.evaluate(async()=>window.shot=await drawing.capture());
    assert.deepEqual(await sample(c.page,150,300),[20,180,90], 'scroll and navigation cannot detach existing ink');
    assert.equal(await c.page.evaluate(()=>shot.pathname), '/');
    await c.page.evaluate(()=>window.scrollTo(0,0));
  }
  await c.page.evaluate(()=>drawing.hide());await c.page.evaluate(async()=>window.shot=await drawing.capture());assert.deepEqual(await sample(c.page,150,550),[20,180,90],'navigation resumes live capture');
  await c.page.evaluate(()=>window.scrollTo(0,1000));await c.page.waitForTimeout(100);await c.page.evaluate(()=>document.querySelector('#inner').scrollTop=400);
  await c.page.evaluate(async()=>window.shot=await captureViewport());await save(c.page,`scroll-${broken?'before':'after'}-${width}`);
  assert.deepEqual(await sample(c.page,10,820),[240,180,30],'fixed footer stays in viewport');
  assert.deepEqual(await sample(c.page,10,210),[160,40,160],'inner scroll position is captured');
  await c.ctx.close();
 }
 if (!broken) {
  const c=await setup();
  const result=await c.page.evaluate(async()=>{const task=captureViewport();setTimeout(()=>window.scrollTo(0,300),20);try{await task;return false;}catch(e){return e.retryable;}});
  assert.equal(result,true,'reject viewport that moves during cloning');
  assert.equal(await c.page.locator('.html2canvas-container').count(),0,'discarded clone is cleaned up');
  await c.page.evaluate(async()=>{window.drawing=createLiveDrawing(document.querySelector('#ink'),()=>{},()=>window.resized=true);await drawing.show();});
  await c.page.setViewportSize({width:430,height:900});await c.page.waitForFunction(()=>window.resized);assert.equal(await c.page.evaluate(()=>drawing.active),false);
  results.push({test:'unstable frames skipped, discarded clone cleaned, resize resets ink',passed:true});await c.ctx.close();
  const privacy=await setup();
  await privacy.page.evaluate(()=>{const box=document.createElement('div');box.style='position:absolute;top:400px;left:0;width:100px';box.innerHTML='<div data-feedback-private style="height:40px;background:red"><div style="visibility:visible!important;height:40px;background:red"></div></div><div style="height:40px;background:rgb(20,180,90)"></div>';document.body.append(box);});
  await privacy.page.evaluate(async()=>window.shot=await captureViewport());
  assert.deepEqual(await sample(privacy.page,10,420),[20,90,160], 'private descendants remain hidden even with explicit visibility');
  assert.deepEqual(await sample(privacy.page,10,460),[20,180,90], 'redaction preserves the geometry below private content');
  results.push({test:'private redaction preserves layout and hides descendants',passed:true});await privacy.ctx.close();
 }
 await writeFile(resolve(output,broken?'reproduced.json':'fidelity-tests.json'),JSON.stringify(results,null,2));console.log(results);
}finally{await browser.close();}
