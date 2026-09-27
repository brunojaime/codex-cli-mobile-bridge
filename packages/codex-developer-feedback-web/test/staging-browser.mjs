import { chromium } from 'playwright';
import { readFile, stat, writeFile, mkdir } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import assert from 'node:assert/strict';
const app = process.argv[2];
assert.ok(['rd','chrem'].includes(app));
const origin = `https://${app}-staging.nienfos.com`;
const output = resolve('../../reports/staging-feedback-flow-20260926');
await mkdir(output,{recursive:true});
const buildRoot = process.env.FEEDBACK_BUILD_ROOT;
const mode = buildRoot ? 'predeploy' : 'live';
const browser = await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'],proxy:{server:'socks5://127.0.0.1:1055'}});
try {
 const context = await browser.newContext({viewport:{width:390,height:844},hasTouch:true});
 if(buildRoot) await context.route(origin+'/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const file=resolve(buildRoot,path==='/'?'index.html':'.'+path);
  if(!file.startsWith(resolve(buildRoot)+'/'))return route.continue();
  try{
   if(!(await stat(file)).isFile())return route.continue();
   const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.json':'application/json'};
   return route.fulfill({body:await readFile(file),contentType:mime[extname(file)]||'application/octet-stream'});
  }catch{return route.continue();}
 });
 const page=await context.newPage();
 let submitted=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/feedback-batches'))submitted++;});
 const response=await page.goto(origin,{waitUntil:'domcontentloaded',timeout:60000});assert.equal(response.status(),200);
 const launch=page.getByRole('button',{name:'Abrir feedback',exact:true});await launch.waitFor();
 assert.equal(await page.locator('[data-codex-feedback]').getAttribute('data-codex-feedback'),'0.3.0');
 await page.screenshot({path:resolve(output,`${app}-${mode}-bug-390.png`)});
 await launch.click();
 await page.waitForFunction(()=>document.querySelector('[data-codex-feedback]')?.shadowRoot?.querySelectorAll('#preset option').length>2,{},{timeout:20000});
 const presets=await page.locator('#preset option').count();
 await page.screenshot({path:resolve(output,`${app}-${mode}-tools-390.png`)});
 await page.getByRole('button',{name:'Dibujar en pantalla',exact:true}).click();
 const canvas=page.locator('#drawing-canvas');await canvas.waitFor({state:'visible'});
 const box=await canvas.boundingBox();assert.equal(box.width,390);assert.equal(box.height,844);assert.equal(box.x,0);assert.equal(box.y,0);const handle=page.getByRole('button',{name:'Mover herramientas',exact:true});const hb=await handle.boundingBox();await page.mouse.move(hb.x+22,hb.y+22);await page.mouse.down();await page.mouse.move(38,110,{steps:10});await page.mouse.up();const cx=box.x+box.width*.48,cy=box.y+box.height*.27;
 const rx=box.width*.32,ry=box.height*.08;
 const cdp=await context.newCDPSession(page);
 const touch=async(type,x,y)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y}]});
 await touch('touchStart',cx+rx,cy);
 for(let i=1;i<=32;i++){const a=i*Math.PI*2/32;await touch('touchMove',cx+Math.cos(a)*rx,cy+Math.sin(a)*ry);}
 await touch('touchEnd',0,0);
 await page.locator('#drawing-hint').filter({hasText:'1 trazo'}).waitFor();
 await page.screenshot({path:resolve(output,`${app}-${mode}-drawing-390.png`)});
 await page.getByRole('button',{name:'Comentar',exact:true}).click();
 await page.getByLabel('¿Qué querés cambiar?').fill('Prueba de dibujo libre en staging. No enviar.');
 await page.getByRole('button',{name:'Guardar en la cola',exact:true}).click();
 assert.equal(submitted,0);
 await page.reload({waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'Abrir feedback, 1 pendientes',exact:true}).click();
 await page.getByRole('button',{name:'Ver pendientes (1)',exact:true}).click();
 assert.match(await page.locator('#queue').innerText(),/Prueba de dibujo libre/);
 await page.getByRole('button',{name:'Eliminar',exact:true}).click();await page.getByRole('button',{name:'Cerrar feedback',exact:true}).click();await page.getByRole('button',{name:'Abrir feedback',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Grabar recorrido con voz'}).isVisible(),true);
 await page.getByRole('button',{name:'Grabar recorrido con voz'}).click();await page.locator('#recording-frames').filter({hasText:'1 capturas'}).waitFor();
 await page.waitForTimeout(1500);await page.getByRole('button',{name:'Capturar paso',exact:true}).click();await page.locator('#recording-frames').filter({hasText:'2 capturas'}).waitFor();
 await page.screenshot({path:resolve(output,`${app}-${mode}-recording-390.png`)});
 await page.getByRole('button',{name:'Detener recorrido',exact:true}).click();await page.locator('#trace-review').waitFor({state:'visible'});
 assert.equal(await page.locator('#trace-audio').isVisible(),true);assert.ok(Number(await page.locator('#trace-position').getAttribute('max'))>=2);
 await page.locator('#trace-audio').evaluate(a=>a.play());await page.waitForTimeout(150);await page.locator('#trace-audio').evaluate(a=>a.pause());
 await page.screenshot({path:resolve(output,`${app}-${mode}-review-390.png`)});
 await page.getByRole('button',{name:'Guardar recorrido',exact:true}).click();await page.reload({waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'Abrir feedback, 1 pendientes',exact:true}).click();await page.getByRole('button',{name:'Ver pendientes (1)',exact:true}).click();assert.match(await page.locator('#queue').innerText(),/Recorrido/);
 await page.getByRole('button',{name:'Eliminar',exact:true}).click();assert.equal(submitted,0);

 const result={app,mode,url:origin,at:new Date().toISOString(),version:'0.3.0',bugIcon:true,nativeSize:true,floatingTools:true,guidedTrace:true,audioRecorderAndPlayback:true,microphoneDevice:"simulated Chromium device",freehandTouch:true,persistence:true,bridgePresets:presets,submissions:submitted};
 await writeFile(resolve(output,`${app}-${mode}.json`),JSON.stringify(result,null,2));console.log(result);
}finally{await browser.close();}
