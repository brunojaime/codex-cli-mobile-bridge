// Deterministic local UI walkthrough. No agent/browser reasoning calls.
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import assert from 'node:assert/strict';

const [projectArg, outputArg, documentArg, base = 'http://127.0.0.1:18879'] = process.argv.slice(2);
if (!projectArg || !outputArg || !documentArg) throw new Error('Expected RD checkout, output folder, DEMO PDF');
const url = new URL(base);
assert.equal(url.hostname, '127.0.0.1', 'Recording only supports isolated loopback');
const health = await (await fetch(`${base}/api/health`)).json();
assert.equal(health.environment, 'local');
const require = createRequire(join(resolve(projectArg), 'package.json'));
const { chromium } = require('playwright');
const out = resolve(outputArg);
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 430, height: 720 },
  deviceScaleFactor: 1, locale: 'es-AR', serviceWorkers: 'block', reducedMotion: 'no-preference' });
let blocked = 0, requests = 0;
await context.route('**/*', async route => {
  if (new URL(route.request().url()).origin !== url.origin) { blocked++; await route.abort(); }
  else { requests++; await route.continue(); }
});
const page = await context.newPage();
page.setDefaultTimeout(45000);
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const pause = ms => page.waitForTimeout(ms);
// Animate actual scrolling and an instructional pointer; preserve application DOM content.
const reveal = async locator => {
  await locator.evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' }));
  await pause(550);
};
const point = async locator => {
  await reveal(locator);
  const box = await locator.boundingBox(); assert(box);
  const x = box.x + box.width/2, y = box.y + box.height/2;
  await page.evaluate(({x,y}) => {
    let cursor=document.getElementById('tutorial-pointer');
    if (!cursor) {
      cursor=document.createElement('div'); cursor.id='tutorial-pointer';
      Object.assign(cursor.style,{position:'fixed',left:'210px',top:'640px',width:'24px',height:'24px',
        border:'2px solid #00a5d1',background:'#00a5d12b',borderRadius:'50%',pointerEvents:'none',
        zIndex:'2147483647',transition:'left 360ms ease-in-out, top 360ms ease-in-out'});
      document.body.append(cursor); cursor.getBoundingClientRect();
    }
    // Native modal dialogs are in the browser top layer, above a body-level cursor.
    const parent=document.querySelector('dialog[open]') ?? document.body;
    if(cursor.parentElement!==parent) parent.append(cursor);
    cursor.style.left=`${x-12}px`;cursor.style.top=`${y-12}px`;
  },{x,y});
  await pause(390);
};
const tap = async locator => {
  await point(locator); await locator.evaluate(el => el.animate([{outline:'3px solid #00a5d1',outlineOffset:'2px'},{outline:'3px solid transparent',outlineOffset:'5px'}],{duration:650})); await locator.click();
  await page.evaluate(()=>document.getElementById('tutorial-pointer')?.animate([
    {transform:'scale(1)',opacity:1},{transform:'scale(1.8)',opacity:.35},{transform:'scale(1)',opacity:1}
  ],{duration:400}));
  await pause(120);
};
const type = async (locator,value) => {await tap(locator);await locator.fill('');await locator.pressSequentially(value,{delay:24});};
let activeEvents=[];
const mark = async id => {activeEvents.push({id,timestamp:await page.evaluate(()=>Date.now()/1000)});};
const cdp = await context.newCDPSession(page);
const timeline = [];
async function scene(id, action) {
  const dir = join(out, id); await mkdir(dir, { recursive: true });
  activeEvents=[];
  const frames = []; let writes = Promise.resolve();
  const listener = event => {
    const file = `frame-${String(frames.length).padStart(5, '0')}.jpg`;
    frames.push({ file, timestamp: event.metadata.timestamp });
    writes = writes.then(() => writeFile(join(dir, file), Buffer.from(event.data, 'base64')));
    void cdp.send('Page.screencastFrameAck', { sessionId: event.sessionId });
  };
  cdp.on('Page.screencastFrame', listener);
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 90, maxWidth: 860, maxHeight: 1440, everyNthFrame: 1 });
  await pause(400);
  await action();
  await pause(600);
  await cdp.send('Page.stopScreencast');
  cdp.off('Page.screencastFrame', listener);
  await writes;
  // CDP emits only changed frames. Always retain the terminal UI state, even when idle.
  const terminalTimestamp = await page.evaluate(() => Date.now()/1000);
  const terminalFile = `frame-${String(frames.length).padStart(5,'0')}.jpg`;
  await page.screenshot({path:join(dir,terminalFile),type:'jpeg',quality:90});
  frames.push({file:terminalFile,timestamp:terminalTimestamp});
  frames.sort((a,b)=>a.timestamp-b.timestamp);
  await page.screenshot({ path: join(out, `${id}.png`) });
  assert(frames.length >= 2, 'Expected captured UI states');
  // Freeze the last frame for one second, including the final still screenshot.
  const duration = frames.at(-1).timestamp - frames[0].timestamp + .4;
  await writeFile(join(dir, 'frames.json'), JSON.stringify({ frames, duration, events: activeEvents }, null, 2));
  timeline.push({ id, duration, frames: frames.length, events: activeEvents });
  console.log(id, frames.length, duration.toFixed(2));
}

