// Private, temporary human access to the OAuth tab; reuse the existing viewer.
// Passwords and MFA stay in the user's browser interaction and are never logged.
import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir,chmod} from 'node:fs/promises';
import {homedir} from 'node:os';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';

let startupStage='configuration';
let cleanupBrowser;
async function main(){
const root=resolve(import.meta.dirname,'..');
const shared=process.env.NIENFOS_SHARED_BROWSER_ROOT ?? '/home/batata/Projects/nienfos-gestion/integrations';
const {VisibleSession}=await import(pathToFileURL(join(shared,'social-browser/visible-session.mjs')));
const {createVisibleServer}=await import(pathToFileURL(join(shared,'social-browser/visible-server.mjs')));
const require=createRequire(join(homedir(),'.local/share/codex-browser/node_modules/playwright/package.json'));
const {chromium}=require('playwright');
const config=JSON.parse(await readFile(join(homedir(),'.local/state/nienfos-bridge-browser/firebase-admin/visible-config.json'),'utf8'));
const pending=JSON.parse(await readFile(join(root,'.data/relevamientos-inbox/oauth-pending.json'),'utf8'));
const callback=new URL(new URL(pending.url).searchParams.get('redirect_uri'));
let connection, context, ownsContext=false;
startupStage='browser_connection';
try {
  connection=await chromium.connectOverCDP('http://127.0.0.1:9223');
  context=connection.contexts()[0];
} catch {
  // The former desktop browser may have stopped. A dedicated private profile
  // lets the operator complete consent without opening another user's profile.
  const profile=join(root,'.data/relevamientos-inbox/oauth-browser-profile');
  await mkdir(profile,{recursive:true,mode:0o700});
  await chmod(profile,0o700);
  context=await chromium.launchPersistentContext(profile,{
    executablePath:'/opt/google/chrome/chrome',headless:true,
    viewport:{width:430,height:780},args:['--no-sandbox'],
  });
  ownsContext=true;
}
cleanupBrowser=()=>ownsContext?context.close():connection.close();
let page=context.pages().find(p=>{
  try{return new URL(p.url()).hostname==='accounts.google.com';}catch{return false;}
});
if(!page)page=await context.newPage();
startupStage='google_navigation';
await page.goto(pending.url,{waitUntil:'domcontentloaded',timeout:60000});
startupStage='viewer_setup';
const directory=join(root,'.data/relevamientos-inbox/viewer');
await mkdir(directory,{recursive:true,mode:0o700});
await chmod(directory,0o700);
const html=await readFile(join(shared,'bridge-browser/mcp-viewer.html'),'utf8');
const htmlPath=join(directory,'viewer.html');
await writeFile(htmlPath,html.replaceAll('/firebase-browser','/drive-browser').replaceAll('Consola Google','Autorización de Google Drive'),{mode:0o600});
await page.setViewportSize({width:430,height:780});
const allowedUrl=(value)=>{
  try{
    const u=new URL(value);
    return u.origin===callback.origin && u.pathname===callback.pathname ||
      u.protocol==='https:' && ['accounts.google.com','myaccount.google.com'].includes(u.hostname);
  }catch{return false;}
};
const browser={page,dir:directory,brandId:'Google Drive',state:{},transport:'private-oauth-viewer',checkpoint:async()=>{}};
const session=new VisibleSession(browser,{ttlMs:30*60*1000,allowedUrl,targets:{home:pending.url,login:pending.url}});
// The page belongs to an existing Chrome session. Do not initialize/close its
// context or other tabs. Human take-control/release is enforced by shared code.
await session.save();
const server=await createVisibleServer({session,origin:config.origin,login:config.login,basePath:'/drive-browser',htmlPath});
await new Promise((ok,fail)=>{server.once('error',fail);server.listen(8799,'127.0.0.1',ok)});
console.log(JSON.stringify({state:'human_login_available',url:config.origin+'/drive-browser/',expiresAt:session.expiresAt}));
async function stop(){server.close();server.closeAllConnections();if(ownsContext)await context.close();else await connection.close();process.exit(0)}
process.on('SIGTERM',stop);process.on('SIGINT',stop);
setTimeout(stop,session.expiresAt-Date.now());
}
main().catch(async(error)=>{console.error(JSON.stringify({state:'viewer_start_failed',stage:startupStage,error_type:error.name,network_code:error.message?.match(/net::ERR_[A-Z_]+/)?.[0]}));if(cleanupBrowser)await cleanupBrowser().catch(()=>{});process.exitCode=1;});
