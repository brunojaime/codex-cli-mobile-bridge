import {existsSync} from 'node:fs';
import {openBrowser} from '@remotion/renderer';

const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE ??
  (existsSync('/usr/bin/google-chrome') ? '/usr/bin/google-chrome' : undefined);
const browser = await openBrowser('chrome', {browserExecutable});
await browser.close({silent: true});
console.log('Remotion: navegador abierto y cerrado correctamente. Sin render.');
