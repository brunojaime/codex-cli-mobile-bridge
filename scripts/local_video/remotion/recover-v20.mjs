// Complete interrupted screenshots, then hold the fully settled closing card.
import fs from 'node:fs/promises';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {getCompositions,openBrowser,renderStill} from '@remotion/renderer';
const frames=path.resolve('../../../.local-videos/nienfos-v20-crecer/render-frames');
const url=await bundle({entryPoint:path.resolve('src/entry-v20.tsx'),publicDir:path.resolve('public')});
const browserExecutable='/usr/bin/google-chrome';
const browser=await openBrowser('chrome',{browserExecutable});
try{
 const comps=await getCompositions(url,{puppeteerInstance:browser,browserExecutable});
 const composition=comps.find(c=>c.id==='NienfosV20');
 if(!composition)throw new Error('Missing composition');
 for(let frame=0;frame<=713;frame++){
  const output=path.join(frames,`element-${String(frame).padStart(3,'0')}.jpeg`);
  try{await fs.access(output);continue;}catch{}
  console.log('Recover exact frame',frame);
  await renderStill({composition,serveUrl:url,puppeteerInstance:browser,browserExecutable,frame,output,imageFormat:'jpeg',jpegQuality:80});
 }
 // Closing composition is static after frame 692: all entrances have settled.
 const tail=await fs.readFile(path.join(frames,'element-713.jpeg'));
 for(let frame=714;frame<composition.durationInFrames;frame++) await fs.writeFile(path.join(frames,`element-${String(frame).padStart(3,'0')}.jpeg`),tail);
 console.log('Recovered sequence; final static hold complete');
}finally{await browser.close({silent:true})}
