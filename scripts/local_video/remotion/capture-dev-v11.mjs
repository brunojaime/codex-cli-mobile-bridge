import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const {chromium}=createRequire('/home/batata/Projects/nienfos.com/package.json')('playwright');
const out=path.resolve('../../../reports/videos/nienfos-presentacion-v11-historia');
const assets=path.resolve('public/presentation-v11');
await fs.mkdir(path.join(out,'source'),{recursive:true});await fs.mkdir(assets,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
 for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
  const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1});
  const page=await context.newPage();
  const response=await page.goto('https://dev.nienfos.com/',{waitUntil:'networkidle',timeout:60000});
  await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(1800);
  await page.screenshot({path:path.join(out,'source',name+'-raw.png')});
  await page.addStyleTag({content:'.dev-label,.motion-toggle,.chat-launcher{visibility:hidden!important}'});
  await page.screenshot({path:path.join(assets,name+'.png')});
  await fs.copyFile(path.join(assets,name+'.png'),path.join(out,'source',name+'.png'));
  await page.screenshot({path:path.join(out,'source',name+'-full.png'),fullPage:true});
  const text=await page.locator('body').innerText();
  await fs.writeFile(path.join(out,'source',name+'-text.txt'),text);
  await fs.writeFile(path.join(out,'source',name+'.json'),JSON.stringify({url:page.url(),status:response.status(),capturedAt:new Date().toISOString(),viewport:[width,height],scope:'Public anonymous page, no forms submitted',displayedBrandUrl:'nienfos.com',captureOnlyHiddenElements:['.dev-label','.motion-toggle','.chat-launcher']},null,2));
  console.log(name,response.status(),text.slice(0,350));await context.close();
 }
}finally{await browser.close()}
