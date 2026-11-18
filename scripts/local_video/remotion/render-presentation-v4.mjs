import fs from 'node:fs/promises';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {getCompositions,openBrowser,renderMedia} from '@remotion/renderer';
const output=path.resolve('../../../reports/videos/nienfos-presentacion-v4');
await fs.mkdir(output,{recursive:true});
const serveUrl=await bundle({entryPoint:path.resolve('src/index.ts'),publicDir:path.resolve('public')});
const browserExecutable='/usr/bin/google-chrome';
const browser=await openBrowser('chrome',{browserExecutable});
try{
const compositions=await getCompositions(serveUrl,{puppeteerInstance:browser,browserExecutable});
const composition=compositions.find(c=>c.id==='NienfosPresentacionV4');
if(!composition)throw new Error('Missing composition');
await renderMedia({composition,serveUrl,codec:'h264',outputLocation:path.join(output,'presentacion.mp4'),puppeteerInstance:browser,browserExecutable,concurrency:1,muted:true,crf:18,onProgress:({renderedFrames})=>{if(renderedFrames%60===0)console.log(renderedFrames+'/690')}});
console.log('DONE');
}finally{await browser.close({silent:true})}
