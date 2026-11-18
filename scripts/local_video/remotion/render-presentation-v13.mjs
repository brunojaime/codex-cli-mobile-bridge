import fs from 'node:fs/promises';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {getCompositions,openBrowser,renderMedia} from '@remotion/renderer';
const output=path.resolve('../../../reports/videos/nienfos-presentacion-v13-kanban');
await fs.mkdir(output,{recursive:true});
const serveUrl=await bundle({entryPoint:path.resolve('src/entry-v13.tsx'),publicDir:path.resolve('public')});
const browserExecutable='/usr/bin/google-chrome';
const browser=await openBrowser('chrome',{browserExecutable});
try{
const compositions=await getCompositions(serveUrl,{puppeteerInstance:browser,browserExecutable});
const composition=compositions.find(c=>c.id==='NienfosPresentacionV13');
if(!composition)throw new Error('Missing composition');
await renderMedia({composition,serveUrl,codec:'h264',outputLocation:path.join(output,'visual-sin-audio.mp4'),puppeteerInstance:browser,browserExecutable,concurrency:1,muted:true,crf:18,onProgress:({renderedFrames})=>{if(renderedFrames%60===0)console.log(renderedFrames+'/624')}});
console.log('DONE');
}finally{await browser.close({silent:true})}
