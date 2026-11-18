import {existsSync} from 'node:fs';
import {Config} from '@remotion/cli/config';

const browser = process.env.REMOTION_BROWSER_EXECUTABLE ??
  (existsSync('/usr/bin/google-chrome') ? '/usr/bin/google-chrome' : undefined);

if (browser) Config.setBrowserExecutable(browser);
