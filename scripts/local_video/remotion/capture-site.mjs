import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const {chromium}=createRequire('/home/batata/Projects/nienfos.com/package.json')('playwright');
const root=path.resolve('../../../');
const output=path.join(root,'reports/videos/nienfos-10-versiones/source');
const assets=path.resolve('public/campaign');
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try {
  for(const mode of ['hero','ocean']) {
    const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,
      recordVideo:{dir:output,size:{width:1440,height:900}}});
    const page=await context.newPage();
    await page.goto('https://nienfos.com',{waitUntil:'networkidle'});
    await page.waitForFunction(()=>document.querySelectorAll('.franca-route').length===24);
    await page.evaluate(()=>document.fonts.ready);
    const text=await page.locator('body').innerText();
    await fs.writeFile(path.join(output,'website-text.txt'),text);
    if(mode==='hero') {
      await page.screenshot({path:path.join(assets,'site-desktop.png')});
      await page.locator('.brand-cover').screenshot({path:path.join(assets,'site-cover.png')});
      await fs.writeFile(path.join(output,'source.json'),JSON.stringify({url:'https://nienfos.com/',capturedAt:new Date().toISOString(),whaleTracks:24,viewport:[1440,900],scope:'Public home page; anonymous context; no forms submitted'},null,2));
    } else {
      await page.evaluate(()=>{
        const sea=document.querySelector('.sea-backdrop');
        document.body.replaceChildren(sea);
        document.body.style.cssText='margin:0;background:#1b3038;overflow:hidden';
        sea.style.cssText='display:block!important;position:fixed!important;inset:0!important;width:1440px!important;height:900px!important;opacity:1!important;transform:none!important;z-index:1!important';
        for(const e of sea.querySelectorAll('*'))for(const a of e.getAnimations()){
          if(e.classList.contains('franca-route'))a.playbackRate=3;
        }
      });
      await page.screenshot({path:path.join(assets,'ocean-still.png')});
    }
    await page.waitForTimeout(11000);
    const video=page.video();
    await context.close();
    await fs.copyFile(await video.path(),path.join(assets,mode+'-recording.webm'));
    console.log('Captured '+mode);
  }
} finally {await browser.close();}
