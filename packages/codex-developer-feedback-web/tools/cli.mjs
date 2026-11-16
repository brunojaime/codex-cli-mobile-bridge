#!/usr/bin/env node
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const args=process.argv.slice(2);
const result=spawnSync('python3',[fileURLToPath(new URL('./feedback_conformance.py',import.meta.url)),...(args.length?args:['--project',process.cwd(),'--release','feedback.release.json'])],{stdio:'inherit'});
if(result.error){console.error('Feedback conformance requires Python 3.9+.');process.exitCode=1;}
else process.exitCode=result.status??1;