const evidence={};
try {
  await page.goto(base);
  await page.getByLabel('Email',{exact:true}).fill('acceso.rd@example.invalid');
  await page.getByLabel('Contraseña',{exact:true}).fill('admin');
  await page.getByRole('button',{name:'Ingresar',exact:true}).click();
  await page.locator('.app-shell').waitFor();
  const reminder=page.getByRole('button',{name:'Ocultar por ahora'});
  if(await reminder.isVisible())await reminder.click();
  const sig=page.getByRole('dialog',{name:'Tu firma',exact:true});
  async function openSignature(){
    await tap(page.getByRole('button',{name:'Abrir menú',exact:true}));
    await tap(page.getByRole('button',{name:/^Opciones de /}));
    await tap(page.getByRole('button',{name:'Firma',exact:true}));
    await sig.getByLabel('Nombre',{exact:true}).waitFor();
  }
  await scene('signature-open',openSignature);
  await scene('signature-fields',async()=>{
    await type(sig.getByLabel('Nombre',{exact:true}),'Ana Pérez DEMO');
    await type(sig.getByLabel('Título o cargo (opcional)',{exact:true}),'Higiene y Seguridad');
    await type(sig.getByLabel('Teléfono (opcional)'),'000 DEMO');await mark('signature-fields');
  });
  await scene('signature-links',async()=>{
    await type(sig.getByLabel('Enlaces (opcionales)'),'https://ejemplo.invalid');
    for(const label of ['Agregar en mensajes nuevos','Agregar en respuestas']){
      const el=sig.getByLabel(label,{exact:true});await point(el);await el.setChecked(true);
    }
    await mark('signature-options');
  });
  await scene('signature-preview-a',async()=>{
    const preview=sig.getByLabel('Vista previa de firma');await point(preview);await pause(900);
    assert((await preview.innerText()).includes('Ana Pérez DEMO'));await mark('preview-a');
  });
  await scene('signature-change',async()=>{
    await type(sig.getByLabel('Nombre',{exact:true}),'Martín López DEMO');await mark('name-change');
    await reveal(sig.getByLabel('Vista previa de firma'));
    assert((await sig.getByLabel('Vista previa de firma').innerText()).includes('Martín López DEMO'));
  });
  await scene('signature-preview-b',async()=>{
    await point(sig.getByLabel('Vista previa de firma'));await pause(1000);
    await tap(sig.getByRole('button',{name:'Guardar firma',exact:true}));await sig.waitFor({state:'hidden'});await mark('signature-save');
  });
  await scene('signature-persist',async()=>{
    await openSignature();assert.equal(await sig.getByLabel('Nombre',{exact:true}).inputValue(),'Martín López DEMO');
    await point(sig.getByLabel('Vista previa de firma'));await pause(850);await mark('signature-reopen');
  });
  const settings=(await(await page.request.get(`${base}/api/v1/mail/signature`)).json()).data;
  assert.equal(settings.signature.name,'Martín López DEMO');assert(settings.signature.autoNew&&settings.signature.autoReply);
  evidence.signature={first_preview:'Ana Pérez DEMO',second_preview:settings.signature.name,persisted:true,autoNew:settings.signature.autoNew,autoReply:settings.signature.autoReply};
  await tap(sig.getByRole('button',{name:'Cerrar firma',exact:true}));
  await page.goto(`${base}/plantillas`);
  const panel=page.getByRole('region',{name:'Plantillas de correo',exact:true});
  await panel.getByLabel('Nombre de la plantilla').waitFor();
  const templates=(await(await page.request.get(`${base}/api/v1/notification-templates`)).json()).data.templates;
  const original=templates.find(t=>t.id==='renewal-default');const rem=templates.find(t=>t.id==='reminder-default');assert(original&&rem);
  await scene('templates-open',async()=>{await point(panel.getByRole('navigation',{name:'Elegir plantilla'}));await mark('templates-list');});
  await scene('template-edit',async()=>{
    await tap(panel.getByRole('button',{name:new RegExp(original.name)}));
    await type(panel.getByLabel('Asunto',{exact:true}),'Documentación actualizada: {{cliente}}');await mark('edit-existing');
  });
  await scene('template-save',async()=>{
    await tap(panel.getByRole('button',{name:'Guardar plantilla',exact:true}));
    await panel.getByRole('status').filter({hasText:'Plantilla guardada'}).waitFor();await mark('save-existing');
    await reveal(panel.getByRole('status'));await pause(700);
  });
  await scene('template-reminder',async()=>{
    await tap(panel.getByRole('button',{name:new RegExp(rem.name)}));
    assert.equal(await panel.getByLabel(/^Uso/).inputValue(),'reminder');
    await point(panel.getByLabel('Asunto',{exact:true}));await pause(550);
    await reveal(panel.getByRole('textbox',{name:'Mensaje',exact:true}));await mark('reminder-body');
  });
  await scene('template-new',async()=>{
    await tap(panel.getByRole('button',{name:'Nueva plantilla',exact:true}));
    await type(panel.getByLabel('Nombre de la plantilla'),'Informe técnico DEMO');await mark('new-name');
    await point(panel.getByLabel(/^Uso/));
  });
  await scene('template-subject',async()=>{
    await type(panel.getByLabel('Asunto',{exact:true}),'Informe para ');
    await point(panel.getByLabel('Insertar variable en asunto'));await panel.getByLabel('Insertar variable en asunto').selectOption('cliente');
    assert.equal(await panel.getByLabel('Asunto',{exact:true}).inputValue(),'Informe para {{cliente}}');await mark('subject-variable');
    await reveal(panel.getByLabel('Asunto',{exact:true}));
  });
  await scene('template-message',async()=>{
    const editor=panel.getByRole('textbox',{name:'Mensaje',exact:true});
    await type(editor,'Hola ');await editor.press('End');
    await point(panel.getByLabel('Insertar variable en mensaje'));await panel.getByLabel('Insertar variable en mensaje').selectOption('cliente');
    await editor.press('End');await editor.press('Enter');await editor.pressSequentially('Adjuntamos el informe técnico. Gracias.',{delay:24});
    await reveal(editor);await mark('message-variable');
    assert((await editor.innerText()).includes('{{cliente}}'));
  });
  await scene('template-preview',async()=>{
    await tap(panel.getByRole('button',{name:'Vista de ejemplo',exact:true}));
    const preview=panel.getByRole('region',{name:'Ejemplo con datos DEMO'});await point(preview);
    assert((await preview.innerText()).includes('Informe para Cliente DEMO'));assert(!(await preview.innerText()).includes('{{cliente}}'));await mark('template-preview');await pause(1100);
  });
  await scene('template-created',async()=>{
    await tap(panel.getByRole('button',{name:'Guardar plantilla',exact:true}));
    await panel.getByRole('status').filter({hasText:'Plantilla guardada'}).waitFor();
    await reveal(panel.getByRole('navigation',{name:'Elegir plantilla'}));
    await panel.getByRole('button',{name:/Informe técnico DEMO/}).waitFor();await mark('template-created');
  });
  await page.reload();await panel.getByLabel('Nombre de la plantilla').waitFor();
  await scene('template-switch',async()=>{
    await tap(panel.getByRole('button',{name:new RegExp(rem.name)}));await pause(600);
    await tap(panel.getByRole('button',{name:/Informe técnico DEMO/}));
    await point(panel.getByLabel('Asunto',{exact:true}));assert.equal(await panel.getByLabel('Asunto',{exact:true}).inputValue(),'Informe para {{cliente}}');await mark('template-selected');
  });
  const saved=(await(await page.request.get(`${base}/api/v1/notification-templates`)).json()).data.templates;
  const added=saved.find(t=>t.name==='Informe técnico DEMO');assert(added);
  assert.equal(saved.find(t=>t.id==='renewal-default').subject,'Documentación actualizada: {{cliente}}');
  evidence.templates={existing_updated:true,new_saved:true,new_subject:added.subject,reloaded:true,reminder_reviewed:true,preview_variables_resolved:true};
  // A real local draft ties the new template and saved signature together.
  const me=(await(await page.request.get(`${base}/api/v1/me`)).json()).data;const headers={'x-csrf-token':me.csrfToken};
  const response=await page.request.post(`${base}/api/v1/clients`,{headers,data:{idempotencyKey:crypto.randomUUID(),name:'Empresa DEMO',industry:'Tutorial DEMO',status:'incorporacion',sites:[],projects:[],professionalIds:[],checklist:[],services:[{name:'Seguridad DEMO',detail:'Ejemplo',scopeKind:'organizacion',scopeId:null}]}});assert.equal(response.status(),201);
  const clientId=(await response.json()).data.id;
  await page.request.post(`${base}/api/v1/clients/${clientId}/contacts`,{headers,data:{firstName:'Responsable',lastName:'DEMO',email:'responsable@example.invalid',jobTitle:'Seguridad',kind:'responsable'}});
  const management=(await(await page.request.get(`${base}/api/v1/clients/${clientId}/integral-management`)).json()).data;const category=management.base.find(c=>c.code==='RD-11');
  await page.goto(`${base}/clientes/${clientId}/gestion-integral/${category.id}`);
  await page.getByRole('button',{name:'Crear nueva actividad',exact:true}).click();await page.getByRole('button',{name:'Agregar novedad Documento',exact:false}).click();
  const dialog=page.getByRole('dialog',{name:'Agregar novedad',exact:true});
  await dialog.getByLabel('Título',{exact:true}).fill('Informe de seguridad DEMO');
  await dialog.getByLabel('Archivo',{exact:true}).setInputFiles(resolve(documentArg));
  await dialog.getByLabel('Fecha de fin de vigencia',{exact:true}).fill('2027-09-30');
  await dialog.getByLabel('Notificar por correo al guardar').check();await dialog.locator('.recipients input').first().check();
  await dialog.getByRole('button',{name:'Revisar correo',exact:true}).click();
  await scene('template-use',async()=>{
    const select=dialog.getByLabel('Plantilla de correo');await point(select);
    page.once('dialog',async prompt=>{assert.equal(prompt.type(),'confirm');assert(prompt.message().includes('Reemplazar este borrador'));await prompt.accept();});
    await select.selectOption(added.id);await mark('apply-template');
    await reveal(dialog.getByLabel('Asunto del correo'));assert.equal(await dialog.getByLabel('Asunto del correo').inputValue(),'Informe para Empresa DEMO');
  });
  await scene('template-result',async()=>{
    await point(dialog.getByRole('textbox',{name:'Mensaje',exact:true}));await pause(700);
    await reveal(dialog.getByLabel('Vista previa de firma'));assert((await dialog.getByLabel('Vista previa de firma').innerText()).includes('Martín López DEMO'));await mark('combined-result');await pause(900);
  });
  evidence.combined={subject:'Informe para Empresa DEMO',signature:'Martín López DEMO',sent:false};
  assert.equal(errors.length,0);
  await writeFile(join(out,'capture.json'),JSON.stringify({environment:health.environment,viewport:{width:430,height:720},scenes:timeline,evidence,page_errors:errors,browser_requests:requests,blocked_external_requests:blocked,mail_provider:'simulation',sent_real_mail:false},null,2));
} catch(error){await page.screenshot({path:join(out,'failure.png')}).catch(()=>{});throw error;}
finally{await browser.close();}
