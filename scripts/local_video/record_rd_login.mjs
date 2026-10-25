// Deterministic local UI walkthrough. No agent/browser reasoning calls.
import { createRequire } from 'node:module';
import { mkdir, writeFile, readFile, cp } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import assert from 'node:assert/strict';

const [projectArg, outputArg, base = 'http://127.0.0.1:18923', offlineProvider] = process.argv.slice(2);
if (!projectArg || !outputArg) throw new Error('Expected RD checkout, output folder');
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
let blocked=0, requests=0, providerPhase=false, authorization=null;
let stopOAuth;const oauthStopped=new Promise(resolve=>{stopOAuth=resolve;});
await context.route('**/*',async route=>{
 const req=route.request(), dest=new URL(req.url());
 if(dest.origin===url.origin){
   requests++;
   if(dest.pathname==='/api/v1/auth/zoho/start'){
     const response=await route.fetch({headers:{...req.headers(),origin:'https://rd-login-demo.invalid'}});
     const body=await response.json();
     authorization=body.data;
     await route.fulfill({response});
   }else await route.continue();
 }else if(!providerPhase && dest.hostname==='accounts.zoho.com' && dest.pathname==='/oauth/v2/auth'){
   // A 204 intercept stops the synthetic OAuth navigation without an error page.
   // The real local start endpoint still executes and its destination is asserted.
   blocked++;await route.fulfill({status:204,body:''});stopOAuth();
 }else if(providerPhase && (dest.hostname.endsWith('.zoho.com')||dest.hostname.endsWith('.zohostatic.com')||dest.hostname.endsWith('.zohocdn.com'))){
   if(req.method()==='GET'||(req.method()==='POST'&&dest.hostname==='accounts.zoho.com'&&dest.pathname==='/accounts/public/api/locate'))await route.continue();else{blocked++;await route.abort();}
 }else{blocked++;await route.abort();}
});
const page = await context.newPage();
page.setDefaultTimeout(45000);
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const pause = ms => page.waitForTimeout(ms);
// Animate actual scrolling and an instructional pointer; preserve application DOM content.
const reveal = async locator => {
  await locator.evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' }));
  await pause(300);
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
const type = async (locator,value) => {await tap(locator);await locator.fill('');await locator.pressSequentially(value,{delay:12});};
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

const evidence={target:'isolated RD local',synthetic_data:true,sent_real_mail:false,completed_zoho_login:false};
const email='acceso.rd@example.invalid', password='DemoClave2026!';
try {
  // Initialize only the disposable local account, then discard its session.
  const initial=await context.request.post(`${base}/api/v1/auth/login`,{data:{mode:'rd',email,password:'admin'}});
  assert.equal(initial.status(),200);await context.clearCookies();
  await page.goto(base);await page.getByRole('button',{name:'Ingresar con mi cuenta RD',exact:true}).waitFor();
  const status=await(await context.request.get(`${base}/api/v1/auth/zoho/status`)).json();assert(status.data.enabled);
  await scene('zoho-button',async()=>{
    await point(page.getByRole('button',{name:'Ingresar con mi cuenta RD',exact:true}));await mark('zoho-button');
  });
  // Execute the actual start action; block its OAuth navigation because the client is synthetic.
  const [startResponse]=await Promise.all([page.waitForResponse(r=>r.url()===`${base}/api/v1/auth/zoho/start`&&r.request().method()==='POST'),page.getByRole('button',{name:'Ingresar con mi cuenta RD',exact:true}).click()]);
  assert.equal(startResponse.status(),200);await startResponse.finished();
  let navigationTimer;try{await Promise.race([oauthStopped,new Promise((_,reject)=>{navigationTimer=setTimeout(()=>reject(new Error('OAuth navigation was not observed')),45000);})]);}finally{clearTimeout(navigationTimer);}
  assert(authorization);const target=new URL(authorization.authorizationUrl??authorization.url);
  assert.equal(target.hostname,'accounts.zoho.com');assert.equal(target.pathname,'/oauth/v2/auth');
  evidence.zoho={button:'Ingresar con mi cuenta RD',destination:target.origin+target.pathname,scope:target.searchParams.get('scope'),actual_start_checked:true};
  if(offlineProvider){
    if(resolve(offlineProvider)!==out)await cp(join(offlineProvider,'zoho-login'),join(out,'zoho-login'),{recursive:true});
    if(resolve(offlineProvider)!==out)await cp(join(offlineProvider,'zoho-login.png'),join(out,'zoho-login.png'));
    evidence.provider=JSON.parse(await readFile(join(offlineProvider,'provider.json'),'utf8'));
    timeline.push({id:'zoho-login',reused_public_capture:true});
  }else{
    providerPhase=true;
    await page.goto('https://accounts.zoho.com/signin',{waitUntil:'domcontentloaded'});
    await page.locator('input[name="LOGIN_ID"]').waitFor();
    await pause(7000);
    await page.getByText('No se encontró ninguna red.',{exact:false}).waitFor({state:'hidden',timeout:20000});
    await scene('zoho-login',async()=>{await point(page.locator('input[name="LOGIN_ID"]'));await mark('zoho-email-field');await pause(800);});
    evidence.provider={url:'https://accounts.zoho.com/signin',captured_at:new Date().toISOString(),public_page:true,submitted_credentials:false};
    providerPhase=false;
  }
  await writeFile(join(out,'provider.json'),JSON.stringify(evidence.provider,null,2));
  await page.goto(base);await page.getByLabel('Email',{exact:true}).waitFor();
  await scene('difference',async()=>{await point(page.getByLabel('Contraseña',{exact:true}));await mark('independent-app-password');});
  await scene('recover-open',async()=>{await tap(page.getByRole('button',{name:'Olvidé mi contraseña',exact:true}));await page.getByRole('button',{name:'Enviar enlace',exact:true}).waitFor();await mark('recovery-open');});
  await scene('recover-send',async()=>{
    await type(page.getByLabel('Email',{exact:true}),email);
    await tap(page.getByRole('button',{name:'Enviar enlace',exact:true}));
    await page.getByText('Si el email corresponde',{exact:false}).waitFor();await mark('request-sent');
  });
  const before=await(await context.request.get(`${base}/__demo/evidence`)).json();assert.equal(before.recipient,email);assert.equal(before.consumed,false);
  let resetUrl;
  await page.goto(`${base}/__demo/mail`);
  await scene('email',async()=>{await point(page.getByRole('link',{name:'Restablecer contraseña',exact:true}));resetUrl=await page.getByRole('link',{name:'Restablecer contraseña',exact:true}).getAttribute('href');assert(resetUrl.startsWith(base));await mark('email-link');});
  await scene('reset',async()=>{
    await mark('open-recovery-link');await tap(page.getByRole('link',{name:'Restablecer contraseña',exact:true}));
    await mark('new-password-field');await type(page.getByLabel('Nueva contraseña',{exact:true}),password);
    await mark('repeat-password-field');await type(page.getByLabel('Repetí la contraseña',{exact:true}),password);
    await mark('save-password');await tap(page.getByRole('button',{name:'Guardar y entrar',exact:true}));await page.locator('.app-shell').waitFor();await mark('password-created');
  });
  const after=await(await context.request.get(`${base}/__demo/evidence`)).json();assert.equal(after.consumed,true);
  await context.clearCookies();await page.goto(base);
  await scene('app-login',async()=>{
    await type(page.getByLabel('Email',{exact:true}),email);await type(page.getByLabel('Contraseña',{exact:true}),password);
    await tap(page.getByRole('button',{name:'Ingresar con contraseña',exact:true}));await page.locator('.app-shell').waitFor();await page.getByRole('heading',{name:/Administración/}).waitFor();await pause(400);await mark('app-login-success');
  });
  await context.clearCookies();
  const invalid=await context.request.post(`${base}/api/v1/auth/login`,{data:{mode:'rd',email,password:'admin'}});assert.equal(invalid.status(),401);
  const reused=await context.request.post(`${base}/api/v1/auth/recovery/complete`,{data:{token:new URL(resetUrl).searchParams.get('token'),newPassword:password}});assert.equal(reused.status(),400);assert.equal((await reused.json()).error.code,'access_link_invalid');
  evidence.recovery={mail:after,new_password_login:true,old_password_rejected:true,one_use_link:true,emailed_password:false};
  evidence.network={local_requests:requests,blocked_external:blocked};evidence.scenes=timeline;
  await writeFile(join(out,'evidence.json'),JSON.stringify(evidence,null,2));
} finally {await context.unrouteAll({behavior:'ignoreErrors'});await browser.close();}
