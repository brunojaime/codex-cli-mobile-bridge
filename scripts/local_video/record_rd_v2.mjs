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
  await point(locator); await locator.click();
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
  assert(frames.length > 2, 'Expected actual UI movement');
  // Freeze the last frame for one second, including the final still screenshot.
  const duration = frames.at(-1).timestamp - frames[0].timestamp + .4;
  await writeFile(join(dir, 'frames.json'), JSON.stringify({ frames, duration, events: activeEvents }, null, 2));
  timeline.push({ id, duration, frames: frames.length, events: activeEvents });
  console.log(id, frames.length, duration.toFixed(2));
}

try {
  await page.goto(base);
  await page.getByLabel('Email', { exact: true }).fill('acceso.rd@example.invalid');
  await page.getByLabel('Contraseña', { exact: true }).fill('admin');
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click();
  await page.locator('.app-shell').waitFor();
  const reminder = page.getByRole('button', { name: 'Ocultar por ahora' });
  if (await reminder.isVisible()) await reminder.click();
  const me = (await (await page.request.get(`${base}/api/v1/me`)).json()).data;
  const headers = { 'x-csrf-token': me.csrfToken };
  const created = await page.request.post(`${base}/api/v1/clients`, { headers, data: {
    idempotencyKey: crypto.randomUUID(), name: 'Empresa DEMO', industry: 'Demostración de funcionalidades',
    status: 'incorporacion', sites: [], projects: [], professionalIds: [], checklist: [],
    services: [{ name: 'Seguridad e higiene DEMO', detail: 'Datos de ejemplo', scopeKind: 'organizacion', scopeId: null }]
  }});
  assert.equal(created.status(), 201);
  const clientId = (await created.json()).data.id;
  const contact = await page.request.post(`${base}/api/v1/clients/${clientId}/contacts`, { headers,
    data: { firstName: 'Responsable', lastName: 'DEMO', email: 'responsable@example.invalid', jobTitle: 'Seguridad', kind: 'responsable' } });
  assert.equal(contact.status(), 201);
  const management = (await (await page.request.get(`${base}/api/v1/clients/${clientId}/integral-management`)).json()).data;
  const category = management.base.find(c => c.code === 'RD-11'); assert(category);
  await page.goto(`${base}/clientes/${clientId}`);
  await page.getByRole('button', { name: 'Crear nueva actividad', exact: true }).waitFor();
  const dialog = page.getByRole('dialog', { name: 'Agregar novedad', exact: true });
  await scene('abrir', async () => {
    await tap(page.getByRole('button', {name:'Crear nueva actividad',exact:true}));
    await tap(page.getByRole('button', {name:'Agregar novedad Documento',exact:false}));
    await dialog.waitFor(); await mark('open');
    await point(dialog.getByLabel('Categoría técnica'));
    await dialog.getByLabel('Categoría técnica').selectOption(category.id); await mark('category');
    await type(dialog.getByLabel('Título',{exact:true}),'Chequeo de extintores DEMO');
    await reveal(dialog.getByRole('button',{name:'Agregar archivos',exact:false}));
  });
  await scene('documento', async () => {
    const chooser=page.waitForEvent('filechooser');
    await tap(dialog.getByRole('button',{name:'Agregar archivos',exact:false}));
    await (await chooser).setFiles(resolve(documentArg));
    await dialog.getByText('chequeo-DEMO.pdf',{exact:false}).first().waitFor(); await mark('upload');
    const start=dialog.getByLabel('Fecha de inicio de vigencia (opcional)',{exact:true});
    await point(start); await start.fill('2026-09-29');
    const end=dialog.getByLabel('Fecha de fin de vigencia',{exact:true});
    await point(end); await end.fill('2027-09-29'); await mark('validity');
    await tap(dialog.getByLabel('Notificar por correo al guardar'));
    await reveal(dialog.getByRole('checkbox',{name:/Responsable DEMO/}));
  });
  await scene('correo', async () => {
    await tap(dialog.getByRole('checkbox',{name:/Responsable DEMO/})); await mark('recipients');
    await tap(dialog.getByRole('button',{name:'Revisar correo',exact:true}));
    await reveal(dialog.getByLabel('Plantilla de correo')); await mark('review');
    await pause(450);
    await point(dialog.getByLabel('Asunto del correo')); await mark('template');
    assert((await dialog.getByLabel('Asunto del correo').inputValue()).includes('Empresa DEMO'));
    await reveal(dialog.getByRole('textbox',{name:'Mensaje',exact:true})); await pause(800);
  });
  await scene('guardar', async () => {
    const save=dialog.getByRole('button',{name:'Guardar y enviar',exact:true});
    await point(save); await pause(300);
    await save.click(); await mark('save');
    await dialog.waitFor({state:'hidden'});
    const jobs=page.getByRole('complementary',{name:'Operaciones en segundo plano'});
    await tap(jobs.getByRole('button',{name:'Mostrar detalles de operaciones'}));
    await jobs.getByText('Novedad guardada.',{exact:false}).last().waitFor(); await mark('background');
    await pause(700);
  });
  const result = (await (await page.request.get(`${base}/api/v1/clients/${clientId}/document-renewals`)).json()).data;
  assert.equal(result.renewals.length, 1);
  assert.equal(result.renewals[0].files.length, 1);
  assert.equal(result.renewals[0].notices.length, 1);
  assert.equal(errors.length, 0);
  await writeFile(join(out, 'capture.json'), JSON.stringify({ edition: 2, environment: health.environment, scenes: timeline,
    browser_requests: requests, blocked_external_requests: blocked, page_errors: errors,
    saved_renewals: result.renewals.length, saved_files: result.renewals[0].files.length,
    saved_notices: result.renewals[0].notices.length, mail_provider: 'simulation',
    notice_status: result.renewals[0].notices[0].status, viewport: { width: 430, height: 720 } }, null, 2));
} catch (error) {
  await page.screenshot({ path: join(out, 'failure.png') }).catch(() => {});
  throw error;
} finally { await browser.close(); }
