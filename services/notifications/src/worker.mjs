import {createInterface} from 'node:readline';
import {openDatabase} from './sqlite.mjs';
import {createEngine} from './engine.mjs';
const credential=JSON.parse(process.env.CODEX_PUSH_CREDENTIAL??'null');
const db=openDatabase(process.env.CODEX_PUSH_DATABASE);
const engine=createEngine({db,environment:process.env.CODEX_PUSH_ENVIRONMENT,projectId:credential.project_id,
 origin:process.env.CODEX_PUSH_ORIGIN,bridgeId:process.env.CODEX_PUSH_BRIDGE_ID,credential});
await engine.prune();
let ticking=false,passes=0;
const timer=setInterval(async()=>{if(ticking)return;ticking=true;try{await engine.tick();if(++passes%17280===0)await engine.prune();}catch(error){const code=/^[A-Za-z_]+$/.test(error?.code??'')?error.code:'retry';process.stderr.write('Push dispatch pass failed ('+code+'); retrying.\n');}finally{ticking=false;}},5000);
for await(const line of createInterface({input:process.stdin})){
 let input;
 try{input=JSON.parse(line);const result=input.method==='register'?await engine.register(input.params):input.method==='tick'?await engine.tick():{ready:true};process.stdout.write(JSON.stringify({id:input.id,result})+'\n');}
 catch{process.stdout.write(JSON.stringify({id:input?.id,error:'push_operation_failed'})+'\n');}
}
clearInterval(timer);db.connection.close();
