import fs from 'node:fs/promises';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {getCompositions,openBrowser,renderMedia,renderStill} from '@remotion/renderer';
const output=path.resolve('../../../reports/videos/nienfos-v20-crecer');
await fs.mkdir(output,{recursive:true});
const serveUrl=await bundle({entryPoint:path.resolve('src/entry-v20.tsx'),publicDir:path.resolve('public')});
const browserExecutable='/usr/bin/google-chrome';
const browser=await openBrowser('chrome',{browserExecutable});
try {
 const comps=await getCompositions(serveUrl,{puppeteerInstance:browser,browserExecutable});
 const composition=comps.find(c=>c.id==='NienfosV20');
 if(!composition)throw new Error('Missing composition');
 const common={composition,serveUrl,puppeteerInstance:browser,browserExecutable};
 for(const [name,frame] of [['portada',0],['gancho',85],['problema',188],['giro',225],['oficio',320],['diseno',406],['integracion',454],['proyectos',518],['futuro',612],['cierre',714]]) {
  await renderStill({...common,output:path.join(output,name+'.png'),frame,imageFormat:'png'});
 }
 let last=-1;
 if(!process.argv.includes('--stills-only')) await renderMedia({...common,codec:'h264',outputLocation:path.join(output,'visual-sin-audio.mp4'),concurrency:4,disableSharedMemoryCapture:true,disallowParallelEncoding:true,x264Preset:'veryfast',muted:true,crf:18,onProgress:({renderedFrames})=>{const step=Math.floor(renderedFrames/60);if(step!==last){last=step;console.log(renderedFrames+'/'+composition.durationInFrames)}}});
 console.log('DONE');
}finally{await browser.close({silent:true})}
