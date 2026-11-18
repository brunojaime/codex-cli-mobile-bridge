import fs from 'node:fs/promises';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {getCompositions,openBrowser,renderMedia} from '@remotion/renderer';

const stories=JSON.parse(await fs.readFile('campaign-pro.json','utf8'));
const output=path.resolve('../../../reports/videos/nienfos-10-profesional');
const selected=process.argv.slice(2);
const browserExecutable='/usr/bin/google-chrome';
const serveUrl=await bundle({entryPoint:path.resolve('src/index.ts'),publicDir:path.resolve('public')});
const browser=await openBrowser('chrome',{browserExecutable});
try {
  const compositions=await getCompositions(serveUrl,{puppeteerInstance:browser,browserExecutable});
  for(const story of stories.filter(s=>selected.length===0 || selected.includes(s.id))) {
    const folder=path.join(output,story.id);
    await fs.mkdir(folder,{recursive:true});
    const composition=compositions.find(c=>c.id==='NienfosPro-'+story.id);
    if(!composition)throw new Error('Composition missing: '+story.id);
    console.log('START '+story.id+' '+story.title);
    const started=Date.now();
    await renderMedia({composition,serveUrl,codec:'h264',outputLocation:path.join(folder,'video.mp4'),
      puppeteerInstance:browser,browserExecutable,concurrency:1,muted:true,crf:20,
      onStart:({frameCount})=>console.log('FRAMES '+story.id+' '+frameCount),
      onProgress:({progress,renderedFrames})=>{if(renderedFrames%30===0)console.log('PROGRESS '+story.id+' '+renderedFrames+' '+Math.round(progress*100)+'%');}});
    await fs.writeFile(path.join(folder,'recipe.json'),JSON.stringify({...story,composition:composition.id,
      frames:composition.durationInFrames,fps:30,size:[720,1280],audio:false,renderSeconds:(Date.now()-started)/1000},null,2));
    console.log('DONE '+story.id+' '+Math.round((Date.now()-started)/1000)+'s');
  }
} finally {await browser.close({silent:true});}
